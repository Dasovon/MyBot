# Development Workflow

## Preferred Setup: Dev Machine → Pi

All development happens on the **dev machine** (`dev`, 192.168.86.52, `~/dev_ws`).
The Pi (`mybot`, 192.168.86.33, `~/mybot_ws`) is a hardware worker — never develop directly on it.

Claude Code runs on dev. It reaches the Pi via `ssh ryan@mybot "..."`.

### What runs where

| Component | Machine | Launch |
|---|---|---|
| micro_ros_agent (ESP32 bridge) | Pi | `robot-launch.service` / `mybot-launch` |
| RPLidar, RealSense | Pi | optional launch args in `launch_robot.launch.py` |
| EKF (robot_localization) | Dev | `dev_launch.py` |
| Nav2 (AMCL, planner, controller) | Dev | `navigation_launch.py` |
| RViz2 | Dev | `rviz2` |

> BNO055 IMU and INA219 are handled entirely by the ESP32-S3 over micro-ROS — no Pi-side sensor nodes needed.
> Current Pi launch path is `twist_mux -> /cmd_vel_raw -> vel_smoother.py -> /diff_cont/cmd_vel_unstamped`.
> Camera and lidar are opt-in launch args so unplugged hardware does not take down the robot stack.
> Motion tests require `enable_motion:=true`; otherwise the launch file keeps the drive path disabled and the bridge runner will time out at zero.
> Low-level PID tuning runs on the ESP32 bench firmware in `src/esp32_microros/test/test_pid_bench`; the dev machine captures the logs.
> The OLED battery path is direct from the ESP32, but the display layout is still being refined.
> The Pi-to-ESP32 communication path still has open cleanup work; keep that separate from OLED layout work.

### Full launch sequence

```bash
# 1. Pi — hardware (via SSH from dev, or let robot-launch.service start automatically)
ssh ryan@mybot "source ~/mybot_ws/install/setup.bash && mybot-launch"

# 2. Dev — EKF
source ~/dev_ws/install/setup.bash && ros2 launch articubot_one dev_launch.py

# 3. Dev — localization
ros2 launch articubot_one localization_launch.py

# 4. Dev — Nav2
ros2 launch articubot_one navigation_launch.py

# 5. Dev — RViz2
rviz2
```

### Emergency stop

```bash
# Send zero velocity (continuous pub — --once latches in twist_mux and won't stop the robot)
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.0}}" -r 10 &
SPID=$!; sleep 2; kill $SPID; wait $SPID 2>/dev/null

# Hard stop — kill micro_ros_agent on Pi; ESP32 detects loss in ~2s and calls motors_stop()
ssh ryan@192.168.86.33 "ps aux | grep micro_ros | grep -v grep | awk '{print \$2}' | xargs kill -9"
```

> **Warning:** Always use `-r 10` continuous publishers for velocity commands. `--once` latches the command in twist_mux — the robot keeps moving until a new message overrides it. Check publisher count with `ros2 topic info /cmd_vel`.

---

### Pi–ESP32 bridge troubleshooting

**Symptom: robot doesn't respond to commands (topics look connected but no motion)**

This happens in two scenarios:

**A. Stuck micro_ros_agent** (after OTA flash or ESP32 30s-watchdog reset):
Ping succeeds at serial level but the DDS bridge is confused — topics are advertised
but no data flows. `ros2 topic hz /diff_cont/odom` will show 0 Hz.

Fix:
```bash
ssh ryan@mybot "sudo systemctl restart robot-launch.service"
# May need 2–3 attempts after an OTA flash
```

Verify bridge is healthy:
```bash
ros2 topic hz /diff_cont/odom   # expect ~30 Hz
ros2 topic hz /imu/imu          # expect ~30 Hz
```

**B. vel_smoother ↔ twist_mux SHM discovery failure** (after service restart without SHM cleanup):
`ros2 topic info /cmd_vel_raw` shows 1 publisher (twist_mux) and 1 subscriber (vel_smoother),
but vel_smoother outputs only zeros regardless of teleop input.

Fix: ensure `robot-launch.service` ExecStartPre includes `rm -f /dev/shm/fastrtps_*`
(see `docs/pi-setup.md` §16 for the correct template). Then restart the service.

**Symptom: ESP32 accepts zero command (arms) but ignores nonzero commands**

The ESP32 boot-arming guard requires an explicit zero command before accepting motion.
`vel_smoother.py` publishes zero at 50 Hz when idle — the ESP32 should arm within 20ms
of vel_smoother starting. If it doesn't:

