# CLAUDE.md

## Project Goal
ROS 2 Humble differential drive robot stack for a Raspberry Pi + Arduino robot using `ros2_control`, `diffdrive_arduino`, and serial motor/encoder communication.

## Environment Note
This repo runs on two machines. Claude Code is installed on both. Know which machine you are on:

- **Pi** (`mybot`, 192.168.86.33): working directory `~/mybot_ws`. Run hardware commands directly.
- **Dev** (`192.168.86.52`): working directory `~/dev_ws`. SSH to Pi for hardware: `ssh ryan@mybot "<command>"`. Pi's hostname `mybot` resolves via mDNS — prefer `mybot` over IP.

When on **dev**, use SSH for any Pi operations (launch robot, check serial, reflash Arduino, reboot, etc). Run ROS commands for dev-side nodes (EKF, Nav2, RViz) locally.

## Tech Stack
- Ubuntu 22.04 LTS
- ROS 2 Humble
- Python 3
- CMake + `ament_cmake`
- `xacro` / URDF
- `ros2_control`
- `controller_manager`
- `diff_drive_controller`
- `joint_state_broadcaster`
- `twist_mux`
- `robot_state_publisher`
- `pluginlib`
- `rclcpp`
- `rclcpp_lifecycle`
- `libserial-dev`
- Gazebo support via `gazebo_ros2_control`
- Navigation / perception assets present in package:
  - Nav2 launch/config files
  - RPLidar launch
  - camera launch
  - ball tracker launch

## Active Repos / Branches
- `src/articubot_one` → branch `main`
- `src/diffdrive_arduino` → branch `humble`
- `src/serial` → branch `newans_ros2`
- `src/ros_arduino_bridge` → branch `main` but **legacy / abandoned for runtime architecture**

## Directory Structure
```text
mybot_ws/
├── src/
│   ├── articubot_one/
│   │   ├── launch/
│   │   ├── config/
│   │   ├── description/
│   │   └── worlds/
│   ├── diffdrive_arduino/
│   │   ├── hardware/
│   │   ├── bringup/
│   │   ├── description/
│   │   └── doc/
│   ├── serial/
│   │   ├── include/
│   │   ├── src/
│   │   ├── tests/
│   │   └── examples/
│   └── ros_arduino_bridge/
│       └── ROSArduinoBridge/
├── build/
├── install/
└── log/
```

## Key Runtime Architecture
```text
Dev machine
  ⇅ network

Raspberry Pi
  ├── ROS 2 Humble
  ├── articubot_one launch files
  ├── robot_state_publisher
  ├── ros2_control_node
  ├── diff_drive_controller
  └── twist_mux

USB serial: /dev/ttyUSB0 @ 57600

Arduino motor controller
  ├── closed loop motor commands
  └── encoder feedback

Motor driver / drivetrain
  └── differential drive base
```

## Dev / Pi Split Architecture
```
Pi (mybot, 192.168.86.33) — ~/mybot_ws
  Runs: hardware drivers only
  ├── robot_state_publisher
  ├── ros2_control_node + diff_cont + joint_broad
  ├── twist_mux
  ├── rplidar_composition  (/dev/rplidar)
  ├── bno055               (I2C bus 1, 0x28)
  └── realsense2_camera_node (/camera/camera/*)

Dev (192.168.86.52) — ~/dev_ws
  Runs: computation + navigation
  ├── ekf_filter_node      (fuses /diff_cont/odom + /imu/imu → /odom)
  ├── map_server + amcl    (localization_launch.py)
  ├── Nav2 stack           (navigation_launch.py)
  ├── rviz2
  └── future: OpenCV / object tracking
```

### Launch Sequence (full stack)
```bash
# Pi
ssh ryan@mybot "source ~/mybot_ws/install/setup.bash && ros2 launch articubot_one launch_robot.launch.py"

# Dev — Terminal 1
ros2 launch articubot_one dev_launch.py

# Dev — Terminal 2
ros2 launch articubot_one localization_launch.py

# Dev — Terminal 3
ros2 launch articubot_one navigation_launch.py

# Dev — Terminal 4
rviz2
```

