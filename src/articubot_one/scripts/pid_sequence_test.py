#!/usr/bin/env python3
"""Deterministic drive-sequence runner for PID tuning.

Publishes a teleop-style command sequence, forces a zero-command stop after
every active move, logs the robot response to CSV for graphing, and reports
command-to-response ratios in the final summary. It also listens to the ESP32
telnet encoder stream so the test can evaluate the wheel response directly.
"""

import argparse
import csv
import math
import os
import re
import socket  # used for direct ESP32 Telnet; avoids telnetlib (deprecated 3.11, removed 3.13)
import signal
import sys
import time
import threading
from dataclasses import dataclass
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, Imu


DEFAULT_LOG = Path.home() / "dev_ws" / "pid_sequence_log.csv"

# Topics that can drive the robot — stale CLI publishers on any of these are
# hazardous when enable_motion:=true is active on the Pi.
_MOTION_TOPICS = (
    "/cmd_vel_joy",
    "/cmd_vel_raw",
    "/cmd_vel",
    "/diff_cont/cmd_vel_unstamped",
)


def _kill_stale_motion_publishers():
    """Kill any ros2 topic pub/hz processes publishing to motion topics on this machine.

    Stale publishers left over from previous test sessions or manual CLI
    commands are dangerous when enable_motion:=true is active on the Pi:
    twist_mux → vel_smoother → ESP32 is live and any nonzero command will
    drive the robot.  /diff_cont/cmd_vel_unstamped publishers bypass
    twist_mux entirely.
    """
    import subprocess as _sp

    killed = 0
    try:
        result = _sp.run(["ps", "aux"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "ros2 topic pub" not in line and "ros2 topic hz" not in line:
                continue
            if not any(t in line for t in _MOTION_TOPICS):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[1])
                if pid == os.getpid():
                    continue
                os.kill(pid, signal.SIGTERM)
                cmd_snippet = " ".join(parts[10:14]) if len(parts) > 13 else " ".join(parts[10:])
                print(f"[cleanup] killed stale publisher PID {pid}: {cmd_snippet}", flush=True)
                killed += 1
            except (ProcessLookupError, ValueError, PermissionError):
                pass
    except Exception as exc:
        print(f"[cleanup] warning: stale publisher scan failed: {exc}", flush=True)
    if killed:
        time.sleep(0.3)
    return killed


WHEEL_RADIUS = 0.034
WHEEL_SEP = 0.179
ENC_LINE_RE = re.compile(
    r"\[enc\]\s+(?:cnt=(?P<cnt_l>-?\d+)/(?P<cnt_r>-?\d+)\s+)?"
    r"tgt=(?P<tgt_l>-?\d+(?:\.\d+)?)/(?P<tgt_r>-?\d+(?:\.\d+)?)\s+"
    r"act=(?P<act_l>-?\d+(?:\.\d+)?)/(?P<act_r>-?\d+(?:\.\d+)?)\s+"
    r"filt=(?P<filt_l>-?\d+(?:\.\d+)?)/(?P<filt_r>-?\d+(?:\.\d+)?)"
)
CMD_LINE_RE = re.compile(
    r"\[cmd\]\s+lin=(?P<lin>-?\d+(?:\.\d+)?)\s+ang=(?P<ang>-?\d+(?:\.\d+)?)\s+armed=(?P<armed>[01])"
)

ARM_SECONDS = 2.0


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    linear: float
    angular: float
    duration: float
    stop_hold: float
    goal_counts: int = 0    # >0 = count-based stop; 0 = time-based
    max_counts: int = 0     # adaptive upper bound (0 = same as goal_counts)


def make_twist(linear: float, angular: float) -> Twist:
    msg = Twist()
    msg.linear.x = float(linear)
    msg.angular.z = float(angular)
    return msg


def yaw_from_quaternion(q) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def twist_values(msg):
    if msg is None:
        return "", ""
    twist = msg.twist.twist
    return twist.linear.x, twist.angular.z


def parse_step(token: str, default_duration: float, stop_hold: float) -> Step:
    token = token.strip()
    if not token:
        raise ValueError("empty step token")

    if ":" in token:
        key, duration = token.split(":", 1)
    elif "@" in token:
        key, duration = token.split("@", 1)
    else:
        key, duration = token, default_duration

    key = key.strip()
    duration = float(duration)

    mapping = {
        "i": ("forward", 0.20, 0.0),
        "forward": ("forward", 0.20, 0.0),
        "k": ("stop", 0.0, 0.0),
        "stop": ("stop", 0.0, 0.0),
        ",": ("reverse", -0.20, 0.0),
        "rev": ("reverse", -0.20, 0.0),
        "back": ("reverse", -0.20, 0.0),
        "j": ("turn_left", 0.0, 1.00),
        "left": ("turn_left", 0.0, 1.00),
        "l": ("turn_right", 0.0, -1.00),
        "right": ("turn_right", 0.0, -1.00),
        "u": ("forward_left", 0.20, 1.00),
        "o": ("forward_right", 0.20, -1.00),
        "m": ("reverse_left", -0.20, 1.00),
        ".": ("reverse_right", -0.20, -1.00),
        "0": ("stop", 0.0, 0.0),
    }
    if key not in mapping:
        raise ValueError(f"unknown step key '{key}'")

    label, linear, angular = mapping[key]
    return Step(key=key, label=label, linear=linear, angular=angular, duration=duration, stop_hold=stop_hold)


def build_profile(name: str, duration: float, stop_hold: float) -> list[Step]:
    if name == "bridge":
        return [
            parse_step("i", duration, stop_hold),
            parse_step("k", 1.0, 1.0),
            parse_step(",", duration, stop_hold),
            parse_step("k", 1.0, 1.0),
            parse_step("j", duration, stop_hold),
            parse_step("k", 1.0, 1.0),
        ]
    if name == "smooth":
        # One sustained forward command followed by a full stop window so we can
        # measure startup, hold, and decay without stop-go command chopping.
        return [
            parse_step("i", duration, stop_hold),
            parse_step("k", max(2.0, stop_hold), max(2.0, stop_hold)),
        ]
    if name == "rebound":
        return [
            parse_step("i", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
            parse_step("l", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
            parse_step(",", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
            parse_step("j", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
        ]
    if name == "power":
        return [
            parse_step("i", 5.0, 1.0),
            parse_step("k", 1.0, 1.0),
            parse_step(",", 5.0, 1.0),
            parse_step("k", 1.0, 1.0),
        ]
    if name == "straight":
        return [
            parse_step("i", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
            parse_step(",", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
        ]
    if name == "turns":
        return [
            parse_step("j", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
            parse_step("l", duration, stop_hold),
            parse_step("k", stop_hold, stop_hold),
        ]
    raise ValueError(f"unknown profile '{name}'")


def parse_sequence(sequence: str, default_duration: float, stop_hold: float) -> list[Step]:
    tokens = sequence.replace("\n", ";").replace("|", ";").split(";")
    steps = [parse_step(token, default_duration, stop_hold) for token in tokens if token.strip()]
    if not steps:
        raise ValueError("sequence is empty")
    return steps


class DriveSequenceRunner(Node):
    def __init__(self, args):
        super().__init__("pid_sequence_test")
        self.args = args

        # Turn state must be initialised before _build_steps so that the
        # profile-specific values set inside _build_steps are not overwritten.
        self._turn_started_at = None
        self._turn_goal_counts = 0
        self._turn_goal_revs = 0.0
        self._turn_max_counts = 0
        self._turn_extend_counts = 0
        self._turn_velocity_floor = args.turn_velocity_floor
        self._turn_adaptive = args.turn_adaptive

        self.steps = self._build_steps(args)
        self.repeats_left = max(1, args.repeats)
        self.sequence_index = 0
        self.phase = "arm"
        self.phase_started = time.monotonic()
        self.current_step = self.steps[0]
        self.done = False
        self.interrupted = False
        self._preflight_started_at = None
        self._preflight_tgt_seen = False
        self._bridge_enc_seen = False
        self._bridge_cmd_seen = False
        self._bridge_cmd_count = 0
        self._bridge_cmd_last_t = None
        self._imu_accel_filt = 0.0   # EMA-filtered IMU accel_x (vibration suppressed)
        self._ang_err_samples = []   # |imu_gyro_z - enc_ang| collected during motion
        self._bridge_cmd_max_gap = 0.0

        # Per-step IMU tracking (reset each time active phase starts)
        self._step_yaw_start: float | None = None
        self._step_yaw_end: float | None = None
        self._step_gyro_integral_rad: float = 0.0
        self._step_gyro_prev_t: float | None = None
        self._step_gyro_prev_gz: float | None = None
        self._step_imu_results: list = []  # one dict per completed step
        self._bridge_cmd_track_active = False

        self.latest_battery = None
        self.latest_imu = None
        self.latest_raw = None
        self.latest_ekf = None
        self.latest_enc = None
        self.latest_enc_at = None
        self.latest_enc_counts = None
        self.latest_enc_counts_at = None
        self.latest_cmd = make_twist(0.0, 0.0)
        self._state_lock = threading.Lock()
        self._enc_stop = threading.Event()
        self._enc_sock = None
        self._enc_sock_lock = threading.Lock()

        self.pub = self.create_publisher(Twist, args.command_topic, 10)
        self.stop_pubs = [self.pub]
        # Stop all upstream command topics so vel_smoother ramps to zero.
        # Do NOT publish to /diff_cont/cmd_vel_unstamped — a second publisher there
        # disrupts the micro_ros_agent DDS matching with vel_smoother.
        stop_topics = ["/cmd_vel_joy", "/cmd_vel"]
        for topic in stop_topics:
            if topic != args.command_topic:
                self.stop_pubs.append(self.create_publisher(Twist, topic, 10))
        if args.command_topic == "/cmd_vel_joy":
            self.get_logger().info(
                "This runner expects motion to be enabled at launch (enable_motion:=true) so twist_mux is active."
            )
        self.create_subscription(BatteryState, "/battery_state", self._on_battery, 10)
        self.create_subscription(Imu, "/imu/imu", self._on_imu, 10)
        self.create_subscription(Odometry, "/diff_cont/odom", self._on_raw_odom, 10)
        self.create_subscription(Odometry, "/odom", self._on_ekf_odom, 10)

        self.command_period = 1.0 / args.command_rate
        self.log_period = 1.0 / args.log_rate
        self.warmup_seconds = args.warmup
        self.next_command_at = time.monotonic()
        self.next_log_at = time.monotonic()
        self.cmd_timer = self.create_timer(0.02, self._tick)
        self.log_timer = self.create_timer(0.02, self._log_if_due)

        self.started_at = time.monotonic()
        self.last_sample = {}
        self.summary = {
            "min_battery_v": None,
            "max_current_a": None,
            "max_power_w": 0.0,
            "max_abs_cmd_vx": 0.0,
            "max_abs_cmd_wz": 0.0,
            "max_abs_cmd_wheel_l": 0.0,
            "max_abs_cmd_wheel_r": 0.0,
            "max_abs_raw_vx": 0.0,
            "max_abs_raw_wz": 0.0,
            "max_abs_ekf_vx": 0.0,
            "max_abs_ekf_wz": 0.0,
            "max_abs_enc_act_l": 0.0,
            "max_abs_enc_act_r": 0.0,
            "max_abs_enc_filt_l": 0.0,
            "max_abs_enc_filt_r": 0.0,
            "max_abs_enc_cnt_l": 0,
            "max_abs_enc_cnt_r": 0,
            "turn_goal_cnt": 0,
            "bridge_cmd_count": 0,
            "bridge_cmd_max_gap_s": 0.0,
        }
        self._enc_thread = threading.Thread(target=self._enc_monitor_loop, daemon=True)
        self._enc_thread.start()
        # Encoder reset happens after preflight succeeds (see _advance)

        self.log_path = Path(args.output).expanduser()
        self.log_file = self.log_path.open("w", newline="")
        self.writer = csv.writer(self.log_file)
        # Metadata rows (prefixed with '#') — readable by scripts that skip comment lines
        self.writer.writerow(["# test_date", time.strftime("%Y-%m-%d %H:%M:%S")])
        self.writer.writerow(["# profile", args.profile or "custom"])
        self.writer.writerow(["# command_topic", args.command_topic])
        self.writer.writerow(["# turn_revolutions", args.turn_revolutions])
        self.writer.writerow(["# turn_max_revolutions", args.turn_max_revolutions])
        self.writer.writerow(["# turn_extend_revolutions", args.turn_extend_revolutions])
        self.writer.writerow(["# floor_distance_m", args.floor_distance])
        self.writer.writerow(["# turn_linear_ms", args.turn_linear])
        self.writer.writerow(["# turn_angular_rads", args.turn_angular])
        self.writer.writerow(["# turn_velocity_floor", args.turn_velocity_floor])
        self.writer.writerow(["# turn_adaptive", args.turn_adaptive])
        self.writer.writerow(["# turn_max_time_s", args.turn_max_time])
        self.writer.writerow(["# turn_counts_per_rev", args.turn_counts_per_rev])
        self.writer.writerow(["# log_rate_hz", args.log_rate])
        self.writer.writerow(["# command_rate_hz", args.command_rate])
        self.writer.writerow(["# warmup_s", args.warmup])
        self.writer.writerow([
            "wall_time", "elapsed_s", "run", "phase", "key", "label",
            "cmd_lin", "cmd_ang",
            "battery_v", "current_a", "power_w",
            "raw_vx", "raw_wz", "ekf_vx", "ekf_wz",
            "imu_yaw_deg", "imu_gyro_z", "imu_accel_x", "imu_accel_x_filt",
            "cmd_wheel_l", "cmd_wheel_r",
            "enc_cnt_l", "enc_cnt_r",
            "enc_tgt_l", "enc_tgt_r",
            "enc_act_l", "enc_act_r",
            "enc_filt_l", "enc_filt_r",
            "enc_derived_lin_mps", "enc_derived_ang_rps",
            "turn_goal_cnt",
        ])

        self.get_logger().info(
            f"logging to {self.log_path} | profile={args.profile or 'custom'} | repeats={self.repeats_left} | warmup={self.warmup_seconds}s"
        )

    def _build_steps(self, args):
        if args.sequence:
            return parse_sequence(args.sequence, args.duration, args.stop_hold)
        if args.profile == "one_turn":
            self._turn_goal_revs = max(0.1, float(args.turn_revolutions))
            self._turn_goal_counts = max(1, int(round(args.turn_counts_per_rev * self._turn_goal_revs)))
            self._turn_max_counts = max(
                self._turn_goal_counts,
                int(round(args.turn_counts_per_rev * max(self._turn_goal_revs, float(args.turn_max_revolutions)))),
            )
            self._turn_extend_counts = max(1, int(round(args.turn_counts_per_rev * float(args.turn_extend_revolutions))))
            return [
                Step(
                    key="i",
                    label="one_turn",
                    linear=args.turn_linear,
                    angular=args.turn_angular,
                    duration=args.turn_max_time,
                    stop_hold=args.stop_hold,
                    goal_counts=self._turn_goal_counts,
                    max_counts=self._turn_max_counts,
                )
            ]
        if args.profile == "monitor":
            # No steps — monitor mode listens and logs; user drives with teleop.
            return [Step(key="k", label="monitor", linear=0.0, angular=0.0, duration=86400.0, stop_hold=0.0)]
        if args.profile == "floor_baseline":
            # Canonical 4-move floor test: fwd Xm, bwd Xm, left 360°, right 360°
            # All moves run in one process to avoid DDS re-matching between invocations.
            # Step timing is kinematics-derived so the test is robust when the telnet
            # enc monitor is unreliable (dropping/reconnecting). The enc monitor still
            # runs and logs velocity data, but does not control the stop condition.
            lin = args.turn_linear
            spn = args.floor_spin_rate
            rotations = args.floor_spin_rotations
            stop_h = args.stop_hold
            dist_label = f"{args.floor_distance:.2f}m".rstrip("0").rstrip(".")
            rot_label  = f"{rotations:.0f}x360" if rotations != 1 else "360"
            # vel_smoother ramp rates (match launch_robot.launch.py vel_smoother params)
            lin_accel = 0.5   # m/s²
            ang_accel = 1.0   # rad/s²
            # Correct kinematic formula: active phase covers ramp-up + cruise.
            # During ramp (t_ramp = spn/ang_accel), only half the angle of a
            # constant-speed ramp is covered.  The deficit = spn/(2*ang_accel) extra
            # cruise time to compensate.  Decel is an abrupt snap-to-zero from
            # vel_smoother, so no decel term is needed here.
            fwd_time  = args.floor_distance / lin + lin / (2.0 * lin_accel)
            spin_time = rotations * 2.0 * math.pi / spn + spn / (2.0 * ang_accel)
            return [
                Step(key="i", label=f"fwd_{dist_label}",       linear=lin,  angular=0.0,  duration=fwd_time,  stop_hold=stop_h, goal_counts=0),
                Step(key=",", label=f"bwd_{dist_label}",       linear=-lin, angular=0.0,  duration=fwd_time,  stop_hold=stop_h, goal_counts=0),
                Step(key="j", label=f"left_{rot_label}",        linear=0.0,  angular=spn,  duration=spin_time, stop_hold=stop_h, goal_counts=0),
                Step(key="l", label=f"right_{rot_label}",       linear=0.0,  angular=-spn, duration=spin_time, stop_hold=stop_h, goal_counts=0),
            ]
        return build_profile(args.profile, args.duration, args.stop_hold)

    def _on_battery(self, msg):
        self.latest_battery = msg
        self.summary["min_battery_v"] = msg.voltage if self.summary["min_battery_v"] is None else min(
            self.summary["min_battery_v"], msg.voltage
        )
        self.summary["max_current_a"] = msg.current if self.summary["max_current_a"] is None else max(
            self.summary["max_current_a"], msg.current
        )

    def _on_imu(self, msg):
        self.latest_imu = msg

    def _on_raw_odom(self, msg):
        self.latest_raw = msg
        vx, wz = twist_values(msg)
        if vx != "":
            self.summary["max_abs_raw_vx"] = max(self.summary["max_abs_raw_vx"], abs(vx))
            self.summary["max_abs_raw_wz"] = max(self.summary["max_abs_raw_wz"], abs(wz))

    def _on_ekf_odom(self, msg):
        self.latest_ekf = msg
        vx, wz = twist_values(msg)
        if vx != "":
            self.summary["max_abs_ekf_vx"] = max(self.summary["max_abs_ekf_vx"], abs(vx))
            self.summary["max_abs_ekf_wz"] = max(self.summary["max_abs_ekf_wz"], abs(wz))

    def _update_encoder_sample(self, sample):
        with self._state_lock:
            sample_at = time.monotonic()
            self.latest_enc = sample
            self.latest_enc_at = sample_at
            self._bridge_enc_seen = True
            if sample.get("cnt_l") is not None and sample.get("cnt_r") is not None:
                self.latest_enc_counts = sample
                self.latest_enc_counts_at = sample_at
                self.summary["max_abs_enc_cnt_l"] = max(self.summary["max_abs_enc_cnt_l"], abs(int(sample["cnt_l"])))
                self.summary["max_abs_enc_cnt_r"] = max(self.summary["max_abs_enc_cnt_r"], abs(int(sample["cnt_r"])))
            if hasattr(self, "summary"):
                self.summary["max_abs_enc_act_l"] = max(self.summary["max_abs_enc_act_l"], abs(sample["act_l"]))
                self.summary["max_abs_enc_act_r"] = max(self.summary["max_abs_enc_act_r"], abs(sample["act_r"]))
                self.summary["max_abs_enc_filt_l"] = max(self.summary["max_abs_enc_filt_l"], abs(sample["filt_l"]))
                self.summary["max_abs_enc_filt_r"] = max(self.summary["max_abs_enc_filt_r"], abs(sample["filt_r"]))

    def _update_cmd_sample(self, sample):
        with self._state_lock:
            self._bridge_cmd_seen = True
            now = time.monotonic()
            is_nonzero = abs(float(sample.get("lin", 0.0))) > 0.001 or abs(float(sample.get("ang", 0.0))) > 0.001
            self._bridge_cmd_count += 1
            if self.args.profile == "bridge" and not self._bridge_cmd_track_active:
                if is_nonzero:
                    self._bridge_cmd_track_active = True
                    self._bridge_cmd_last_t = now
                return
            if self._bridge_cmd_last_t is not None:
                self._bridge_cmd_max_gap = max(self._bridge_cmd_max_gap, now - self._bridge_cmd_last_t)
            self._bridge_cmd_last_t = now

    def _turn_motion_alive(self, enc):
        if not enc:
            return False
        if self.args.turn_wheel == "left":
            return abs(float(enc.get("act_l", 0.0))) >= self._turn_velocity_floor
        if self.args.turn_wheel == "right":
            return abs(float(enc.get("act_r", 0.0))) >= self._turn_velocity_floor
        return min(abs(float(enc.get("act_l", 0.0))), abs(float(enc.get("act_r", 0.0)))) >= self._turn_velocity_floor

    def _send_encoder_reset(self):
        host = self.args.encoder_host
        port = self.args.encoder_port
        with self._enc_sock_lock:
            sock = self._enc_sock
        if sock is not None:
            try:
                sock.sendall(b"r")
                return
            except Exception as exc:
                self.get_logger().warn(f"encoder reset on monitor socket failed: {exc}")
        try:
            with socket.create_connection((host, port), timeout=5.0) as sock:
                sock.sendall(b"r")
        except Exception as exc:
            self.get_logger().warn(f"encoder reset failed: {exc}")

    def _enc_monitor_loop(self):
        host = self.args.encoder_host
        port = self.args.encoder_port
        while not self._enc_stop.is_set():
            try:
                with socket.create_connection((host, port), timeout=5.0) as sock:
                    with self._enc_sock_lock:
                        self._enc_sock = sock
                    sock.settimeout(1.0)
                    buffer = ""
                    while not self._enc_stop.is_set():
                        try:
                            chunk = sock.recv(1024)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        buffer += chunk.decode("utf-8", errors="ignore")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            match = ENC_LINE_RE.search(line)
                            if not match:
                                cmd_match = CMD_LINE_RE.search(line)
                                if cmd_match:
                                    self._update_cmd_sample(
                                        {
                                            "lin": float(cmd_match.group("lin")),
                                            "ang": float(cmd_match.group("ang")),
                                            "armed": int(cmd_match.group("armed")),
                                        }
                                    )
                                continue
                            self._update_encoder_sample(
                                {
                                    "cnt_l": int(match.group("cnt_l")) if match.group("cnt_l") is not None else None,
                                    "cnt_r": int(match.group("cnt_r")) if match.group("cnt_r") is not None else None,
                                    "tgt_l": float(match.group("tgt_l")),
                                    "tgt_r": float(match.group("tgt_r")),
                                    "act_l": float(match.group("act_l")),
                                    "act_r": float(match.group("act_r")),
                                    "filt_l": float(match.group("filt_l")),
                                    "filt_r": float(match.group("filt_r")),
                                }
                            )
                    with self._enc_sock_lock:
                        if self._enc_sock is sock:
                            self._enc_sock = None
            except Exception as exc:
                with self._enc_sock_lock:
                    self._enc_sock = None
                self.get_logger().warn(f"encoder monitor offline: {exc}")
                if self._enc_stop.wait(2.0):
                    break

    def _current_cmd(self):
        if self.phase == "arm":
            return 0.0, 0.0
        if self.phase == "preflight":
            return 0.0, 0.0
        if self.phase == "active":
            return self.current_step.linear, self.current_step.angular
        return 0.0, 0.0

    def _step_done(self):
        if self.phase == "arm":
            return (time.monotonic() - self.phase_started) >= ARM_SECONDS
        if self.phase == "preflight":
            now = time.monotonic()
            if self._preflight_started_at is None:
                self._preflight_started_at = now
            elapsed = now - self._preflight_started_at
            with self._state_lock:
                enc = self.latest_enc or {}
                bridge_enc_seen = self._bridge_enc_seen
                bridge_cmd_seen = self._bridge_cmd_seen
            if self.args.profile == "bridge":
                if self._bridge_cmd_count >= 2:
                    return True
                if elapsed > 5.0:
                    self.get_logger().error(
                        "[PREFLIGHT FAILED] ESP32 did not log a steady command stream while "
                        "the bridge was publishing zero. The Pi-to-ESP32 path is not fully alive."
                    )
                    self.done = True
                    return True
                return False
            # Preflight sends zeros — confirm DDS delivery by counting [cmd] lines
            # arriving from the ESP32 telnet stream (_bridge_cmd_count increments for
            # all profiles). A count ≥ 5 means the full path is live with no motion.
            if self._bridge_cmd_count >= 5:
                return True
            if elapsed > 15.0:
                self.get_logger().error(
                    "[PREFLIGHT FAILED] No [cmd] telemetry from ESP32 after 15s of zeros. "
                    "The micro_ros_agent DDS bridge is stuck — commands are not reaching the ESP32. "
                    "Fix: sudo systemctl restart robot-launch.service (may need 2-3 attempts after OTA flash)"
                )
                self.done = True
                return True
            return False
        if self.current_step.goal_counts > 0 and self.phase == "active":
            with self._state_lock:
                enc = self.latest_enc_counts or {}
                enc_at = self.latest_enc_counts_at or 0.0
            if enc:
                if self._turn_started_at is not None and enc_at < self._turn_started_at:
                    return False
                left = abs(int(enc.get("cnt_l", 0)))
                right = abs(int(enc.get("cnt_r", 0)))
                target = self._turn_goal_counts
                if self._turn_started_at is None:
                    self._turn_started_at = time.monotonic()
                if self.args.turn_wheel == "left":
                    reached = left >= target
                elif self.args.turn_wheel == "right":
                    reached = right >= target
                else:
                    reached = min(left, right) >= target
                if reached:
                    if self._turn_adaptive and self._turn_goal_counts < self._turn_max_counts and self._turn_motion_alive(enc):
                        self._turn_goal_counts = min(self._turn_max_counts, self._turn_goal_counts + self._turn_extend_counts)
                        self.get_logger().info(
                            f"adaptive turn target extended to {self._turn_goal_counts} counts "
                            f"({self._turn_goal_counts / self.args.turn_counts_per_rev:.2f} rev)"
                        )
                        return False
                    return True
                if (time.monotonic() - self._turn_started_at) >= self.current_step.duration:
                    self.get_logger().warn(
                        f"count-based step '{self.current_step.label}' timeout reached before target count "
                        f"({min(left, right)}/{target})"
                    )
                    return True
        if self.phase == "warmup":
            return (time.monotonic() - self.phase_started) >= self.warmup_seconds
        return (time.monotonic() - self.phase_started) >= (
            self.current_step.duration if self.phase == "active" else self.current_step.stop_hold
        )

    def _reset_step_imu(self):
        self._step_yaw_start = None
        self._step_yaw_end = None
        self._step_gyro_integral_rad = 0.0
        self._step_gyro_prev_t = None
        self._step_gyro_prev_gz = None

    def _report_step_imu(self):
        step = self.current_step
        if step is None or self._step_yaw_start is None:
            return
        label = step.label
        gyro_deg = self._step_gyro_integral_rad * 180.0 / math.pi
        yaw_delta = (self._step_yaw_end - self._step_yaw_start) if self._step_yaw_end is not None else float("nan")
        is_spin = abs(step.angular) > 0.01 and abs(step.linear) < 0.01
        if is_spin:
            rotations = self.args.floor_spin_rotations if self.args.profile == "floor_baseline" else 1.0
            expected_deg = rotations * (360.0 if step.angular > 0 else -360.0)
            overshoot = gyro_deg - expected_deg
            pct = 100.0 * gyro_deg / expected_deg if expected_deg else 0.0
            print(
                f"[imu] {label:<16}  gyro_total={gyro_deg:+.1f}°  expected={expected_deg:+.0f}°  delta={overshoot:+.1f}°  ({pct:.1f}%)",
                flush=True,
            )
        else:
            direction = "CURVED RIGHT" if gyro_deg < -5 else "CURVED LEFT" if gyro_deg > 5 else "straight"
            print(
                f"[imu] {label:<14}  heading_drift={gyro_deg:+.1f}°  ({direction})",
                flush=True,
            )
        self._step_imu_results.append({
            "label": label,
            "gyro_deg": gyro_deg,
            "yaw_delta": yaw_delta,
            "is_spin": is_spin,
            "expected_deg": (rotations * (360.0 if step.angular > 0 else -360.0)) if is_spin else 0.0,
        })

    def _advance(self):
        if self.phase == "arm":
            if self.current_step.goal_counts > 0:
                self._publish_zero()
                self._turn_goal_counts = self.current_step.goal_counts
                self._turn_max_counts = self.current_step.max_counts or self.current_step.goal_counts
                if not self.args.no_encoder_reset:
                    self._send_encoder_reset()
                    with self._state_lock:
                        self.latest_enc_counts = None
                        self.latest_enc_counts_at = None
                self.phase = "warmup"
                self.phase_started = time.monotonic()
                return
            self.phase = "preflight"
            self.phase_started = time.monotonic()
            self._publish_zero()
            return

        if self.phase == "preflight":
            self._publish_zero()
            if not self.done:
                self.get_logger().info("preflight OK — commands reaching ESP32")
                if self.current_step.goal_counts > 0 and not self.args.no_encoder_reset:
                    self._send_encoder_reset()
                    with self._state_lock:
                        self.latest_enc_counts = None
                        self.latest_enc_counts_at = None
                self.phase = "warmup"
                self.phase_started = time.monotonic()
            return

        if self.phase == "warmup":
            self.phase = "active"
            self.phase_started = time.monotonic()
            self._turn_started_at = self.phase_started if self.current_step.goal_counts > 0 else None
            self._reset_step_imu()
            return

        if self.phase == "active":
            self._report_step_imu()
            self.phase = "stop"
            self.phase_started = time.monotonic()
            self._publish_zero()
            return

        self.sequence_index += 1
        if self.sequence_index >= len(self.steps):
            self.repeats_left -= 1
            if self.repeats_left <= 0:
                self.done = True
                self._publish_zero()
                return
            self.sequence_index = 0
        self.current_step = self.steps[self.sequence_index]
        if self.current_step.goal_counts > 0:
            self._publish_zero()
            self._turn_goal_counts = self.current_step.goal_counts
            self._turn_max_counts = self.current_step.max_counts or self.current_step.goal_counts
            self._turn_started_at = None
            if not self.args.no_encoder_reset:
                self._send_encoder_reset()
                with self._state_lock:
                    self.latest_enc_counts = None
                    self.latest_enc_counts_at = None
            self.phase = "warmup"
            self.phase_started = time.monotonic()
        else:
            self.phase = "active"
            self.phase_started = time.monotonic()
            self._reset_step_imu()

    def _publish_zero(self):
        self.latest_cmd = make_twist(0.0, 0.0)
        self.pub.publish(self.latest_cmd)

    def _tick(self):
        if self.done:
            return

        now = time.monotonic()
        if now < self.next_command_at:
            return

        lin, ang = self._current_cmd()
        self.latest_cmd = make_twist(lin, ang)
        self.pub.publish(self.latest_cmd)
        self.next_command_at = now + self.command_period

        if self._step_done():
            self._advance()

    def _log_if_due(self):
        if self.done:
            return
        if self.args.log_active_only and self.phase != "active":
            return
        now = time.monotonic()
        if now < self.next_log_at:
            return
        self.next_log_at = now + self.log_period
        self._write_sample(now)

    def _write_sample(self, now):
        cmd_abs_vx = abs(self.latest_cmd.linear.x)
        cmd_abs_wz = abs(self.latest_cmd.angular.z)
        self.summary["max_abs_cmd_vx"] = max(self.summary["max_abs_cmd_vx"], cmd_abs_vx)
        self.summary["max_abs_cmd_wz"] = max(self.summary["max_abs_cmd_wz"], cmd_abs_wz)
        cmd_wheel_l = (self.latest_cmd.linear.x - self.latest_cmd.angular.z * WHEEL_SEP * 0.5) / WHEEL_RADIUS
        cmd_wheel_r = (self.latest_cmd.linear.x + self.latest_cmd.angular.z * WHEEL_SEP * 0.5) / WHEEL_RADIUS
        self.summary["max_abs_cmd_wheel_l"] = max(self.summary["max_abs_cmd_wheel_l"], abs(cmd_wheel_l))
        self.summary["max_abs_cmd_wheel_r"] = max(self.summary["max_abs_cmd_wheel_r"], abs(cmd_wheel_r))
        self.summary["turn_goal_cnt"] = self._turn_goal_counts
        self.summary["bridge_cmd_count"] = self._bridge_cmd_count
        self.summary["bridge_cmd_max_gap_s"] = self._bridge_cmd_max_gap

        battery_v = current_a = ""
        power_w = ""
        if self.latest_battery is not None:
            battery_v = self.latest_battery.voltage
            current_a = self.latest_battery.current
            power_w = battery_v * current_a
            self.summary["max_power_w"] = max(self.summary["max_power_w"], power_w)

        raw_vx, raw_wz = twist_values(self.latest_raw)
        ekf_vx, ekf_wz = twist_values(self.latest_ekf)
        imu_yaw = imu_gyro_z = imu_accel_x = imu_accel_x_filt = ""
        if self.latest_imu is not None:
            imu_yaw = yaw_from_quaternion(self.latest_imu.orientation)
            imu_gyro_z = self.latest_imu.angular_velocity.z
            raw_accel = self.latest_imu.linear_acceleration.x
            imu_accel_x = raw_accel
            self._imu_accel_filt = 0.1 * raw_accel + 0.9 * self._imu_accel_filt
            imu_accel_x_filt = self._imu_accel_filt
        with self._state_lock:
            enc = self.latest_enc or {}

        filt_l = float(enc.get("filt_l", 0.0)) if enc else 0.0
        filt_r = float(enc.get("filt_r", 0.0)) if enc else 0.0
        enc_derived_lin = (filt_l + filt_r) * WHEEL_RADIUS / 2.0
        enc_derived_ang = (filt_r - filt_l) * WHEEL_RADIUS / WHEEL_SEP
        enc_derived_lin_out = enc_derived_lin if enc else ""
        enc_derived_ang_out = enc_derived_ang if enc else ""

        if self.phase == "active" and enc and imu_gyro_z != "":
            self._ang_err_samples.append(abs(float(imu_gyro_z) - enc_derived_ang))

        # Accumulate per-step IMU heading / rotation for step summary
        if self.phase == "active" and self.latest_imu is not None:
            step_yaw = yaw_from_quaternion(self.latest_imu.orientation)
            step_gz = float(self.latest_imu.angular_velocity.z)
            if self._step_yaw_start is None:
                self._step_yaw_start = step_yaw
                self._step_gyro_prev_t = now
                self._step_gyro_prev_gz = step_gz
            else:
                dt_imu = now - self._step_gyro_prev_t
                if 0.0 < dt_imu < 0.5:
                    self._step_gyro_integral_rad += 0.5 * (step_gz + self._step_gyro_prev_gz) * dt_imu
                self._step_gyro_prev_t = now
                self._step_gyro_prev_gz = step_gz
            self._step_yaw_end = step_yaw

        self.writer.writerow(
            [
                time.strftime("%H:%M:%S", time.localtime()),
                f"{now - self.started_at:.3f}",
                self.sequence_index + 1,
                self.phase,
                self.current_step.key if self.current_step else "",
                self.current_step.label if self.current_step else "",
                self.latest_cmd.linear.x,
                self.latest_cmd.angular.z,
                battery_v,
                current_a,
                power_w,
                raw_vx,
                raw_wz,
                ekf_vx,
                ekf_wz,
                imu_yaw,
                imu_gyro_z,
                imu_accel_x,
                imu_accel_x_filt,
                cmd_wheel_l,
                cmd_wheel_r,
                enc.get("cnt_l", ""),
                enc.get("cnt_r", ""),
                enc.get("tgt_l", ""),
                enc.get("tgt_r", ""),
                enc.get("act_l", ""),
                enc.get("act_r", ""),
                enc.get("filt_l", ""),
                enc.get("filt_r", ""),
                enc_derived_lin_out,
                enc_derived_ang_out,
                self._turn_goal_counts,
            ]
        )
        self.log_file.flush()

    def force_stop(self, duration=3.0):
        # 3.0s: vel_smoother ramps at 1.0 rad/s² so 1.5 rad/s → 0 takes 1.5s; direct
        # /diff_cont/cmd_vel_unstamped publish stops ESP32 immediately as a belt-and-suspenders.
        print("[stop] publishing zeros to all motion topics...", flush=True)
        end = time.monotonic() + duration
        zero = make_twist(0.0, 0.0)
        while time.monotonic() < end:
            for pub in self.stop_pubs:
                pub.publish(zero)
            time.sleep(0.05)
        print("[stop] done", flush=True)

    def close(self):
        self._enc_stop.set()
        self.log_file.close()

    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--profile",
            default="rebound",
            choices=["bridge", "smooth", "rebound", "power", "straight", "turns", "one_turn", "floor_baseline"],
            help="predefined teleop-style sequence; floor_baseline runs fwd/bwd 1m + left/right 360° in one process",
        )
        parser.add_argument(
            "--sequence",
            help="custom sequence like 'i:1.0;k:0.4;l:0.8;k:0.4' (overrides --profile)",
        )
        parser.add_argument("--duration", type=float, default=1.2, help="default active duration for a step")
        parser.add_argument("--stop-hold", type=float, default=0.5, help="seconds to hold zero after each active move")
        parser.add_argument("--repeats", type=int, default=1, help="repeat the chosen profile this many times")
        parser.add_argument("--warmup", type=float, default=2.0, help="seconds to wait before starting the sequence")
        parser.add_argument(
            "--command-topic",
            default="/cmd_vel_joy",
            help="topic to publish commands on; /cmd_vel_joy routes through twist_mux at highest priority",
        )
        parser.add_argument(
            "--encoder-host",
            default="esp32-mybot.local",
            help="host serving the ESP32 telnet encoder stream",
        )
        parser.add_argument(
            "--encoder-port",
            type=int,
            default=23,
            help="port for the ESP32 telnet encoder stream",
        )
        parser.add_argument("--command-rate", type=float, default=10.0, help="publish rate while moving")
        parser.add_argument("--log-rate", type=float, default=10.0, help="CSV sample rate")
        parser.add_argument(
            "--log-all-phases",
            dest="log_active_only",
            action="store_false",
            help="log warmup/stop phases as well as active motion; default logs active motion only",
        )
        parser.set_defaults(log_active_only=True)
        parser.add_argument("--output", default=str(DEFAULT_LOG), help="CSV output file")
        parser.add_argument(
            "--turn-wheel",
            default="both",
            choices=["left", "right", "both"],
            help="which wheel counts toward the one-turn stop condition",
        )
        parser.add_argument("--turn-counts-per-rev", type=float, default=1010.0, help="encoder counts per revolution")
        parser.add_argument("--turn-revolutions", type=float, default=1.0, help="initial target revolutions")
        parser.add_argument(
            "--turn-adaptive",
            action="store_true",
            help="extend the target in rev-sized steps while wheel velocity stays above the floor",
        )
        parser.add_argument(
            "--turn-extend-revolutions",
            type=float,
            default=1.0,
            help="revolutions to add each time the current target is met in adaptive mode",
        )
        parser.add_argument(
            "--turn-max-revolutions",
            type=float,
            default=50.0,
            help="maximum revolutions to allow in adaptive mode",
        )
        parser.add_argument(
            "--turn-velocity-floor",
            type=float,
            default=0.50,
            help="minimum encoder wheel speed required to extend an adaptive turn",
        )
        parser.add_argument("--turn-linear", type=float, default=0.20, help="linear command during one-turn test")
        parser.add_argument("--turn-angular", type=float, default=0.0, help="angular command during one-turn test")
        parser.add_argument("--floor-distance", type=float, default=0.25, help="linear travel distance in meters for floor_baseline fwd/bwd segments (default 0.25)")
        parser.add_argument("--floor-spin-rate", type=float, default=1.5, help="angular.z speed for floor_baseline spin segments (rad/s)")
        parser.add_argument("--floor-spin-rotations", type=float, default=1.0, help="number of full rotations per spin step in floor_baseline (default 1)")
        parser.add_argument("--turn-max-time", type=float, default=120.0, help="safety timeout for one-turn test")
        parser.add_argument(
            "--no-encoder-reset",
            action="store_true",
            help="do not send 'r' to zero the encoder counters before one_turn",
        )
        return parser.parse_args()


def main():
    args = DriveSequenceRunner.parse_args()
    _kill_stale_motion_publishers()
    rclpy.init()
    node = DriveSequenceRunner(args)

    def handle_signal(signum, frame):
        del signum, frame
        node.interrupted = True
        node.done = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        node.force_stop()
        node.close()
        summary = node.summary
        linear_ratio = (
            summary["max_abs_raw_vx"] / summary["max_abs_cmd_vx"]
            if summary["max_abs_cmd_vx"] > 0.0
            else None
        )
        angular_ratio = (
            summary["max_abs_raw_wz"] / summary["max_abs_cmd_wz"]
            if summary["max_abs_cmd_wz"] > 0.0
            else None
        )
        linear_ratio_str = f"{linear_ratio:.3f}" if linear_ratio is not None else "n/a"
        angular_ratio_str = f"{angular_ratio:.3f}" if angular_ratio is not None else "n/a"
        enc_ratio_l = (
            summary["max_abs_enc_act_l"] / summary["max_abs_cmd_wheel_l"]
            if summary["max_abs_cmd_wheel_l"] > 0.0
            else None
        )
        enc_ratio_r = (
            summary["max_abs_enc_act_r"] / summary["max_abs_cmd_wheel_r"]
            if summary["max_abs_cmd_wheel_r"] > 0.0
            else None
        )
        enc_ratio_l_str = f"{enc_ratio_l:.3f}" if enc_ratio_l is not None else "n/a"
        enc_ratio_r_str = f"{enc_ratio_r:.3f}" if enc_ratio_r is not None else "n/a"
        ang_err_samples = node._ang_err_samples
        ang_agreement_str = (
            f"{sum(ang_err_samples)/len(ang_err_samples):.3f}"
            if ang_err_samples
            else "n/a"
        )
        print(
            "summary | "
            f"min_battery={summary['min_battery_v']}V "
            f"max_current={summary['max_current_a']}A "
            f"max_power={summary['max_power_w']:.2f}W "
            f"cmd|vx|={summary['max_abs_cmd_vx']:.3f} "
            f"cmd|wz|={summary['max_abs_cmd_wz']:.3f} "
            f"max|raw_vx|={summary['max_abs_raw_vx']:.3f} "
            f"max|raw_wz|={summary['max_abs_raw_wz']:.3f} "
            f"max|ekf_vx|={summary['max_abs_ekf_vx']:.3f} "
            f"max|ekf_wz|={summary['max_abs_ekf_wz']:.3f} "
            f"raw_ratio(vx)={linear_ratio_str} "
            f"raw_ratio(wz)={angular_ratio_str} "
            f"cmd_wheel|max|={summary['max_abs_cmd_wheel_l']:.3f}/{summary['max_abs_cmd_wheel_r']:.3f} "
            f"enc_max|cnt|={summary['max_abs_enc_cnt_l']}/{summary['max_abs_enc_cnt_r']} "
            f"enc_max|act|={summary['max_abs_enc_act_l']:.3f}/{summary['max_abs_enc_act_r']:.3f} "
            f"turn_goal_cnt={summary['turn_goal_cnt']} "
            f"bridge_cmd_count={summary['bridge_cmd_count']} "
            f"bridge_cmd_max_gap_s={summary['bridge_cmd_max_gap_s']:.3f} "
            f"enc_ratio={enc_ratio_l_str}/{enc_ratio_r_str} "
            f"imu_enc_ang_err_avg={ang_agreement_str}",
            flush=True,
        )
        if node._step_imu_results:
            print("imu_per_step |", flush=True)
            for r in node._step_imu_results:
                if r["is_spin"]:
                    overshoot = r["gyro_deg"] - r["expected_deg"]
                    print(
                        f"  {r['label']:<14}  gyro_total={r['gyro_deg']:+.1f}°  "
                        f"expected={r['expected_deg']:+.0f}°  overshoot={overshoot:+.1f}°  "
                        f"yaw_net={r['yaw_delta']:+.1f}°",
                        flush=True,
                    )
                else:
                    direction = "CURVED RIGHT" if r["gyro_deg"] < -5 else "CURVED LEFT" if r["gyro_deg"] > 5 else "straight"
                    print(
                        f"  {r['label']:<14}  heading_drift={r['gyro_deg']:+.1f}°  ({direction})",
                        flush=True,
                    )
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