1. Check `ros2 topic echo /diff_cont/cmd_vel_unstamped` — if it shows nothing, the bridge is stuck (scenario A above).
2. Check `ros2 topic info /diff_cont/cmd_vel_unstamped` — if ESP32 subscription is listed, bridge is ok; if missing, micro_ros_agent hasn't connected.

### Recurring Failure Policy

If the same failure keeps returning, promote the fix into the repo instead of
leaving it as a manual workaround.

- Update code when the root cause is code-level.
- Update launch or service config when the failure depends on startup order or
  process ownership.
- Update `CLAUDE.md` and the relevant docs in the same change so the next session
  starts from the fixed state.
- Do not keep repeating the same stopgap in chat; once a fix is real, make it
  permanent.

**Before rebooting the Pi, always stop dev-side ROS nodes:**
```bash
pkill -f "ros2 launch\|ros2 run\|rviz2\|nav2\|amcl"
```
Stale teleop publishers on the dev machine can deliver commands via DDS as soon as the
Pi bridge comes back up, bypassing the ESP32 arming guard.

---

## End-of-Session Routine

Run this at the end of every session. Claude Code can execute it on your behalf.

### 1. Stop all ROS processes

```bash
# Dev — kill local nodes
pkill -f "ros2 launch\|ekf_filter\|nav2\|amcl\|map_server" 2>/dev/null

# Pi — kill hardware nodes
ssh ryan@mybot "sudo pkill -f 'ros2 launch\|micro_ros_agent\|rplidar\|realsense2_camera' 2>/dev/null"
```

### 2. Update CLAUDE.md (on dev)

Edit `CLAUDE.md` to reflect:
- Current status (what works, what's broken)
- Any new fix history entries
- Next steps
- Tutorial progress changes

### 3. Update hardware docs (if hardware changed)

Update or create files in `docs/`:
- `docs/realsense-rsusb-setup.md`
- `docs/pin-mapping.md`
- `docs/wire-colors.md`
- `docs/workflow.md` (this file)

### 4. Commit and push from dev

```bash
cd ~/dev_ws/src/articubot_one
git add -p   # review changes
git commit -m "Session summary: <what was done>"
git push
```

### 5. Sync Pi

```bash
ssh ryan@mybot "cd ~/mybot_ws/src/articubot_one && git pull"
```

### 6. Update memory files (Claude does this)

Memory files live at:
- Dev: `/home/ryan/.claude/projects/-home-ryan-dev-ws/memory/`
- Pi: `/home/ryan/.claude/projects/-home-ryan-mybot-ws/memory/`

---

## Repo Layout (dev_ws perspective)

```
~/dev_ws/src/
├── articubot_one/          ← main package, branch: main
│   ├── launch/             ← all launch files
│   ├── config/             ← nav2, ekf, controller, slam params
│   ├── description/        ← URDF/xacro
│   └── docs/               ← this file and hardware docs
~/mybot_ws/src/             ← Pi workspace (mirrors above via git pull)
├── articubot_one/
├── diffdrive_arduino/      ← branch: humble
└── serial/                 ← branch: newans_ros2
```

## ESP32-S3 micro-ROS Stack (production)

ESP32-S3 handles motors, encoders, BNO055 IMU, and INA219 power monitor. Pi runs `micro_ros_agent` as the bridge for integration runs; motion is opt-in and stays disabled on boot unless `enable_motion:=true` is passed. The OLED service reads battery telemetry directly from the ESP32 Telnet stream and does not depend on the ROS battery topic. EKF, Nav2, AMCL are unchanged and run on dev.

**`mybot-launch` already starts the agent.** To run it manually on Pi:
```bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00
```

**OTA firmware flash (from dev):**
```bash
cd ~/dev_ws/src/articubot_one/src/esp32_microros
pio run -e esp32-s3-ota --target upload
```

**Wireless serial monitor:**
```bash
nc esp32-mybot.local 23
```

**Verify topics are live:**
```bash
ros2 topic hz /diff_cont/odom       # expect ~30 Hz
ros2 topic hz /imu/imu              # expect ~30 Hz
ros2 topic echo /battery_state
```

See `docs/pin-mapping.md` for full ESP32 wiring table.

---

## Pi-only setup (not in git)

These changes live only on the Pi and must be re-applied if Pi is reimaged:

| What | Where |
|---|---|
| librealsense RSUSB build | `/usr/local/lib/librealsense2.so.2.56.4` |
| librealsense .so replacement | `/opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4` |
| librealsense source | `~/librealsense` (tag v2.56.4) |
| udev rules | `/etc/udev/rules.d/99-mybot.rules`, `99-realsense-libusb.rules` |
| mybot-launch alias | `~/.bashrc` |
| passwordless sudo | `/etc/sudoers.d/ryan-nopasswd` |