### Dev Workspace Setup
```bash
mkdir -p ~/dev_ws/src && cd ~/dev_ws/src
git clone git@github.com:Dasovon/MyBot.git articubot_one
cd ~/dev_ws
sudo apt install -y ros-humble-robot-localization ros-humble-navigation2 \
  ros-humble-nav2-bringup ros-humble-realsense2-camera-msgs ros-humble-realsense2-description
source /opt/ros/humble/setup.bash
colcon build --symlink-install
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
echo "source ~/dev_ws/install/setup.bash" >> ~/.bashrc
echo "export ROS_DOMAIN_ID=0" >> ~/.bashrc
```

## Key Config Values
From `src/articubot_one/description/ros2_control.xacro`:
- hardware plugin: `diffdrive_arduino/DiffDriveArduinoHardware`
- left wheel joint: `left_wheel_joint`
- right wheel joint: `right_wheel_joint`
- loop rate: `30`
- serial device: `/dev/arduino` (udev symlink → ttyUSB0)
- baud rate: `57600`
- timeout: `1000 ms`
- encoder counts per rev: `1010` (re-validated 2026-03-17 with corrected wheel_radius=0.034; 3 wall-guided runs avg 1011; actual gear ratio is 45:1 not 34:1 — Amazon listing RPM is inaccurate; formula: new = old × reported/actual)

From `src/articubot_one/config/my_controllers.yaml`:
- controller manager update rate: `30`
- diff drive controller name: `diff_cont`
- joint state broadcaster name: `joint_broad`
- wheel separation: `0.179` (179mm center-to-center, measured 2026-03-16)
- wheel radius: `0.034` (68mm diameter, new JGA25-371 motors — wider than CAD drawing)
- `use_stamped_vel: false`
- command remap target: `/diff_cont/cmd_vel_unstamped`
- linear acceleration limit: `0.5 m/s²`
- angular acceleration limit: `1.0 rad/s²`

## Coding Conventions
- ROS package build type is `ament_cmake`.
- Launch and config layout follows standard ROS 2 package conventions.
- Xacro and YAML define robot hardware behavior; do not move constants into random code paths.
- Keep runtime names exact:
  - controller names
  - joint names
  - plugin class names
  - serial device path
- Package is tutorial-derived and still contains template residue. Prefer surgical edits over broad cleanup.
- Test/lint hooks exist but are minimal:
  - `articubot_one` uses `ament_lint_auto` and `ament_lint_common`
  - `serial` uses `ament_cmake_gtest`
  - `diffdrive_arduino` uses `ament_cmake_gtest`
- No evidence of strict TDD in active project workflow.
- Naming style is ROS-standard snake_case for files, launch files, parameters, and controller names.

## Critical Rules
- Never use the old plugin string:
  - wrong: `diffdrive_arduino/DiffDriveArduino`
  - correct: `diffdrive_arduino/DiffDriveArduinoHardware`
- Never mix incompatible repo states:
  - `diffdrive_arduino` must stay on branch `humble`
  - `serial` must stay on branch `newans_ros2`
- Never assume `ros_arduino_bridge` is part of the active ROS 2 runtime path. It is kept in the workspace, but the working architecture is:
  - `ros2_control -> diffdrive_arduino -> serial`
- Never skip a true clean rebuild after changing plugin packages, branches, or manifests:
  - `rm -rf build install log`
- Never trust stale overlay paths in `AMENT_PREFIX_PATH` or `CMAKE_PREFIX_PATH`.
- Never rename controller, joint, or plugin identifiers casually. ROS is extremely literal.
- Never change serial device, baud, motor polarity, and encoder mapping all at once during debugging.
- Never treat tutorial comments as truth. Verify against current files.

## End-of-Session Rule
At the end of every session, Claude must update:
1. `CLAUDE.md` — current status, fix history, tutorial progress, next steps
2. All memory files in `/home/ryan/.claude/projects/-home-ryan-mybot-ws/memory/`
3. Any hardware docs in `docs/` if hardware was changed

This applies even if the session ended without completing the task.

---

