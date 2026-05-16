# CLAUDE.md

## Session Orientation — Read First

### What this project is
ROS 2 Humble differential drive robot. RPi 4 + ESP32-S3 (production stack — Arduino Nano replaced). Based on Articulated Robotics tutorial series.

### Current state (2026-05-15)
- Nav2 autonomous navigation ✅ working (saved map at `~/mybot_ws/maps/my_map`)
- RealSense D435 ✅ color + depth 640×480@15fps (RSUSB backend, fix #18)
- **Pi fully restored after reflash** ✅: ROS Humble, mybot_ws, microros_ws, librealsense RSUSB, udev rules, SLAM map — all restored. Pi IP: 192.168.86.33
- **ESP32-S3 driving with Pi velocity smoother** (fix #33):
  - Publishes: `/diff_cont/odom` (30Hz), `/imu/imu` (30Hz), `/battery_state` (1Hz)
  - Subscribes: `/diff_cont/cmd_vel_unstamped`
  - Robot stack auto-starts with `robot-launch.service`; `mybot-launch` remains the manual restart path
  - PID: Kp=30, Ki=150, KI_MAX=1.0, Kd=0
  - EMA filter: VEL_ALPHA=0.2 (suppresses left encoder EMI noise)
  - Command shaping: START_PWM_SEED=55, PWM_SLEW_PER_TICK=8 (ESP32-level only; command ramping now done on Pi)
  - REVERSAL_COAST_VEL=3.0 rad/s (raised from 0.8 — EMI noise on left encoder was false-triggering coast)
  - CMD_TIMEOUT_MS=1000ms (safety stop if publisher dies while agent alive)
  - **Launch path (fix #33)**: `twist_mux → /cmd_vel_raw → vel_smoother.py (50Hz, 0.5 m/s², 1.0 rad/s²) → /diff_cont/cmd_vel_unstamped`
  - **Teleop must use `repeat_rate:=10.0`**: `ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p repeat_rate:=10.0`
  - If agent shows stuck/AGENT OFFLINE after OTA reboot: `sudo systemctl restart robot-launch.service`
- **Waveshare 2.42" OLED display** ✅ FULLY WORKING (2026-05-15):
  - `oled-display.service` ENABLED, running as `ryan`, survives cold power cycle
  - Shows: IP, battery V/A, velocity, position, nav status — all data from ESP32
  - Root cause of "dark display": RPi.GPIO requires gpio/spi groups (fix #25 below)
  - Root cause of "BAT -- / AGENT OFFLINE": DDS late-joining timing (fix #27 below)
  - Service uses default FastDDS (SHM+UDP); self-restart loop in node handles timing
- **Fully automatic boot** ✅ (2026-05-15):
  - `robot-launch.service` ENABLED — starts micro_ros_agent + sensor stack at boot
  - ESP32 watchdog: 30 s in WAITING state → `esp_restart()` → USB re-enumerates cleanly (fix #29)
  - No manual `mybot-launch` or reset button needed after power-on

### Next steps
1. Object Tracking with OpenCV (final tutorial chapter)
2. Jetson Nano setup (Docker + ROS 2 Humble + CUDA)

---

## Machines

| | Pi | Dev (Linux) | Windows |
|---|---|---|---|
| Hostname | `mybot` | `dev` | `RyansPC` |
| IP | `192.168.86.33` | `192.168.86.52` | `192.168.86.47` |
| Workspace | `~/mybot_ws` | `~/dev_ws` | `C:\Users\Ryan\Documents\win_ws\MyBot` |
| Repo path | `src/articubot_one` | `src/articubot_one` | `src/esp32_microros` (ESP32 only) |

**Which machine am I on?** `hostname` → `mybot` = Pi | `dev` = Linux dev machine | `RyansPC` = Windows (ESP32 dev only)

SSH to Pi: `ssh ryan@mybot "..."` — prefer hostname over IP.

### What runs where
| Component | Machine |
|---|---|
| micro_ros_agent, RPLidar, RealSense | Pi |
| motors, encoders, BNO055, INA219, odometry, IMU | ESP32-S3 (via USB to Pi) |
| EKF, Nav2 (AMCL/planner/controller), RViz2, OpenCV | Dev |

**ESP32 dev:** use dev (Linux) or Windows — no Pi needed for bench work.

---

## Launch Sequence

**Pi robot stack auto-starts at boot** via `robot-launch.service` — no manual step needed.
If you need to restart it manually: `ssh ryan@mybot "mybot-launch"` (kills stale processes first).

```bash
# 1. Pi — auto-starts at boot (robot-launch.service)
# Manual override if needed:
ssh ryan@mybot "mybot-launch"

# 2. Dev — EKF
ros2 launch articubot_one dev_launch.py

# 3. Dev — localization
ros2 launch articubot_one localization_launch.py

# 4. Dev — Nav2
ros2 launch articubot_one navigation_launch.py

# 5. Dev — RViz2
rviz2
# Fixed Frame: map | Add: Map /map (Transient Local), LaserScan /scan, RobotModel
# 2D Pose Estimate → init AMCL | Nav2 Goal → navigate
```

---

## Key Config Values

| Parameter | Value | Source |
|---|---|---|
| hardware plugin | `diffdrive_arduino/DiffDriveArduinoHardware` | ros2_control.xacro |
| serial device | `/dev/arduino` (udev → ttyUSB0) | ros2_control.xacro |
| baud rate | `57600` | ros2_control.xacro |
| enc_counts_per_rev | `1010` | ros2_control.xacro |
| wheel_separation | `0.179` m | my_controllers.yaml |
| wheel_radius | `0.034` m | my_controllers.yaml |
| controller update rate | `30` Hz | my_controllers.yaml |
| left joint | `left_wheel_joint` | ros2_control.xacro |
| right joint | `right_wheel_joint` | ros2_control.xacro |

---

## Critical Rules
- Plugin string: **`diffdrive_arduino/DiffDriveArduinoHardware`** — never the old `diffdrive_arduino/DiffDriveArduino`
- Branch locks: `diffdrive_arduino` → `humble` | `serial` → `newans_ros2`
- `ros_arduino_bridge` = legacy reference only — active path is `ros2_control → diffdrive_arduino → serial`
- After changing plugin packages, branches, or manifests: **true clean rebuild** (`rm -rf build install log`)
- Never rename controller, joint, or plugin identifiers. ROS is extremely literal.
- Never change serial device, baud, motor polarity, and encoder mapping all at once during debugging.
- `articubot_one` still contains template placeholders in `README.md` and `package.xml` — treat as tutorial residue.

## Coding Conventions
- Build type: `ament_cmake` | Style: ROS-standard snake_case
- Xacro and YAML own hardware constants — keep them there
- Surgical edits only — tutorial-derived package has residue; avoid broad cleanup
- `ros_arduino_bridge` stays in tree as reference; never treat as active runtime

---

## Repos / Branches
- `src/articubot_one` → `main` (active — includes ESP32 firmware and OLED node)
- `src/diffdrive_arduino` → `humble` (on Pi, kept in ws but not active)
- `src/serial` → `newans_ros2` (on Pi, kept in ws but not active)
- `src/ros_arduino_bridge` → `main` (legacy Arduino firmware reference only)

Remote: `github.com/Dasovon/MyBot`

---

## Hardware

### Motors & Encoders
- JGA25-371 DC12V 130RPM, 45:1 gear ratio, 11 PPR encoder
- `enc_counts_per_rev = 1010` (2x quadrature × 11 × 45 ≈ 990; empirically validated → 1010)
- Both encoders count positive for forward rotation (no inversion needed)

### Encoder wire colors
| Color | Signal |
|---|---|
| Red | Motor + |
| White | Motor − |
| Blue | Encoder 3.3–5V |
| Black | Encoder GND |
| Yellow | Encoder A |
| Green | Encoder B |

### TB6612 → Arduino Nano pin mapping
| TB6612 | Arduino | Notes |
|---|---|---|
| VCC | 5V | sets logic thresholds — must match MCU voltage |
| PWMA | D5 | RIGHT motor speed |
| AIN2 | D6 | RIGHT motor dir B |
| AIN1 | D7 | RIGHT motor dir A |
| BIN1 | D8 | LEFT motor dir A |
| BIN2 | D9 | LEFT motor dir B |
| PWMB | D10 | LEFT motor speed |
| STBY | — | Adafruit pullup, leave unwired |

Motor A (PWMA/AIN1/AIN2) = **RIGHT** | Motor B (PWMB/BIN1/BIN2) = **LEFT**

⚠️ First TB6612 damaged — 12V reached AIN1/BIN1 (max 5.5V). Replacement on order. Before installing: verify VM wire has no breadboard bridge to AIN1/BIN1.

### Encoder → Arduino
| Signal | Pin |
|---|---|
| Left A | D2 (INT0) |
| Left B | D4 |
| Right A | D3 (INT1) |
| Right B | D12 |

### Arduino Nano firmware
- Firmware define: `TB6612_MOTOR_DRIVER`
- Baud: `57600` | Flash tool: `arduino-cli` at `/home/ryan/bin/arduino-cli`
- Board FQBN: `arduino:avr:nano:cpu=atmega328old`
- Flash:
  ```bash
  fuser -k /dev/ttyUSB0 2>/dev/null
  /home/ryan/bin/arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
  /home/ryan/bin/arduino-cli upload --fqbn arduino:avr:nano:cpu=atmega328old --port /dev/ttyUSB0 ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
  ```
- Serial commands: `e` (encoders) | `r` (reset) | `o <PWM1> <PWM2>` (raw) | `m <S1> <S2>` (closed-loop)

### ESP32-S3 pin mapping — Lonely Binary Expansion Base (production stack)
⚠️ GPIO4/5/6/7 and GPIO25/26/27/32/33/34/35/36/43/44 are NOT broken out on the Lonely Binary board.

Board left side: 3V3, GND, 15, 16, 17, 18, 8, 3, 46, 9, 10, 11, 12, 13, 14
Board right side: 3V3, GND, 1, 2, 42, 41, 40, 39, 38, 37, 36, 35, 0, 45, 48, 47, 21, 20, 19

| Function | GPIO | Board side |
|---|---|---|
| PWMA (RIGHT speed) | 10 | Left |
| AIN1 | 11 | Left |
| AIN2 | 12 | Left |
| PWMB (LEFT speed) | 13 | Left |
| BIN1 | 14 | Left |
| BIN2 | 15 | Left |
| BNO055 SDA / INA219 SDA | 8 | Left |
| BNO055 SCL / INA219 SCL | 9 | Left |
| Left enc A | 40 | Right |
| Left enc B | 41 | Right |
| Right enc A | 42 | Right |
| Right enc B | 39 | Right |

ESP32-S3 VCC → 3.3V (no level shifter needed for TB6612 at 3.3V logic).

I2C bus (GPIO8/9): BNO055 @ 0x28, INA219 @ 0x40 — both confirmed on bench.

### ESP32 micro-ROS topics (identical to Arduino stack)
- Publishes: `/diff_cont/odom` (Odometry), `/imu/imu` (Imu)
- Subscribes: `/diff_cont/cmd_vel_unstamped` (Twist)

### RealSense D435
- RSUSB backend (librealsense v2.56.4 built from source, `-DFORCE_RSUSB_BACKEND=ON`)
- May need physical replug after Pi reboot to enumerate
- Launch: `launch/camera.launch.py` — included in `launch_robot.launch.py`

### ⚠️ credentials.h — never commit
Gitignored. Create manually on every dev machine at `src/esp32_microros/**/credentials.h`:
```cpp
#pragma once
#define WIFI_SSID     "FBI-Van"
#define WIFI_PASSWORD "RachelRyan+2017"
#define OTA_PASSWORD  "esp32ota"
```

### Windows ESP32 dev setup (one-time)
1. **CH340 driver** — download from [wch-ic.com](https://www.wch-ic.com/downloads/CH341SER_EXE.html) and install. The Lonely Binary expansion base uses a CH340 chip (not CP2102).
2. **Git for Windows** — from git-scm.com, all defaults
3. **VS Code** — from code.visualstudio.com
4. **PlatformIO IDE extension** — in VS Code Extensions sidebar, search "PlatformIO IDE", install
5. **Clone repo:**
   ```
   git clone https://github.com/Dasovon/MyBot.git
   cd MyBot
   # ESP32 firmware lives on main in this repo; no branch switch needed
   ```
6. **Open sketch folder** in VS Code:
   `File → Open Folder → MyBot\src\esp32_microros\test\test_bno055`
7. **Create credentials.h** (gitignored — must create manually):
   Create file at `src\credentials.h` with the block shown above.
8. **First flash (USB):** PlatformIO sidebar → `esp32-s3` env → Upload
   - If upload fails: hold BOOT button on ESP32, click Upload, release when "Connecting..." appears
9. **All future flashes (OTA):** PlatformIO sidebar → `esp32-s3-ota` env → Upload
   - Or from terminal: `pio run -e esp32-s3-ota --target upload`
10. **Monitor wirelessly:** open terminal, run `nc esp32-mybot.local 23`
    - On Windows use PuTTY (Raw mode, port 23) or install netcat via Git Bash

---

## Key Commands

```bash
# Source
source /opt/ros/humble/setup.bash && source ~/mybot_ws/install/setup.bash

# Build
colcon build --symlink-install

# Clean rebuild
rm -rf build install log && colcon build --symlink-install

# Launch robot (Pi alias — clears serial before launching)
mybot-launch

# IMU
sudo i2cdetect -y 1
ros2 topic echo /imu/imu
ros2 topic echo /imu/calib_status

# Odometry
ros2 topic echo /odom
ros2 topic echo /diff_cont/odom

# Serial
ls /dev/ttyUSB*
python3 -m serial.tools.miniterm /dev/ttyUSB0 57600

# ESP32 test flash
cd src/esp32_microros/test/<test_name>
pio run --target upload           # USB (first time)
pio run -e esp32-s3-ota --target upload  # OTA (all future)
nc esp32-mybot.local 23           # wireless monitor

# micro-ROS agent on Pi — ESP32-S3 connected via native USB (ttyACM0)
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0
```

### Dev workspace setup (one-time, on dev machine)
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

---

## End-of-Session Routine

1. Stop ROS processes on dev and Pi
2. Update `CLAUDE.md` — current status, next steps, tutorial progress
3. Update `docs/` — if hardware or setup changed
4. Commit and push from dev:
   ```bash
   cd ~/dev_ws/src/articubot_one && git add -A && git commit -m "..." && git push
   ```
5. Sync Pi:
   ```bash
   ssh ryan@mybot "cd ~/mybot_ws/src/articubot_one && git pull"
   ```
6. Update memory files at `/home/ryan/.claude/projects/-home-ryan-dev-ws/memory/`

---

## Tutorial Progress
Following: https://articulatedrobotics.xyz/category/build-a-mobile-robot-with-ros

```
├── URDF + Gazebo Simulation          ✅
├── Hardware (Pi, Power, Lidar)       ✅
├── Adding a Camera (RealSense D435)  ✅ RSUSB backend, 15fps
├── ros2_control (sim + real)         ✅ full validation 2026-03-13
├── Teleoperation                     ✅ (Arduino stack + ESP32 stack both validated)
├── SLAM with slam_toolbox            ✅ map saved 2026-03-21
├── Navigation with Nav2              ✅ autonomous goals working
├── ESP32-S3 micro-ROS migration      ✅ full stack driving 2026-05-10
└── Object Tracking with OpenCV       ⬜ pending
```

---

## Physical Dimensions (URDF reference)
- `wheel_radius`: 0.034m | `wheel_separation`: 0.179m
- `wheel_offset_x`: 0.1565 | `wheel_offset_y`: 0.0895 | `wheel_offset_z`: -0.010
- `caster_wheel_offset_x`: 0.033
- Lidar xyz in chassis frame: `0.200, 0, 0.116`
- **Front** = drive wheel side (curved bumper) | **Back** = caster side

---

## Docs to Maintain
- `docs/pin-mapping.md` | `docs/wire-colors.md` | `docs/workflow.md`
- `docs/hardware-block-diagram.md` | `docs/known-good-wiring.md`

---

## References
- Upstream robot package: `https://github.com/joshnewans/articubot_one`
- `https://github.com/joshnewans/diffdrive_arduino` | `https://github.com/joshnewans/serial`
- Tutorial video: `https://youtu.be/J02jEKawE5U`
- ros2_control demo: `https://github.com/ros-controls/ros2_control_demos/tree/master/example_2`

---

## Exact Fix History

### 1) Hardware plugin class fix
File: `src/articubot_one/description/ros2_control.xacro`
```xml
<!-- old -->
<plugin>diffdrive_arduino/DiffDriveArduino</plugin>
<!-- new -->
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
ROS1-era design, replaced by `ros2_control → diffdrive_arduino → serial`.

### 4) True clean rebuild
```bash
cd ~/mybot_ws
rm -rf build install log
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
```

### 5) Arduino firmware rewrite for correct L298N wiring
Files changed in `src/ros_arduino_bridge/ROSArduinoBridge/`:
- `motor_driver.h` — updated pin defines, swapped IN1↔IN2 and IN3↔IN4 to fix reversed direction
- `motor_driver.ino` — rewrote `initMotorController()` and `setMotorSpeed()` using PWM on ENA/ENB and digitalWrite on IN pins
- `encoder_driver.h` — updated encoder pin defines (Left: D2+D4, Right: D3+D12)
- `encoder_driver.ino` — replaced AVR PCINT register code with `attachInterrupt`
- `ROSArduinoBridge.ino` — replaced PCINT setup with `pinMode INPUT_PULLUP` + `attachInterrupt`

### 6) Fixed `launch_robot.launch.py` robot_description lookup
Old: queried a running node before it existed:
```python
robot_description = Command(['ros2 param get --hide-type /robot_state_publisher robot_description'])
```
Fixed: use xacro directly:
```python
robot_description = Command(['xacro ', os.path.join(get_package_share_directory(package_name), 'description', 'robot.urdf.xacro'), ' use_ros2_control:=true sim_mode:=false'])
```

### 7) Encoder count and direction fixes (2026-03-13)
- `ros2_control.xacro` — `enc_counts_per_rev` corrected from 3436 to 748 (E-S Motor, 11 PPR, 34:1, 2x quadrature)
- `encoder_driver.ino` — right encoder ISR inverted: `if (A == B)` → `if (A != B)` so both wheels count positive for forward

### 8) Kinematics and controller config fixes (2026-03-13)
- `my_controllers.yaml` — `wheel_radius` corrected 0.033 → 0.0325; acceleration limits added (0.5 m/s², 1.0 rad/s²)
- `launch_robot.launch.py` — remapped `/diff_cont/odom` → `/odom` for Nav2 compatibility

### 9) PID tuning validation (2026-03-13)
Firmware defaults confirmed optimal: Kp=20, Kd=12, Ki=0, Ko=50. No firmware changes needed.

### 10) Motor swap and encoder recalibration (2026-03-16)
Motors replaced with JGA25-371 DC12V 130RPM, 45:1 (Amazon listing says 34:1 — inaccurate).
- `ros2_control.xacro` — `enc_counts_per_rev` updated to 990, then re-validated 2026-03-17 → 1010

### 11) URDF updated to actual robot dimensions (2026-03-16)
- `robot_core.xacro` — chassis, wheel, caster dimensions from physical measurement
- `lidar.xacro` — laser_frame xyz updated
- `my_controllers.yaml` — `wheel_separation` 0.297 → 0.179, `wheel_radius` 0.0325 → 0.034

### 12) RPLidar A1 M8 installed and robot model orientation fixed (2026-03-17)
- `/etc/udev/rules.d/99-mybot.rules` — udev symlinks for `/dev/arduino` (CH340) and `/dev/rplidar` (CP2102)
- `ros2_control.xacro` — device `/dev/ttyUSB0` → `/dev/arduino`
- `rplidar.launch.py` — `serial_port /dev/rplidar`, `serial_baudrate 115200` (required — timeout without it)
- `robot_core.xacro` — `chassis_joint rpy="0 0 pi"` to fix 180° backwards render
- `~/.bashrc` — `mybot-launch` alias added

### 13) SLAM with slam_toolbox configured and confirmed working (2026-03-18)
- `online_async_launch.py` — `use_sim_time` default `true` → `false`
- `mapper_params_online_async.yaml` — `mode: mapping`, `max_laser_range: 12.0`, reduced minimum travel thresholds

### 14) BNO055 IMU + robot_localization EKF integrated (2026-03-18)
- `robot_core.xacro` — `imu_link` added at xyz="0.004 -0.018 0.055"
- `bno055_params.yaml` — I2C bus 1, addr 0x28, topic prefix `imu/`, NDOF mode
- `ekf.yaml` — fuses `/diff_cont/odom` + `/imu/imu` → `/odom` at 20Hz, `two_d_mode true`
- `launch_robot.launch.py` — added bno055 + ekf_node; EKF now owns `/odom`
- EKF IMU config: orientation disabled (magnetometer unreliable on metal robot), angular velocity + linear accel enabled

### 15) Nav2 launch files and params updated to Humble API (2026-03-20)
- `navigation_launch.py` — rewritten: `recoveries_server` → `behavior_server`, added `smoother_server` and `velocity_smoother`
- `localization_launch.py` — rewritten: `ParameterFile` wrapper, default map `~/mybot_ws/maps/my_map.yaml`
- `nav2_params.yaml` — fully replaced with Humble-compatible params:
  - `robot_model_type: "nav2_amcl::DifferentialMotionModel"` (old `"differential"` deprecated)
  - `robot_radius: 0.17` | `inflation_radius: 0.35` | `laser_max_range: 12.0`
  - Added `smoother_server`, `waypoint_follower`, `velocity_smoother` sections

### 16) SLAM drift tuning (2026-03-21)
`mapper_params_online_async.yaml`:
- `minimum_time_interval: 0.5` → `0.3`
- `link_match_minimum_response_fine: 0.1` → `0.3`
- `loop_match_minimum_chain_size: 10` → `5`

### 17) Nav2 velocity limits increased (2026-03-21)
`nav2_params.yaml`: `max_vel_x: 0.26` → `0.4`, `max_speed_xy: 0.26` → `0.4`, velocity_smoother limits updated to match.
Reason: robot lacked torque to move consistently at 0.26 m/s.

### 18) RealSense D435 — librealsense source build with FORCE_RSUSB_BACKEND (2026-03-21, COMPLETE)
Problem: apt librealsense compiled against kernel UVC driver; `xioctl(UVCIOC_CTRL_QUERY)` timeouts prevent color stream intrinsics. Depth worked; color failed.

Solution: build librealsense v2.56.4 from source with `-DFORCE_RSUSB_BACKEND=ON`, then replace the apt `.so` (must match SONAME `librealsense2.so.2.56`):
```bash
sudo apt remove ros-humble-librealsense2*
sudo apt install libusb-1.0-0-dev libssl-dev cmake libgtk-3-dev
git clone https://github.com/IntelRealSense/librealsense ~/librealsense && cd ~/librealsense && git checkout v2.56.4
mkdir build && cd build
cmake .. -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF -DBUILD_GRAPHICAL_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
make -j2 && sudo make install && sudo ldconfig   # -j2 not -j4 — Pi OOMs with -j4
sudo apt install ros-humble-realsense2-camera ros-humble-realsense2-description
sudo cp /usr/local/lib/librealsense2.so.2.56.4 /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4
```
Key lessons: `LD_LIBRARY_PATH` tricks don't work — ROS setup.bash prepends its lib path; must overwrite the file. D435 may need physical replug after Pi reboot.

### 19) Motor driver swap: L298N → Adafruit TB6612 (2026-04-25, chip damaged — replacement needed)
- `motor_driver.h` — added `TB6612_MOTOR_DRIVER` ifdef block
- `motor_driver.ino` — added TB6612 `initMotorController()` and `setMotorSpeed()`
- `ROSArduinoBridge.ino` — `#define L298_MOTOR_DRIVER` → `#define TB6612_MOTOR_DRIVER`

Diagnosis: first unit damaged by 12V reaching AIN1/BIN1 logic pins (max VCC+0.5V = 5.5V). xIN2 pins unaffected (CCW direction worked). Confirmed via multimeter: BIN1 read 11.9V with motor supply connected.

Note: `src/ros_arduino_bridge/` on Pi is a separate repo. Firmware edits in `articubot_one/src/ros_arduino_bridge/` must be SCP'd to Pi before flashing.

### 20) TB6612 wiring table label correction + VCC documentation (2026-04-26)
Root cause: original table had Motor A and Motor B labels swapped vs firmware. Firmware assigns `RIGHT_MOTOR_*` to Motor A (PWMA/AIN1/AIN2) and `LEFT_MOTOR_*` to Motor B (PWMB/BIN1/BIN2).
Files corrected: `CLAUDE.md`, `HARDWARE_MEMORY.md`, `docs/pin-mapping.md`.

### 21) ESP32 + micro-ROS experiment scaffolded (2026-04-26)
Branch: `main`

Files created:
- `src/esp32_microros/platformio.ini` — ESP32-DevKitC, Arduino 3.x, micro-ROS humble, Adafruit BNO055
- `src/esp32_microros/src/main.cpp` — full firmware: encoders + PID + odometry + BNO055 + micro-ROS pub/sub
- `src/esp32_microros/test/test_bno055/` — BNO055 I2C test, serial output, calibration status
- `src/esp32_microros/test/test_encoders/` — encoder pulse counting, direction verification
- `src/esp32_microros/test/test_motors/` — TB6612 test with safety checklist
- `src/esp32_microros/test/test_microros/` — micro-ROS transport test, heartbeat publisher

Status at scaffold: firmware written, not yet flashed. BNO055 + INA219 subsequently confirmed on bench (2026-05-09). Motors/encoders confirmed 2026-05-09. micro-ROS transport confirmed 2026-05-10.

### 22) ESP32-S3 board pin corrections — Lonely Binary Expansion Base (2026-05-09)
Original ESP32 sketch used wrong board (`esp32dev`) and wrong GPIO pins (GPIO25/26/27/32/33/34/35/36/39 — not present on S3 or not broken out on Lonely Binary board). Fixed across all test sketches.

Lonely Binary board layout — GPIO not broken out: 4, 5, 6, 7, 25, 26, 27, 32, 33, 34 (as output), 36 (S3 has no VP/VN), 43, 44.

Final validated pin assignments:
- TB6612: PWMA=10, AIN1=11, AIN2=12, PWMB=13, BIN1=14, BIN2=15
- Encoders: Left A/B = 40/41, Right A/B = 42/39
- I2C: SDA=8, SCL=9

LEDC API: ESP32-S3 Arduino framework uses legacy API — `ledcSetup(ch, freq, res)` + `ledcAttachPin(pin, ch)` + channel-based `ledcWrite(ch, duty)`. New-style `ledcAttach(pin, freq, res)` not available.

### 23) micro-ROS transport: micro_ros_platformio + USB HWCDC (2026-05-10)
Problem 1: `micro_ros_arduino` humble branch has no precompiled `libmicroros.a` for `xtensa-esp32s3-elf` — only for original `esp32`, ARM Cortex-M, and Teensy targets. Linker errors: `undefined reference to rclc_executor_fini` etc.

Fix: replaced `micro_ros_arduino` zip with `micro_ros_platformio` library, which cross-compiles `libmicroros.a` for the exact PlatformIO target at build time.

Problem 2: `micro_ros_platformio` build script needs `~/.platformio/penv/bin/activate` but pip-installed PlatformIO doesn't create this venv.

Fix: manually created fake penv:
```bash
mkdir -p ~/.platformio/penv/bin
ln -sf /usr/bin/python3 ~/.platformio/penv/bin/python
printf 'export PATH="%s/.platformio/penv/bin:$PATH"\n' "$HOME" > ~/.platformio/penv/bin/activate
mkdir -p ~/.platformio/penv/lib/python3.10/site-packages
printf '/usr/lib/python3/dist-packages\n/usr/local/lib/python3.10/dist-packages\n' > ~/.platformio/penv/lib/python3.10/site-packages/system.pth
```

Problem 3: ESP32-S3 with native USB connected to Pi — `Serial` (UART0) goes to CH340 chip, but only the native USB JTAG port (ttyACM0) was connected. `Serial.write()` sent data nowhere.

Fix: added `build_flags = -DARDUINO_USB_CDC_ON_BOOT=1` to `platformio.ini`. The board definition already has `ARDUINO_USB_MODE=1` (HWCDC), so adding CDC_ON_BOOT routes `Serial` to the HWCDC peripheral which appears as `/dev/ttyACM0` on the Pi.

Problem 4: Connection cycling — ping timeout 100ms/1 attempt caused false disconnects after publish.

Fix: increased to `rmw_uros_ping_agent(500, 3)` and executor spin to 10ms.

Transport summary:
- ESP32 `Serial` → HWCDC → USB cable → Pi `/dev/ttyACM0`
- WiFi retained for OTA flashing and TelnetStream monitoring only
- micro-ROS agent workspace: `~/microros_ws` (built from source — `ros-humble-micro-ros-agent` not in apt for arm64)
- Agent command: `source ~/microros_ws/install/setup.bash && ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0`

### 24) Full ESP32-S3 production firmware (2026-05-10)
Files: `src/esp32_microros/platformio.ini` and `src/esp32_microros/src/main.cpp` — complete rewrite from scaffold.

`platformio.ini` changes:
- Board: `esp32dev` → `esp32-s3-devkitc-1`
- Library: `micro_ros_arduino` zip → `micro_ros_platformio`
- Added: `board_microros_distro = humble`, `board_microros_transport = serial`, `ARDUINO_USB_CDC_ON_BOOT=1`
- Added libs: `Adafruit INA219@^1.2.3`, `TelnetStream@^1.3.0`
- Added OTA env `[env:esp32-s3-ota]`

`main.cpp` — full production firmware combining all validated components:
- WAITING/CONNECTED state machine (identical pattern to test_microros)
- Encoders: GPIO40/41 (left), GPIO42/39 (right), INPUT_PULLUP, IRAM_ATTR ISRs
- PID: Kp=20, Kd=12, Ki=0 (from validated Arduino firmware); targets zeroed on agent loss
- Differential drive odometry → pub `/diff_cont/odom` at 30Hz
- BNO055 (GPIO8/9, 0x28) → pub `/imu/imu` at 30Hz; orientation_covariance[0]=-1 (EKF ignores orientation)
- INA219 (GPIO8/9, 0x40) → pub `/battery_state` at 1Hz; logged to TelnetStream
- TB6612 motors GPIO10-15, legacy LEDC API (ledcSetup/ledcAttachPin/ledcWrite, ch 0/1, 1kHz 8-bit)
- Sub `/diff_cont/cmd_vel_unstamped` → wheel rad/s targets
- Ping keep-alive every 2s; motors stop immediately on agent loss
- Odometry + encoder counts reset to 0 on each reconnect
- Build: 862KB flash (27.4%), 74KB RAM (22.8%) — well within huge_app.csv limits
- Flashed via OTA 2026-05-10 17:13

### 25) Pi launch migrated from ros2_control to micro_ros_agent (2026-05-10)
File: `src/articubot_one/launch/launch_robot.launch.py`

Removed: `controller_manager`, `delayed_controller_manager`, `diff_drive_spawner`, `joint_broad_spawner`, bno055 node, ina219 node, `robot_description` variable, `controller_params_file`, `Command`/`RegisterEventHandler`/`OnProcessStart` imports.

Added: `micro_ros_agent` Node (`ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0`).

Note: `micro_ros_agent` is built from source in `~/microros_ws` on Pi (not in apt for arm64). The mybot-launch alias was updated to `source ~/microros_ws/install/setup.bash` before launch.

### 26) ESP32 PID tuning and motor cross-wiring fix (2026-05-10)
Problem: violent motor jolting during turns and runaway at ±12 rad/s with zero target.

Root cause: a previous debugging attempt swapped PWMA↔PWMB channel assignments in `motor_set()` calls. This created a cross-wired positive feedback loop: pid_l read the left encoder but drove the right motor; correcting one motor accelerated the other. The runaway was stable at max speed because both PIDs saturated at ±255.

Fix: reverted motor assignment to original correct wiring:
```cpp
motor_set(PWMB_CH, BIN1, BIN2, pid_compute(pid_l, vel_l, dt));  // Left PID → Motor B (Left)
motor_set(PWMA_CH, AIN1, AIN2, pid_compute(pid_r, vel_r, dt));  // Right PID → Motor A (Right)
```

Also changed PID gains: `Kp=100 → Kp=30` (Kp=100 caused oscillation at turn speeds with no Kd), `Ki=150` retained (overcomes deadband), `Kd=0` retained.

Also added coast-to-stop: when target is near zero, PID returns 0 (motor coasts) instead of actively braking. Eliminates hard stop jerk on key release:
```cpp
if (fabsf(p.target) < 0.01f) { p.integral = 0.0f; p.prev_err = 0.0f; return 0; }
```

Teleop validated: forward, left/right turns, and combined arc all stable. Driven via `teleop_twist_keyboard` on dev machine.

### 27) OLED display subscriptions (BAT -- / AGENT OFFLINE) — DDS timing fix (2026-05-15)

**Symptom:** OLED display hardware works (shows IP, renders frames) but all data fields show `--`
and status shows `AGENT OFFLINE`. Occurs every boot — display worked only if oled service restarted
manually after `mybot-launch`.

**Root cause:** DDS late-joining publisher timing. The oled service starts at boot (ExecStartPre=5s
delay). The ESP32 connects to micro_ros_agent later (after `mybot-launch` is run). When micro_ros_agent
creates DDS publishers for `/battery_state`, `/diff_cont/odom`, etc., the oled node's subscriptions
were already created in a DDS universe where those publishers didn't exist. FastDDS SHM transport
made endpoint re-negotiation fail silently for late-joining publishers from micro_ros_agent.

**Diagnostic path:**
1. `ros2 topic info /battery_state -v --no-daemon` → oled subscription not listed (Subscription count: 0)
2. `ros2 topic echo /battery_state --no-daemon` (with fastdds_no_shm.xml) → received data fine
3. Restarting oled service WHILE ESP32 was connected → callbacks fired immediately (11.50V at 116ms)
4. Confirmed: the node matching works, but only when it starts after the publishers are live.

**Fix:** Self-restart on data timeout in `oled_display_node.py`. If `_battery_voltage` is still None
after 30 seconds, calls `os._exit(1)`. Systemd (`Restart=always`, `RestartSec=5`) restarts the node.
Repeats every ~35 s until `mybot-launch` is running and the ESP32 is connected. At that point the
node starts with live publishers already in the DDS domain — callbacks fire within ~1 second.

**What did NOT work:** forcing FastDDS UDP-only transport (`FASTRTPS_DEFAULT_PROFILES_FILE` with
`useBuiltinTransports=false`). UDP-only profile breaks matching with micro_ros_agent because
micro_ros_agent's DDS participants use SHM as primary transport; with no common transport the
endpoints can't exchange data. Default SHM+UDP is required.

**Confirmed working:** odom callback at 1.1s after node start, battery at 1.6s (11.43V from real ESP32).
Display shows: `BAT 11.43V  0.30A`, `VEL 0.00m/s  0.0r/s`, `TELEOP`.

**Files changed:**
- `src/articubot_one/scripts/oled_display_node.py` — added `import os`, `DATA_TIMEOUT = 30.0`,
  `_node_start_t`, and timeout check in `_render()` that calls `os._exit(1)`
- `/etc/systemd/system/oled-display.service` (Pi only) — no special env vars; default FastDDS

### 29) ESP32 30s WAITING watchdog — esp_restart() on HWCDC reconnect failure (2026-05-15)

**Symptom:** After Pi reboot, ESP32 is stuck in WAITING state and never reconnects to
micro_ros_agent. Display stays at AGENT OFFLINE. Physical reset button press on ESP32 always fixes it.

**Root cause:** ESP32-S3 HWCDC (native USB) uses the USB CDC peripheral directly. When the Pi
reboots, the Linux USB host re-enumerates the bus. The CDC endpoint gets into an inconsistent
state — the ESP32 thinks it's WAITING for the agent, but the USB layer is confused and the
serial transport never re-establishes. `rmw_uros_ping_agent()` always times out (no valid serial
connection). `esp_restart()` does a full chip reset which re-initializes the USB peripheral
cleanly and lets the host re-enumerate a fresh CDC device.

**Fix:** In `WAITING` case, track how long the ESP32 has been waiting. If > 30 s with no agent,
call `esp_restart()`. This handles the Pi reboot case automatically — ESP32 resets, Pi picks up
the re-enumerated `/dev/ttyACM0`, micro_ros_agent reconnects.

```cpp
case WAITING:
    if (waiting_start == 0) waiting_start = millis();
    if (rmw_uros_ping_agent(500, 3) == RMW_RET_OK) {
        waiting_start = 0;
        // ... create entities, go to CONNECTED ...
    } else if (millis() - waiting_start > 30000) {
        log("[esp32_robot] no agent for 30s — restarting\n");
        esp_restart();
    }
    break;
```

Also zeroed `waiting_start = 0` in the CONNECTED→WAITING transition so the timer resets on
each agent loss, not just on power-up.

**Boot sequence (fully automatic):** Pi boots → robot-launch.service starts micro_ros_agent →
ESP32 pings, finds agent, connects → display shows TELEOP within ~35 s. No manual button press.

**Files changed:**
- `src/esp32_microros/src/main.cpp` — added `waiting_start`, watchdog in WAITING case

### 28) OLED cold-boot SPI init — close+reopen fix (2026-05-15)

**Symptom:** After cold boot or reboot, display shows nothing. "Display init OK" logged but screen blank.
Works fine after manual `sudo systemctl restart oled-display`. Display works because OLED GDDRAM holds
its content as long as 3.3V is present, so screen looks "frozen" during reboot rather than going dark.

**Root cause:** On first kernel boot, opening `/dev/spidev0.0` for the first time doesn't fully apply
the mode/speed configuration. The single dummy write (with RST=LOW, display ignoring it) was not
enough to settle the kernel SPI controller. All subsequent init commands were silently malformed —
"Display init OK" logged because no exception was thrown, but GDDRAM writes never rendered.

**Fix:** Close and reopen the SPI device after the dummy write. This forces the kernel to fully
re-apply the mode and speed config before the real init sequence runs.

```python
self._spi.writebytes([0x00])
time.sleep(0.1)
self._spi.close()
self._spi.open(0, 0)
self._spi.max_speed_hz = 100000
self._spi.mode = 0b11
time.sleep(0.05)
```

**Confirmed:** Display renders correctly on first boot without any manual restart.

**Files changed:**
- `src/articubot_one/scripts/oled_display_node.py` — dummy write now followed by close+reopen

### 30) RPLidar startup failure — rplidar_node + 8s TimerAction delay (2026-05-15)

**Symptom:** `rplidar_composition` fails on every service start with `Can not start scan: 80008002!`
(RESULT_OPERATION_NOT_SUPPORT) or `80008000` (RESULT_OPERATION_TIMEOUT). Lidar motor is spinning
but the node exits immediately.

**Root cause (80008000):** On cold boot, the lidar motor needs ~8 seconds to reach operating speed
after the serial port is opened (DTR asserted). `rplidar_composition` launched immediately and timed
out before the motor was ready.

**Root cause (80008002):** `rplidar_composition` with SDK 2.0.0 tries to call `SET_MOTOR_PWM` which
the A1 M8 does not support (it uses DTR-based motor control only). `rplidar_node` auto-detects
the correct motor control method and scan mode.

**What did NOT work:**
- Python serial STOP+RESET (0xA5 0x25 / 0xA5 0x40) — didn't clear state
- Toggling `/sys/bus/usb/devices/1-1.2/authorized` — caused hub-wide USB disruption,
  knocked RealSense off the bus; required camera replug to recover

**Fix:**
1. Switch `rplidar.launch.py` from `rplidar_composition` to `rplidar_node`, remove `scan_mode`
   param (auto-detects Express mode at 4kHz/10Hz on A1 M8).
2. Wrap lidar launch in `TimerAction(period=8.0, ...)` in `launch_robot.launch.py` so the motor
   has time to spin up before the node connects.

**Files changed:**
- `src/articubot_one/launch/rplidar.launch.py` — `rplidar_composition` → `rplidar_node`, removed `scan_mode`
- `src/articubot_one/launch/launch_robot.launch.py` — `TimerAction(8s)` wrapping lidar launch

### 31) Jerky motion after Pi SD reinstall — EMA filter + command ramp + integral preseed (2026-05-15)

**Symptom:** After Pi SD card wipe and reinstall, robot drove jerkily during turns and straight-line
motion. One wheel appeared to turn more than the other. Fast startup "punch" on first movement.
"k" stop key left the robot coasting for ~1 second. Physical robot and wiring were unchanged.

**Root cause 1 — Left encoder EMI noise:** GPIO40/41 (left encoder) pick up TB6612 1 kHz PWM
switching noise from the motor power wires running nearby. Each noise burst adds phantom encoder
counts, spiking the raw velocity reading by 10–13 rad/s above true velocity for one tick. At
Kp=30, this caused a −60–105 PWM overcorrection every spike → physical jerk. The right encoder
(GPIO42/39) was stable. This noise existed pre-reinstall but was masked by the Arduino stack's
`diff_drive_controller` which had its own velocity smoothing. The direct micro-ROS path
(ESP32 → cmd_vel → PID, no middleware smoothing) exposed it.

**Root cause 2 — Command step-in:** `teleop_twist_keyboard` sends step changes in cmd_vel. With
Kp=30 and a step to 5.88 rad/s wheel speed, the first PID tick produces 176 PWM — nearly full
drive — causing the robot to lurch before settling.

**Root cause 3 — Ramp stop coast:** When the command ramp is active, sending cmd=0 ("k" key)
only starts the ramp decelerating at LIN_ACCEL rate. At 0.50 m/s² from 0.3 m/s, that's ~600 ms
of continued motion after the stop key is pressed.

**What did NOT work (tried in order):**
- EMA alpha=0.4 + spike clip (VEL_SPIKE=3.5) feeding PID: clipped spikes still caused −60 PWM
  corrections → still jerky
- Using clip_l/clip_r directly for PID (no EMA lag): spike clips still caused −60 PWM jerk
- Median-of-3 filter: introduced 33 ms feedback lag → PID oscillated during low-speed turns
  (wheels bounced back and forth)
- Slew rate on cmd target (LIN_ACCEL=0.5 m/s²): ramp step too small (0.49 rad/s/tick → 14.7 PWM)
  to overcome motor deadband (≈45 PWM) — integral wound up then lurched

**Fix — three parts applied together:**

1. **EMA velocity filter (alpha=0.2)** on encoder feedback before PID. Attenuates spike amplitude
   from ×3 above true to ×1.4 above true (0.2×spike + 0.8×true), keeping PID correction
   below the motor deadband. Confirmed smooth turning and straight driving.
   ```cpp
   static constexpr float VEL_ALPHA = 0.2f;
   vel_l_filt = VEL_ALPHA * vel_l + (1.0f - VEL_ALPHA) * vel_l_filt;
   // PID uses vel_l_filt, not raw vel_l
   ```

2. **Command ramp** shapes cmd_vel before it reaches PID targets. Eliminates startup punch.
   Stop command (both cmd_lin and cmd_ang ≈ 0) snaps ramp to zero immediately for crisp stop.
   ```cpp
   static constexpr float LIN_ACCEL = 0.35f;  // m/s²
   static constexpr float ANG_ACCEL = 1.10f;  // rad/s²
   if (fabsf(cmd_lin) < 0.01f && fabsf(cmd_ang) < 0.01f) {
       ramp_lin = 0.0f; ramp_ang = 0.0f;  // snap to zero on stop
   } else {
       ramp_lin += constrain(cmd_lin - ramp_lin, -LIN_ACCEL*dt, LIN_ACCEL*dt);
       ramp_ang += constrain(cmd_ang - ramp_ang, -ANG_ACCEL*dt, ANG_ACCEL*dt);
   }
   ```
   Tuning ranges: LIN_ACCEL 0.25–0.60 m/s², ANG_ACCEL 0.80–1.50 rad/s².
   Too low = sluggish feel. Too high = startup punch returns.

3. **Integral preseed** on rest→move transition. The ramp's first step only produces ~5–15 PWM
   from the P term — below motor deadband (~45 PWM). Preseed sets integral so that
   `Kp×error + Ki×integral = START_PWM_SEED` on the first tick, starting the motor cleanly.
   ```cpp
   static constexpr float START_PWM_SEED = 55.0f;
   // Fires only when pid.target was ~0 and new target is non-zero
   if (fabsf(p.target) < 0.01f && fabsf(nt) > 0.01f) {
       float s = (nt > 0) ? 1.0f : -1.0f;
       p.integral = constrain(s * (START_PWM_SEED - KP * fabsf(nt)) / KI, -KI_MAX, KI_MAX);
   }
   ```

4. **PWM slew limiter** (`PWM_SLEW_PER_TICK = 8`): caps motor PWM change at ±8 per 33ms tick
   after the PID output. Prevents abrupt mid-drive PWM jumps from noise spikes or fast target
   changes. Snaps to zero immediately when PID returns 0 (coast-to-stop still crisp).

5. **Reversal coast** in `pid_compute`: if a wheel is rolling >3.0 rad/s in the opposite direction
   of the new target, coast instead of fighting it (prevents reverse kick on direction change).
   Threshold raised to 3.0 in fix #32 — see below.

**Final tuned values (2026-05-15, updated by fix #32):**
- VEL_ALPHA = 0.2 (do not increase — higher alpha lets more noise through)
- LIN_ACCEL = 0.35 m/s², ANG_ACCEL = 1.10 rad/s² (felt right after iterative tuning)
- START_PWM_SEED = 55 PWM, PWM_SLEW_PER_TICK = 8, REVERSAL_COAST_VEL = 3.0 rad/s
- CMD_TIMEOUT_MS = 1000 ms

**Permanent hardware fix (not yet done):** Solder 100 nF ceramic caps from GPIO40 to GND and
GPIO41 to GND at the ESP32 headers. This removes the EMI noise at source and eliminates the
need for the EMA filter entirely.

**Files changed:**
- `src/esp32_microros/src/main.cpp` — EMA filter, command ramp, snap-to-zero stop, integral preseed, PWM slew, reversal coast

### 32) Teleop stall — command timeout + key repeat + reversal coast EMI false triggers (2026-05-15)

**Symptom:** Robot moves a short distance on a key tap; holding a key causes repeated stall-start
cycles instead of sustained motion. Changing CMD_TIMEOUT_MS from 500ms to 1000ms had no effect.

**Root cause 1 — teleop key repeat disabled in raw mode:** `teleop_twist_keyboard` puts the
terminal in raw (non-canonical) mode to read single keypresses. In raw mode most terminal
emulators suppress OS key repeat, so holding a key delivers only one publish event — identical
to a tap. The command timeout then fires 500–1000 ms later, stopping the robot.

**Root cause 2 — REVERSAL_COAST_VEL = 0.8 rad/s too low:** The left encoder (GPIO40/41) picks
up TB6612 1 kHz PWM switching noise. A noise burst of ~−4 rad/s raw yields a filtered value of
0.2 × (−4) = −0.8 rad/s — exactly the threshold. This false-triggered the reversal coast while
driving forward, returning 0 from `pid_compute` and resetting `slew_pwm`'s `last` to 0. The
motor had to rebuild PWM from scratch every noise burst (stall-restart cycle even mid-drive).

**Root cause 3 — no-active-braking also resetting slew:** The `pid_compute` no-active-braking
check (`if target > 0 && out < 0 → return 0`) fired on noise-induced velocity overshoots,
also resetting the slew limiter. Removed — the slew limiter already caps abrupt PWM changes,
making the check redundant.

**Diagnosis method:** Telnet monitor during driving showed tgt cycling between non-zero and 0.00
on consecutive 1Hz log ticks, with tgt ramp value resetting to a low number on each press
(confirming fresh ramp start = timeout fired between presses). After applying repeat_rate,
tgt stayed non-zero across consecutive ticks.

**Fix:**
1. Run `teleop_twist_keyboard` with `repeat_rate:=10.0` — node republishes at 10 Hz while a key
   is held, keeping cmd alive well within the 1000 ms timeout:
   ```bash
   ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p repeat_rate:=10.0
   ```
2. Raise `REVERSAL_COAST_VEL` from 0.8 → 3.0 rad/s. Requires a −15 rad/s raw noise spike to
   false-trigger (0.2 × 15 = 3.0), far above typical EMI levels.
3. Remove no-active-braking check from `pid_compute` — slew limiter handles abrupt changes.
4. Keep `CMD_TIMEOUT_MS = 1000` as a safety stop for lost publisher scenarios.

**Also discovered:** micro_ros_agent enters a stuck state after ESP32 reboots from OTA or the
30s WAITING watchdog fires. Topics are advertised but no data flows (ping succeeds at serial
level but DDS bridge is confused). Fix: `sudo systemctl restart robot-launch.service`. Does not
require a reboot.

**Files changed:**
- `src/esp32_microros/src/main.cpp` — REVERSAL_COAST_VEL 0.8→3.0, no-active-braking removed, CMD_TIMEOUT_MS 500→1000

### 33) Velocity smoother — restore diff_drive_controller acceleration limiting (2026-05-15)

**Symptom:** Motion after SD-card reinstall was never as smooth as the "perfect" state with the
initial ESP32-S3 firmware. Multiple band-aids (EMA, command ramp, preseed, slew) helped but never
fully recovered the feel.

**Root cause:** When the initial ESP32-S3 production firmware (commit c62b3bb, Kp=20, Kd=12, Ki=0)
was working perfectly, the Pi launch still had `diff_drive_controller` from `ros2_control` active.
That controller applied acceleration limits (linear 0.5 m/s², angular 1.0 rad/s²) and published
smoothed commands to the hardware at 50 Hz. The ESP32 PID only ever saw slow, well-conditioned
ramps — never a raw step input.

In the same commit that fixed the motor cross-wiring (fix #26, commit 19f7155), `diff_drive_controller`
was also removed and the PID changed to Kp=30, Ki=150. After the SD-card reinstall the user pulled
that state, losing the acceleration limiter entirely. All subsequent motion fixes were compensating
for that missing layer.

**Fix:** Pi-side `vel_smoother.py` node — subscribes to `/cmd_vel_raw` (twist_mux output), applies
0.5 m/s² linear and 1.0 rad/s² angular acceleration limits, publishes to `/diff_cont/cmd_vel_unstamped`
at 50 Hz. This is architecturally identical to what `diff_drive_controller` was doing.

The ESP32 command ramp (LIN_ACCEL/ANG_ACCEL) was removed to avoid double-ramping, which would have
made the response sluggish. Preseed, PWM slew, EMA filter, and reversal coast remain.

**Pipeline after fix:**
```
teleop → /cmd_vel → twist_mux → /cmd_vel_raw → vel_smoother.py (50Hz, 0.5/1.0) → /diff_cont/cmd_vel_unstamped → ESP32
```

**Note on permanent hardware fix (not yet done):** Solder 100 nF ceramic caps from GPIO40 to GND
and GPIO41 to GND at the ESP32 headers. This removes the EMI noise at source, allowing the EMA
filter to be removed or relaxed, which reduces feedback lag and lets the PID respond faster.

**Files changed:**
- `src/articubot_one/scripts/vel_smoother.py` — new node (linear_accel=0.5, angular_accel=1.0, freq=50)
- `src/articubot_one/launch/launch_robot.launch.py` — twist_mux remaps to /cmd_vel_raw; vel_smoother added
- `src/articubot_one/CMakeLists.txt` — install vel_smoother.py
- `src/esp32_microros/src/main.cpp` — remove LIN_ACCEL/ANG_ACCEL command ramp; ramp_lin/ramp_ang vars removed
