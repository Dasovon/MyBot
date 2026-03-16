# CLAUDE.md

## Project Goal
ROS 2 Humble differential drive robot stack for a Raspberry Pi + Arduino robot using `ros2_control`, `diffdrive_arduino`, and serial motor/encoder communication.

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

## Key Config Values
From `src/articubot_one/description/ros2_control.xacro`:
- hardware plugin: `diffdrive_arduino/DiffDriveArduinoHardware`
- left wheel joint: `left_wheel_joint`
- right wheel joint: `right_wheel_joint`
- loop rate: `30`
- serial device: `/dev/ttyUSB0`
- baud rate: `57600`
- timeout: `1000 ms`
- encoder counts per rev: `1100` (updated 2026-03-16: motors swapped to DC12V 130RPM Amazon encoder gear motors; measured ~1100 counts/rev via serial encoder readback; was 748 for old E-S Motor 34:1 units; pending odometry validation)

From `src/articubot_one/config/my_controllers.yaml`:
- controller manager update rate: `30`
- diff drive controller name: `diff_cont`
- joint state broadcaster name: `joint_broad`
- wheel separation: `0.297`
- wheel radius: `0.0325` (65mm diameter confirmed from E-S Motor datasheet)
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

## Current Status (2026-03-16)
- Motors swapped to DC12V 130RPM Amazon encoder gear motors
- `enc_counts_per_rev` updated to `1100` (measured, pending odometry validation)
- Both encoders confirmed working via serial readback
- Left encoder counts negative for forward rotation — direction inversion may need re-check after full launch
- **Pending:** drive 1m forward, verify `/odom` x ≈ 1.0m, fine-tune `enc_counts_per_rev` if needed
- Dev machine (192.168.86.52) communicates with Pi (192.168.86.33) via ROS 2 DDS on `ROS_DOMAIN_ID=0`
- Next steps: validate odometry → mount RPLidar → SLAM → Nav2

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

### 10) Motor swap and encoder recalibration (2026-03-16)
Motors replaced with: DC12V 130RPM encoder gear motors (Amazon B07X7M1LLQ)
- 11 PPR encoder on motor shaft, ~50:1 gear ratio (inferred from ~1100 counts/rev measurement)
- Encoder voltage: 3.3–5V
- Wire colors updated (see Hardware / Wiring Notes)
Files changed:
- `src/articubot_one/description/ros2_control.xacro` — `enc_counts_per_rev` updated from 748 to 1100
- Value measured via serial encoder readback (`e` command); pending odometry validation
- If odometry is off, adjust: `new_value = 1100 × (actual_distance / reported_distance)`

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
ros2 launch articubot_one launch_robot.launch.py
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
│   ├── Adding Lidar                                             ⬅ NEXT
│   └── Adding a Camera                                          ⬜ pending
└── Applications
    ├── ros2_control Concepts & Simulation                       ✅ done
    ├── ros2_control extra bits                                   ✅ done
    ├── ros2_control on the real robot                           ✅ done (+ full validation 2026-03-13)
    ├── Teleoperation                                            ✅ done
    ├── SLAM with slam_toolbox                                   ⬜ pending
    ├── Navigation with Nav2                                     ⬜ pending
    └── Object Tracking with OpenCV                             ⬜ pending
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