## Current Status (2026-03-21)
- Motors swapped to DC12V 130RPM Amazon JGA25-371 encoder gear motors (actual ratio 45:1)
- `enc_counts_per_rev = 1010` — re-validated 2026-03-17 with corrected wheel_radius=0.034 (3 wall-guided runs avg: 1006/1016/1012)
- Both encoders confirmed positive for forward rotation — no inversion needed
- URDF updated to actual robot dimensions (robot_core.xacro, lidar.xacro, my_controllers.yaml)
- wheel_separation corrected from 0.297 → 0.179m (old value was wider than entire robot)
- wheel_radius corrected from 0.0325 → 0.034m (measured 68mm, datasheet says 65mm)
- RPLidar A1 M8 installed and scanning — ros-humble-rplidar-ros installed, /dev/rplidar udev symlink active
- Robot model orientation fixed — chassis was rendered backwards; fixed with 180° chassis_joint rotation
- face.xacro disabled — tutorial-era visual removed
- Dev machine (192.168.86.52) communicates with Pi (192.168.86.33) via ROS 2 DDS on `ROS_DOMAIN_ID=0`
- SLAM complete — new map made 2026-03-21, saved to `~/mybot_ws/maps/my_map` (.pgm + .yaml), 113x140 @ 0.05m/pix; see fix #16 for SLAM drift tuning
- BNO055 IMU fully integrated (2026-03-18) — ros-humble-bno055 installed, I2C bus 1, address 0x28, publishing /imu/imu
- robot_localization EKF running — fuses /diff_cont/odom + /imu/imu → /odom at 20Hz
- imu_link added to URDF at xyz="0.004 -0.018 0.055" (80mm from front, 50mm from right edge, upper deck)
- Nav2 launch files and params updated to Humble-compatible API (2026-03-20) — see fix #15
- Nav2 working end-to-end (2026-03-21) — robot navigates autonomously to goals; see fix #17 for velocity increase
- RealSense D435 partially integrated (2026-03-21) — apt packages installed, udev rules added, depth stream working; color stream broken (Pi kernel UVC driver doesn't support D435 extension units needed for intrinsics)
- Next steps: Build librealsense from source with FORCE_RSUSB_BACKEND=ON to fix color stream (fix #18 — in progress)

### Previous validated state (2026-03-13)
- All 7 differential drive validation checkpoints passed with old E-S Motor 34:1 units
- Teleop working via `ros2 run teleop_twist_keyboard teleop_twist_keyboard`

## Exact Fix History That Matters
### 1) Hardware plugin class fix
File:
`src/articubot_one/description/ros2_control.xacro`

Old:
```xml
<plugin>diffdrive_arduino/DiffDriveArduino</plugin>
```

New:
```xml
<plugin>diffdrive_arduino/DiffDriveArduinoHardware</plugin>
```

### 2) Re-clone correct paired branches
```bash
cd ~/mybot_ws/src
rm -rf diffdrive_arduino serial
git clone -b humble https://github.com/joshnewans/diffdrive_arduino.git
git clone -b newans_ros2 https://github.com/joshnewans/serial.git
```

### 3) Stop using `ros_arduino_bridge`
Reason:
- ROS1-era design
- not needed for working ROS 2 Humble hardware path
- replaced by `ros2_control -> diffdrive_arduino -> serial`

### 7) Encoder count and direction fixes (2026-03-13)
Files changed:
- `src/articubot_one/description/ros2_control.xacro` — `enc_counts_per_rev` corrected from 3436 to 748
  - Motor: E-S Motor 25SG-370CA-34-EN, 11 PPR encoder, 34:1 gear ratio
  - Firmware uses 2x quadrature → 11 × 2 × 34 = 748 counts/rev (verified by hand-rotation)
- `src/ros_arduino_bridge/ROSArduinoBridge/encoder_driver.ino` — right encoder ISR direction inverted
  - Was: `if (A == B) pos++` → right wheel counted negative for forward rotation
  - Fixed: `if (A != B) pos++` → both wheels now count positive for forward rotation
  - Reflashed Arduino after fix

### 18) RealSense D435 — librealsense source build with FORCE_RSUSB_BACKEND (2026-03-21, IN PROGRESS)
Problem: apt-installed `ros-humble-librealsense2` compiled against kernel V4L2/UVC driver. On Pi, UVC extension unit queries (`xioctl(UVCIOC_CTRL_QUERY)`) time out, preventing RGB camera from retrieving intrinsics. Depth stream works; color stream fails with "No intrinsics available".

Decision: Build librealsense from source with `-DFORCE_RSUSB_BACKEND=ON` (uses libusb directly, bypasses kernel UVC driver).

Steps:
1. Remove apt `ros-humble-librealsense2`
2. Install build dependencies: `libusb-1.0-0-dev`, `libssl-dev`, `cmake`, `libgtk-3-dev`
3. Clone `https://github.com/realsenseai/librealsense`
4. Build with `-DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF -DBUILD_GRAPHICAL_EXAMPLES=OFF`
5. Install to system (`sudo make install`)
6. Keep `ros-humble-realsense2-camera` from apt — it will link against the new lib
7. Add udev rule for RSUSB access: `99-realsense-libusb.rules` already installed

Status: Decision made 2026-03-21. Not yet executed.

### 17) Nav2 velocity limits increased (2026-03-21)
File changed:
- `src/articubot_one/config/nav2_params.yaml` — raised max velocity from TurtleBot3 default 0.26 m/s to 0.4 m/s

Changes:
- DWB planner: `max_vel_x: 0.26` → `0.4`, `max_speed_xy: 0.26` → `0.4`
- velocity_smoother: `max_velocity: [0.26, 0.0, 1.0]` → `[0.4, 0.0, 1.0]`, `min_velocity: [-0.26, 0.0, -1.0]` → `[-0.4, 0.0, -1.0]`

Reason: robot was struggling to move at 0.26 m/s — not enough torque to overcome static friction consistently. diff_drive_controller already allows 0.5 m/s; 0.4 gives headroom below that limit.

### 16) SLAM drift tuning (2026-03-21)
File changed:
- `src/articubot_one/config/mapper_params_online_async.yaml`

Changes:
- `minimum_time_interval: 0.5` → `0.3` (more frequent scan matching — was missing too much motion between scans)
- `link_match_minimum_response_fine: 0.1` → `0.3` (reject weaker/ambiguous scan matches)
- `loop_match_minimum_chain_size: 10` → `5` (loop closure kicks in sooner — needed for small rooms)

Result: map drift reduced; new map saved 2026-03-21 at 113x140 @ 0.05m/pix.

### 15) Nav2 launch files and params updated to Humble API (2026-03-20)
Files changed:
- `src/articubot_one/launch/navigation_launch.py` — rewritten to Humble nav2_bringup style: `recoveries_server` → `behavior_server`, added `smoother_server` and `velocity_smoother` to lifecycle nodes, uses `ParameterFile` wrapper
- `src/articubot_one/launch/localization_launch.py` — rewritten to Humble nav2_bringup style: uses `ParameterFile` wrapper, default map path set to `~/mybot_ws/maps/my_map.yaml`
- `src/articubot_one/config/nav2_params.yaml` — fully replaced with Humble-compatible params:
  - `use_sim_time: False` everywhere
  - `robot_model_type: "nav2_amcl::DifferentialMotionModel"` (old `"differential"` deprecated)
  - `robot_radius: 0.17` (our robot ~156mm circumscribed radius, was 0.22 for TurtleBot3)
  - `inflation_radius: 0.35` (reduced from 0.55, fits smaller robot in small rooms)
  - `laser_max_range: 12.0` (RPLidar A1 M8 spec)
  - `recoveries_server` block replaced with `behavior_server` block (nav2_behaviors/*)
  - Added `smoother_server`, `waypoint_follower`, `velocity_smoother` sections
  - Updated bt_navigator plugin list to full Humble set

Nav2 launch sequence:
1. Pi Terminal 1: `mybot-launch`
2. Pi Terminal 2: `source ~/mybot_ws/install/setup.bash && ros2 launch articubot_one localization_launch.py`
3. Pi Terminal 3: `source ~/mybot_ws/install/setup.bash && ros2 launch articubot_one navigation_launch.py`
4. Dev machine: `rviz2` — Fixed Frame: `map`, add Map `/map`, LaserScan `/scan`, RobotModel `/robot_description`
5. Use **2D Pose Estimate** tool to initialize AMCL (click robot location + drag heading)
6. Use **Nav2 Goal** (or Nav2 Goal Pose) to send navigation target

Key notes:
- Localization MUST be running before RViz `map` frame exists
- AMCL will not publish transform until initial pose is set via 2D Pose Estimate
- velocity_smoother remaps internally: nav `cmd_vel_nav` → smoothed → `/cmd_vel` → twist_mux → `/diff_cont/cmd_vel_unstamped`
- Nav2 confirmed receiving all topics from Pi on dev machine (ros2 topic list verified)

### 14) BNO055 IMU + robot_localization EKF integrated (2026-03-18)
Packages installed:
- `ros-humble-bno055` — I2C IMU driver
- `ros-humble-robot-localization` — EKF sensor fusion

Files changed:
- `src/articubot_one/description/robot_core.xacro` — added `imu_link` at xyz="0.004 -0.018 0.055" (80mm from front edge, 50mm from right edge, upper deck)
- `src/articubot_one/config/bno055_params.yaml` — new: I2C bus 1, addr 0x28, topic prefix `imu/`, frame_id `imu_link`, NDOF mode
- `src/articubot_one/config/ekf.yaml` — new: fuses /diff_cont/odom + /imu/imu → /odom at 20Hz, two_d_mode true
- `src/articubot_one/launch/launch_robot.launch.py` — added bno055 and ekf_node; removed old `/diff_cont/odom → /odom` remap (EKF now owns /odom); added `/odometry/filtered → /odom` remap on EKF node

Key notes:
- BNO055 uses I2C not UART — must set `connection_type: i2c` and `i2c_bus: 1` in config
- EKF IMU config: orientation disabled (magnetometer unreliable on metal robot), angular velocity + linear accel enabled
- EKF frequency lowered to 20Hz to avoid overload warnings on Pi
- i2c-tools installed for diagnostics: `sudo i2cdetect -y 1` confirms BNO055 at 0x28

### 13) SLAM with slam_toolbox configured and confirmed working (2026-03-18)
Files changed:
- `src/articubot_one/launch/online_async_launch.py` — `use_sim_time` default changed `true` → `false` (real robot)
- `src/articubot_one/config/mapper_params_online_async.yaml` — `mode: localization` → `mode: mapping`; placeholder `map_file_name` commented out; `max_laser_range: 20.0` → `12.0` (RPLidar A1 M8 spec); `minimum_travel_distance` and `minimum_travel_heading` lowered from `0.5` → `0.2` (reduces drift in small rooms)

Launch sequence:
1. Pi Terminal 1: `mybot-launch`
2. Pi Terminal 2: `source ~/mybot_ws/install/setup.bash && ros2 launch articubot_one online_async_launch.py`
3. Dev machine: `rviz2` — add Map `/map`, LaserScan `/scan`, set Fixed Frame to `map`
4. Drive with teleop to build map
5. Save map: `ros2 run nav2_map_server map_saver_cli -f ~/mybot_ws/maps/my_map`

Key notes:
- Must `source ~/mybot_ws/install/setup.bash` on Pi before launching — Pi also has `robot_ws` which does not have articubot_one
- slam_toolbox is passive — robot must be driven manually with teleop
- BNO055 IMU on hand; plan to integrate with `robot_localization` EKF after map is complete

### 12) RPLidar A1 M8 installed and robot model orientation fixed (2026-03-17)
Files changed:
- `/etc/udev/rules.d/99-mybot.rules` — udev symlinks: `/dev/arduino` (CH340, 1a86:7523) and `/dev/rplidar` (CP2102, 10c4:ea60)
- `src/articubot_one/description/ros2_control.xacro` — device changed from `/dev/ttyUSB0` to `/dev/arduino`
- `src/articubot_one/launch/rplidar.launch.py` — serial_port `/dev/rplidar`, serial_baudrate 115200 added
- `src/articubot_one/launch/launch_robot.launch.py` — rplidar.launch.py included in main launch
- `src/articubot_one/description/robot.urdf.xacro` — face.xacro disabled
- `src/articubot_one/description/robot_core.xacro` — chassis_joint rpy="0 0 pi" added; chassis_joint x changed to `chassis_length - wheel_offset_x`; caster_wheel_offset_x 0.033 → 0.207
- `src/articubot_one/description/lidar.xacro` — origin x 0.200 → 0.040 (40mm from front in flipped chassis frame)
- `~/.bashrc` — `mybot-launch` alias added (clears serial ports before launching)
- `/etc/sudoers.d/ryan-nopasswd` — passwordless sudo for ryan

Key issues resolved:
- rplidar failed with timeout until `serial_baudrate: 115200` was added explicitly
- Stale serial port processes cause crash on restart — use `sudo fuser -k /dev/arduino /dev/rplidar` before launching (or `mybot-launch` alias)
- Robot model was rendered 180° backwards — chassis was oriented with caster side as positive x. Fixed by adding rpy="0 0 pi" to chassis_joint and recalculating caster and lidar offsets

### 11) URDF updated to actual robot dimensions (2026-03-16)
All dimensions measured from physical robot and CAD renders in `Hardware/mybot/`.
Files changed:
- `src/articubot_one/description/robot_core.xacro` — chassis, wheel, and caster dimensions updated to actual measurements
- `src/articubot_one/description/lidar.xacro` — laser_frame xyz updated to actual lidar position
- `src/articubot_one/config/my_controllers.yaml` — wheel_separation and wheel_radius corrected

Key corrections:
- `wheel_separation`: 0.297 → 0.179 (old value was physically impossible — wider than robot)
- `wheel_radius`: 0.0325 → 0.034 (measured 68mm diameter; datasheet says 65mm)
- `chassis_length`: 0.335 → 0.240
- `chassis_width`: 0.265 → 0.1355
- `wheel_offset_y`: 0.1485 → 0.0895
- `caster_wheel_offset_x`: 0.075 → 0.033
- lidar xyz: `0.122, 0, 0.212` → `0.200, 0, 0.116`

Note: `enc_counts_per_rev` re-validated 2026-03-17 → updated to 1010 (3 wall-guided runs, avg 1011).

### 10) Motor swap and encoder recalibration (2026-03-16)
Motors replaced with: DC12V 130RPM encoder gear motors (Amazon B07X7M1LLQ)
- JGA25-371, actual gear ratio 45:1 (Amazon listing says 34:1 — inaccurate)
- 11 PPR encoder on motor shaft
- Encoder voltage: 3.3–5V
- Wire colors updated (see Hardware / Wiring Notes)
Files changed:
- `src/articubot_one/description/ros2_control.xacro` — `enc_counts_per_rev` updated to 990 (validated via odometry 2026-03-16; correction formula: new = old × reported/actual), then re-validated 2026-03-17 → 1010 (3 wall-guided runs with corrected wheel_radius=0.034)

### 8) Kinematics and controller config fixes (2026-03-13)
Files changed:
- `src/articubot_one/config/my_controllers.yaml` — wheel_radius corrected from 0.033 to 0.0325 (65mm wheel diameter confirmed from datasheet); acceleration limits added (0.5 m/s², 1.0 rad/s²) to smooth teleop motion
- `src/articubot_one/launch/launch_robot.launch.py` — remapped `/diff_cont/odom` to `/odom` on controller_manager node for Nav2 compatibility

### 9) PID tuning validation (2026-03-13)
Tested via serial with custom tuning script. Firmware defaults confirmed optimal:
- Kp=20, Kd=12, Ki=0, Ko=50
- Settles to target in ~3s from cold start with zero steady-state error
- No firmware changes needed — defaults are correct

### 5) Arduino firmware rewrite for correct L298N wiring
Files changed in `src/ros_arduino_bridge/ROSArduinoBridge/`:
- `motor_driver.h` — updated pin defines to match actual wiring, swapped IN1↔IN2 and IN3↔IN4 to fix reversed direction
- `motor_driver.ino` — rewrote `initMotorController()` and `setMotorSpeed()` to use PWM on ENA/ENB and digitalWrite on IN pins
- `encoder_driver.h` — updated encoder pin defines (Left: D2+D4, Right: D3+D12)
- `encoder_driver.ino` — replaced AVR PCINT register code with `attachInterrupt` (D3/D12 are on different AVR ports, PCINT grouping can't handle them together)
- `ROSArduinoBridge.ino` — replaced PCINT setup block with `pinMode INPUT_PULLUP` + `attachInterrupt`

Flash tool: `arduino-cli` installed at `/home/ryan/bin/arduino-cli`
Board FQBN: `arduino:avr:nano:cpu=atmega328old`
Flash command:
```bash
fuser -k /dev/ttyUSB0 2>/dev/null
/home/ryan/bin/arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
/home/ryan/bin/arduino-cli upload --fqbn arduino:avr:nano:cpu=atmega328old --port /dev/ttyUSB0 ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
```

### 6) Fixed `launch_robot.launch.py` robot_description lookup
Old line 49 queried a running node before it existed:
```python
robot_description = Command(['ros2 param get --hide-type /robot_state_publisher robot_description'])
```
Fixed to use xacro directly:
```python
robot_description = Command(['xacro ', os.path.join(get_package_share_directory(package_name), 'description', 'robot.urdf.xacro'), ' use_ros2_control:=true sim_mode:=false'])
```

### 4) True clean rebuild
```bash
cd ~/mybot_ws
rm -rf build install log
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
```

## Key Commands
### Source environment
```bash
source /opt/ros/humble/setup.bash
source ~/mybot_ws/install/setup.bash
```

### Install dependencies
```bash
rosdep install --from-paths src --ignore-src -r -y
```

### Build
```bash
colcon build --symlink-install
```

### Clean rebuild
```bash
rm -rf build install log
colcon build --symlink-install
```

### Launch robot
```bash
mybot-launch
```
Alias clears /dev/arduino and /dev/rplidar before launching. Starts: robot_state_publisher, ros2_control_node, diff_drive_controller, joint_state_broadcaster, twist_mux, rplidar, bno055, ekf_filter_node.

### Check IMU
```bash
sudo i2cdetect -y 1        # confirm BNO055 at 0x28
ros2 topic echo /imu/imu   # verify IMU data flowing
ros2 topic echo /imu/calib_status  # check calibration (0-3, 3=fully calibrated)
```

### Check odometry
```bash
ros2 topic echo /odom              # EKF filtered odometry
ros2 topic echo /diff_cont/odom    # raw wheel odometry
```

### Package checks
```bash
ros2 pkg list | grep diffdrive
ros2 pkg executables diffdrive_arduino
ros2 pkg executables serial
```

### Serial checks
```bash
ls /dev/ttyUSB*
python3 -m serial.tools.miniterm /dev/ttyUSB0 57600
```

## Launch Behavior Notes
From `launch_robot.launch.py`:
- includes `rsp.launch.py` with:
  - `use_sim_time=false`
  - `use_ros2_control=true`
- runs `twist_mux`
- remaps `/cmd_vel_out` to `/diff_cont/cmd_vel_unstamped`
- starts `ros2_control_node`
- spawns:
  - `diff_cont`
  - `joint_broad`
- controller manager startup is delayed by `3.0` seconds

## Robot Physical Dimensions
Source: `Hardware/mybot/` — CAD renders (mybot_dim.png and orthographic views)

### Orientation
- **Front** = drive wheel side (curved bumper)
- **Back** = caster side (flat end)
- Note: opposite of tutorial robot orientation — verify when editing URDF

### Chassis (all mm)
- Chassis length (front→back): `240`
- Chassis plate width: `135.5`
- Total width incl. motors: `200` (left overhang 26.2mm, right 38.3mm — slightly asymmetric)
- Lidar standoff base: `25mm`
- Back wall/caster assembly height: `95mm`
- Total height (ground→lidar top): `153.25`
- Lower plate height from ground: `47.25` (±0.1)
- Inter-deck gap: `40`
- Standoff outer span (side view): `96.5`
- Standoff inner span (side view): `70`
- Plate thickness: `5`

### Wheels & Caster
- Wheel diameter: `Ø65mm` → radius `32.5mm` ✓
- Wheel separation: `297mm` center-to-center ✓
- Wheel axle from front edge: `83.5mm` → 36.5mm ahead of chassis center
- Caster: `R10` ball (20mm diameter)
- Caster from back edge: `33mm` → 87mm behind chassis center

### Derived URDF values
- Wheel axle height from ground: `32.5mm`
- Lower plate above axle: `47.25 − 32.5 = 14.75mm`
- Caster x from chassis center: `−87mm`
- Lidar: centered laterally (y=0), x and z position TBD from physical measurement

### Derived URDF values (applied 2026-03-16)
- `wheel_offset_x`: `0.1565` (chassis rear to wheel axle = 240 − 83.5mm)
- `wheel_offset_y`: `0.0895` (half of 179mm c-t-c)
- `wheel_offset_z`: `-0.010` (plate is 10mm ABOVE axle — negative)
- `caster_wheel_offset_x`: `0.033` (33mm from rear in chassis frame)
- Lidar xyz in chassis frame: `0.200, 0, 0.116` (40mm from front, 160mm scan plane from ground)
- Ground to top of top plate: `96mm`

## Hardware / Wiring Notes
### Serial / firmware behavior from `ros_arduino_bridge/README.md`
- default baud rate: `57600`
- command examples:
  - `e` → encoder counts
  - `r` → reset encoders
  - `o <PWM1> <PWM2>` → raw PWM
  - `m <Spd1> <Spd2>` → closed-loop speed
  - `p <Kp> <Kd> <Ki> <Ko>` → PID update
- firmware expects carriage return
- serial user should be in `dialout`

### Confirmed working pin mapping (flashed and verified 2026-03-13)
L298N → Arduino Nano:
```
ENA → D5   (PWM, left motor enable)
IN1 → D6   (left motor direction)
IN2 → D7   (left motor direction)
IN3 → D8   (right motor direction)
IN4 → D9   (right motor direction)
ENB → D10  (PWM, right motor enable)
```
Encoders:
```
Left  encoder A → D2  (INT0)
Left  encoder B → D4
Right encoder A → D3  (INT1)
Right encoder B → D12
```
Motor logic: PWM on ENA/ENB, direction on IN pins via digitalWrite.
Direction was corrected by swapping IN1↔IN2 and IN3↔IN4 in firmware (motors ran reversed initially).

### Known encoder wire colors (DC12V 130RPM Amazon gear motors, installed 2026-03-16)
- Red: motor power +
- White: motor power -
- Blue: encoder power + (3.3–5V)
- Black: encoder power -
- Yellow: encoder A phase
- Green: encoder B phase

### Hardware docs Claude should preserve
Create or maintain these if absent:
- `docs/pin-mapping.md`
- `docs/wire-colors.md`
- `docs/pin-locations.md`
- `docs/hardware-block-diagram.md`
- `docs/known-good-wiring.md`

## Tutorial Progress
Following: https://articulatedrobotics.xyz/category/build-a-mobile-robot-with-ros
Author repos: https://github.com/joshnewans

```
Build a Mobile Robot with ROS
├── Project Overview                                              ✅ done
├── Concept Design
│   ├── URDF Design                                              ✅ done
│   └── Gazebo Simulation                                        ✅ done
├── Hardware
│   ├── The Brain - Raspberry Pi                                 ✅ done
│   ├── Power Concepts                                           ✅ done
│   ├── Adding Lidar                                             ✅ done (2026-03-17)
│   └── Adding a Camera                                          ⬜ pending
└── Applications
    ├── ros2_control Concepts & Simulation                       ✅ done
    ├── ros2_control extra bits                                   ✅ done
    ├── ros2_control on the real robot                           ✅ done (+ full validation 2026-03-13)
    ├── Teleoperation                                            ✅ done
    ├── SLAM with slam_toolbox                                   ✅ done (2026-03-18) — map saved; new map 2026-03-21
    ├── Navigation with Nav2                                     ✅ done (2026-03-21) — robot navigates autonomously to goals
    └── Object Tracking with OpenCV                             ⬜ pending

Camera hardware notes:
- D435 detected at USB 3.2 (Bus 002 Device 002: ID 8086:0b07)
- FW version: 5.17.0.10, Serial: 244622071235
- Depth stream: working (640x480@15fps)
- Color stream: broken until RSUSB backend build (fix #18)
- launch/camera.launch.py — wraps rs_launch.py, 640x480@15fps, no pointcloud, no align_depth
- camera included in launch_robot.launch.py
```

### Repositories
- `https://github.com/joshnewans/articubot_one` — base robot package
- `https://github.com/joshnewans/diffdrive_arduino`
- `https://github.com/joshnewans/serial`

### Tutorials / upstream references
- `https://youtu.be/J02jEKawE5U`
- `https://github.com/ros-controls/ros2_control_demos/tree/master/example_2`

### Hardware references from project history
- `https://www.robotshop.com/products/e-s-motor-25d-12v-encoder-gear-motor-w-mounting-bracket-65mm-wheel-smart-robot-diy`
- `https://cdn.robotshop.com/rbm/a00a7635-653b-4220-aac9-b0c23c5c5e2c/9/937bc8fd-df7e-4549-84e7-739dc23aaa9d/c1a0ee55_25d-encoder-gear-motor-kits.pdf`

## Helpful Images In Repo
- `src/diffdrive_arduino/doc/diffbot.png`

## Missing But Important Visuals To Add
These are not present in the repo snapshot and should be added:
- real robot wiring photo
- Arduino pin location image
- motor driver pin location image
- wheel left/right orientation photo
- encoder wire color photo or datasheet screenshot
- top-level hardware block diagram
- USB/serial connection photo
- known-good wiring diagram

## Project Reality Check
- `articubot_one` still contains template placeholders in `README.md` and `package.xml`.
- `ros_arduino_bridge` still exists in source tree, but should be treated as reference firmware / legacy material, not the active ROS 2 software path.
- The working system depends on exact plugin naming, paired branches, and clean rebuild discipline.
