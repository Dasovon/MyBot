# Development Workflow

## Preferred Setup: Dev Machine → Pi

All development happens on the **dev machine** (`dev`, 192.168.86.52, `~/dev_ws`).
The Pi (`mybot`, 192.168.86.33, `~/mybot_ws`) is a hardware worker — never develop directly on it.

Claude Code runs on dev. It reaches the Pi via `ssh ryan@mybot "..."`.

### What runs where

| Component | Machine | Launch |
|---|---|---|
| micro_ros_agent (ESP32 bridge) | Pi | `mybot-launch` |
| RPLidar, RealSense | Pi | `mybot-launch` |
| EKF (robot_localization) | Dev | `dev_launch.py` |
| Nav2 (AMCL, planner, controller) | Dev | `navigation_launch.py` |
| Ball tracker / OpenCV | Dev | `ball_tracker.launch.py` |
| RViz2 | Dev | `rviz2` |

> BNO055 IMU and INA219 are handled entirely by the ESP32-S3 over micro-ROS — no Pi-side sensor nodes needed.

### Full launch sequence

```bash
# 1. Pi — hardware (via SSH from dev, or use mybot-launch alias on Pi directly)
ssh ryan@mybot "source ~/mybot_ws/install/setup.bash && mybot-launch"

# 2. Dev — EKF
source ~/dev_ws/install/setup.bash && ros2 launch articubot_one dev_launch.py

# 3. Dev — localization
ros2 launch articubot_one localization_launch.py

# 4. Dev — Nav2
ros2 launch articubot_one navigation_launch.py

# 5. Dev — ball tracker (optional)
ros2 launch articubot_one ball_tracker.launch.py

# 6. Dev — RViz2
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

> **Warning:** Always kill ball_tracker before closing its tuning window — `follow_ball` keeps sending velocity commands after the window closes.

---

## End-of-Session Routine

Run this at the end of every session. Claude Code can execute it on your behalf.

### 1. Stop all ROS processes

```bash
# Dev — kill local nodes
pkill -f "ros2 launch\|detect_ball\|follow_ball\|ekf_filter\|nav2\|amcl\|map_server" 2>/dev/null

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
└── ball_tracker/           ← joshnewans ball tracker (dev-side only)

~/mybot_ws/src/             ← Pi workspace (mirrors above via git pull)
├── articubot_one/
├── diffdrive_arduino/      ← branch: humble
└── serial/                 ← branch: newans_ros2
```

## ESP32-S3 micro-ROS Stack (production)

ESP32-S3 handles motors, encoders, BNO055 IMU, and INA219 power monitor. Pi runs `micro_ros_agent` as the bridge. EKF, Nav2, AMCL are unchanged and run on dev.

**`mybot-launch` already starts the agent.** To run it manually on Pi:
```bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0
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
