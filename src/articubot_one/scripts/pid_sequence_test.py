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
import re
import socket
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


DEFAULT_LOG = Path("/home/ryan/dev_ws/pid_sequence_log.csv")
WHEEL_RADIUS = 0.034
WHEEL_SEP = 0.179
ENC_LINE_RE = re.compile(
    r"\[enc\]\s+(?:cnt=(?P<cnt_l>-?\d+)/(?P<cnt_r>-?\d+)\s+)?"
    r"tgt=(?P<tgt_l>-?\d+(?:\.\d+)?)/(?P<tgt_r>-?\d+(?:\.\d+)?)\s+"
    r"act=(?P<act_l>-?\d+(?:\.\d+)?)/(?P<act_r>-?\d+(?:\.\d+)?)\s+"
    r"filt=(?P<filt_l>-?\d+(?:\.\d+)?)/(?P<filt_r>-?\d+(?:\.\d+)?)"
)


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    linear: float
    angular: float
    duration: float
    stop_hold: float


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
        self.steps = self._build_steps(args)
        self.repeats_left = max(1, args.repeats)
        self.sequence_index = 0
        self.phase = "warmup"
        self.phase_started = time.monotonic()
        self.current_step = self.steps[0]
        self.done = False
        self.interrupted = False

        self.latest_battery = None
        self.latest_imu = None
        self.latest_raw = None
        self.latest_ekf = None
        self.latest_enc = None
        self.latest_enc_counts = None
        self.latest_cmd = make_twist(0.0, 0.0)
        self._state_lock = threading.Lock()
        self._enc_stop = threading.Event()
        self._turn_started_at = None

        self.pub = self.create_publisher(Twist, args.command_topic, 10)
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
        }
        self._enc_thread = threading.Thread(target=self._enc_monitor_loop, daemon=True)
        self._enc_thread.start()
        if args.profile == "one_turn" and not args.no_encoder_reset:
            self._send_encoder_reset()

        self.log_path = Path(args.output).expanduser()
        self.log_file = self.log_path.open("w", newline="")
        self.writer = csv.writer(self.log_file)
        self.writer.writerow(
            [
                "wall_time",
                "elapsed_s",
                "run",
                "step_index",
                "phase",
                "key",
                "label",
                "cmd_lin",
                "cmd_ang",
                "battery_v",
                "current_a",
                "power_w",
                "raw_vx",
                "raw_wz",
                "ekf_vx",
                "ekf_wz",
                "imu_yaw_deg",
                "imu_gyro_z",
                "imu_accel_x",
                "cmd_wheel_l",
                "cmd_wheel_r",
                "enc_cnt_l",
                "enc_cnt_r",
                "enc_act_l",
                "enc_act_r",
                "enc_filt_l",
                "enc_filt_r",
            ]
        )

        self.get_logger().info(
            f"logging to {self.log_path} | profile={args.profile or 'custom'} | repeats={self.repeats_left} | warmup={self.warmup_seconds}s"
        )

    def _build_steps(self, args):
        if args.sequence:
            return parse_sequence(args.sequence, args.duration, args.stop_hold)
        if args.profile == "one_turn":
            return [
                Step(
                    key="i",
                    label="one_turn",
                    linear=args.turn_linear,
                    angular=0.0,
                    duration=args.turn_max_time,
                    stop_hold=args.stop_hold,
                )
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
            self.latest_enc = sample
            if sample.get("cnt_l") is not None and sample.get("cnt_r") is not None:
                self.latest_enc_counts = sample
                self.summary["max_abs_enc_cnt_l"] = max(self.summary["max_abs_enc_cnt_l"], abs(int(sample["cnt_l"])))
                self.summary["max_abs_enc_cnt_r"] = max(self.summary["max_abs_enc_cnt_r"], abs(int(sample["cnt_r"])))
            if hasattr(self, "summary"):
                self.summary["max_abs_enc_act_l"] = max(self.summary["max_abs_enc_act_l"], abs(sample["act_l"]))
                self.summary["max_abs_enc_act_r"] = max(self.summary["max_abs_enc_act_r"], abs(sample["act_r"]))
                self.summary["max_abs_enc_filt_l"] = max(self.summary["max_abs_enc_filt_l"], abs(sample["filt_l"]))
                self.summary["max_abs_enc_filt_r"] = max(self.summary["max_abs_enc_filt_r"], abs(sample["filt_r"]))

    def _send_encoder_reset(self):
        host = self.args.encoder_host
        port = self.args.encoder_port
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
            except Exception as exc:
                self.get_logger().warn(f"encoder monitor offline: {exc}")
                if self._enc_stop.wait(2.0):
                    break

    def _current_cmd(self):
        if self.phase == "active":
            return self.current_step.linear, self.current_step.angular
        return 0.0, 0.0

    def _step_done(self):
        if self.args.profile == "one_turn" and self.phase == "active":
            with self._state_lock:
                enc = self.latest_enc_counts or {}
            if enc:
                left = abs(int(enc.get("cnt_l", 0)))
                right = abs(int(enc.get("cnt_r", 0)))
                target = self.args.turn_target_counts
                if self._turn_started_at is None:
                    self._turn_started_at = time.monotonic()
                if self.args.turn_wheel == "left":
                    if left >= target:
                        return True
                elif self.args.turn_wheel == "right":
                    if right >= target:
                        return True
                else:
                    if min(left, right) >= target:
                        return True
                if (time.monotonic() - self._turn_started_at) >= self.args.turn_max_time:
                    self.get_logger().warn("one_turn timeout reached before target count")
                    return True
        if self.phase == "warmup":
            return (time.monotonic() - self.phase_started) >= self.warmup_seconds
        return (time.monotonic() - self.phase_started) >= (
            self.current_step.duration if self.phase == "active" else self.current_step.stop_hold
        )

    def _advance(self):
        if self.phase == "warmup":
            self.phase = "active"
            self.phase_started = time.monotonic()
            return

        if self.phase == "active":
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
        self.phase = "active"
        self.phase_started = time.monotonic()

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

        battery_v = current_a = ""
        power_w = ""
        if self.latest_battery is not None:
            battery_v = self.latest_battery.voltage
            current_a = self.latest_battery.current
            power_w = battery_v * current_a
            self.summary["max_power_w"] = max(self.summary["max_power_w"], power_w)

        raw_vx, raw_wz = twist_values(self.latest_raw)
        ekf_vx, ekf_wz = twist_values(self.latest_ekf)
        imu_yaw = imu_gyro_z = imu_accel_x = ""
        if self.latest_imu is not None:
            imu_yaw = yaw_from_quaternion(self.latest_imu.orientation)
            imu_gyro_z = self.latest_imu.angular_velocity.z
            imu_accel_x = self.latest_imu.linear_acceleration.x
        with self._state_lock:
            enc = self.latest_enc or {}

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
                cmd_wheel_l,
                cmd_wheel_r,
                enc.get("cnt_l", ""),
                enc.get("cnt_r", ""),
                enc.get("act_l", ""),
                enc.get("act_r", ""),
                enc.get("filt_l", ""),
                enc.get("filt_r", ""),
            ]
        )
        self.log_file.flush()

    def force_stop(self, duration=0.6):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.pub.publish(make_twist(0.0, 0.0))
            time.sleep(0.1)

    def close(self):
        self._enc_stop.set()
        self.log_file.close()

    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--profile",
            default="rebound",
            choices=["rebound", "power", "straight", "turns", "one_turn"],
            help="predefined teleop-style sequence",
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
            default="/cmd_vel_raw",
            help="topic to publish commands on (default matches the active teleop path)",
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
        parser.add_argument("--log-rate", type=float, default=4.0, help="CSV sample rate")
        parser.add_argument("--output", default=str(DEFAULT_LOG), help="CSV output file")
        parser.add_argument(
            "--turn-wheel",
            default="both",
            choices=["left", "right", "both"],
            help="which wheel counts toward the one-turn stop condition",
        )
        parser.add_argument("--turn-target-counts", type=int, default=1010, help="encoder counts required to stop")
        parser.add_argument("--turn-linear", type=float, default=0.20, help="linear command during one-turn test")
        parser.add_argument("--turn-max-time", type=float, default=10.0, help="safety timeout for one-turn test")
        parser.add_argument(
            "--no-encoder-reset",
            action="store_true",
            help="do not send 'r' to zero the encoder counters before one_turn",
        )
        return parser.parse_args()


def main():
    args = DriveSequenceRunner.parse_args()
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
            f"enc_ratio={enc_ratio_l_str}/{enc_ratio_r_str}",
            flush=True,
        )
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
