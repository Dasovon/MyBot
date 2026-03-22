# Development Workflow

## Preferred Setup: Dev Machine → Pi

All development happens on the **dev machine** (`dev`, 192.168.86.52, `~/dev_ws`).
The Pi (`mybot`, 192.168.86.33, `~/mybot_ws`) is a hardware worker — never develop directly on it.

Claude Code runs on dev. It reaches the Pi via `ssh ryan@mybot "..."`.

### What runs where

| Component | Machine | Launch |
|---|---|---|
| ros2_control, motors, encoders | Pi | `mybot-launch` |
| RPLidar, BNO055 IMU, RealSense | Pi | `mybot-launch` |
| EKF (robot_localization) | Dev | `dev_launch.py` |
| Nav2 (AMCL, planner, controller) | Dev | `navigation_launch.py` |
| Ball tracker / OpenCV | Dev | `ball_tracker.launch.py` |
| RViz2 | Dev | `rviz2` |

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
# Send zero velocity
source /opt/ros/humble/setup.bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'

# If ros2_control is down, stop Arduino directly via serial (on Pi)
ssh ryan@mybot "python3 -c \"import serial,time; s=serial.Serial('/dev/arduino',57600,timeout=1); s.write(b'm 0 0\r'); time.sleep(0.2); s.close()\""
```

> **Warning:** Always kill ball_tracker before closing its tuning window — `follow_ball` keeps sending velocity commands after the window closes.

---

## End-of-Session Routine

Run this at the end of every session. Claude Code can execute it on your behalf.

### 1. Stop all ROS processes

```bash
# Dev — kill local nodes
pkill -f "ros2 launch\|detect_ball\|follow_ball\|ekf_filter\|nav2\|amcl\|map_server" 2>/dev/null

# Pi — kill hardware nodes
ssh ryan@mybot "sudo pkill -f 'ros2 launch\|ros2_control_node\|rplidar\|bno055\|realsense2_camera' 2>/dev/null"
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
