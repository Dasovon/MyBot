# HARDWARE_MEMORY.md

## Robot Hardware Goal
Differential drive ROS 2 robot using Raspberry Pi + Arduino motor controller + serial ros2_control hardware interface.

---

## System Block Diagram

Dev Machine (ROS tools / teleop / RViz2 / Nav2 / EKF)
        ⇅ WiFi / network (ROS_DOMAIN_ID=0)

Raspberry Pi (ROS 2 Humble) — 192.168.86.33
├── robot_state_publisher
├── micro_ros_agent (serial /dev/ttyACM0) ← ESP32-S3
├── twist_mux
├── rplidar_node → /scan (/dev/rplidar)
└── realsense2_camera_node → /camera/*

ESP32-S3-DevKitC-1 — 192.168.86.43 (WiFi OTA only)
├── Publishes: /diff_cont/odom (30Hz), /imu/imu (30Hz), /battery_state (1Hz)
├── Subscribes: /diff_cont/cmd_vel_unstamped
├── GPIO10-15 → TB6612 → Left/Right DC Gear Motors (JGA25-371, 45:1)
├── GPIO40/41 (Left enc A/B), GPIO42/39 (Right enc A/B)
└── I2C GPIO8/9 → BNO055 (0x28) + INA219 (0x40)

---

## Serial Links

### ESP32-S3 (micro-ROS)
Device: /dev/ttyACM0  (HWCDC native USB — no udev symlink needed)
Protocol: micro-ROS serial transport
Agent: `source ~/microros_ws/install/setup.bash && ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0`

### RPLidar
Device: /dev/rplidar  (udev symlink → CP2102, 10c4:ea60)
Baud: 115200

### udev rules file
/etc/udev/rules.d/99-mybot.rules

User must be in: dialout group

---

## I2C — BNO055 IMU

Device: /dev/i2c-1 (I2C bus 1 — GPIO2=SDA pin3, GPIO3=SCL pin5)
Address: 0x28 (default, ADR pin unconnected)
Confirmed: sudo i2cdetect -y 1 shows 0x28

Wiring (BNO055 → Raspberry Pi):
VIN  → 3.3V (pin 1)
GND  → GND  (pin 6)
SDA  → GPIO2 / SDA (pin 3)
SCL  → GPIO3 / SCL (pin 5)
RST, INT, ADR, PS0, PS1 → unconnected

Physical mount position (base_link frame):
xyz = "0.004 -0.018 0.055"
(80mm from front edge, 50mm from right edge, upper deck)

ROS config: config/bno055_params.yaml
- connection_type: i2c
- i2c_bus: 1
- i2c_addr: 0x28
- topic prefix: imu/
- frame_id: imu_link
- operation_mode: 0x0C (NDOF — full sensor fusion)

---

## Motor Driver Pin Mapping (Arduino → Adafruit TB6612)

Replaced L298N with Adafruit TB6612 breakout (2026-04-25). Same physical Arduino pins.

PWMA = D5   → right motor PWM speed   (Motor A = RIGHT)
AIN2 = D6   → right motor direction B
AIN1 = D7   → right motor direction A
BIN1 = D8   → left motor direction A  (Motor B = LEFT)
BIN2 = D9   → left motor direction B
PWMB = D10  → left motor PWM speed

STBY → not wired; Adafruit breakout has onboard pullup (defaults HIGH = enabled)

Firmware define: TB6612_MOTOR_DRIVER
File: src/ros_arduino_bridge/ROSArduinoBridge/ROSArduinoBridge.ino

Direction logic:
  Forward:  xIN1=HIGH, xIN2=LOW + PWM
  Backward: xIN1=LOW,  xIN2=HIGH + PWM
  Coast:    xIN1=LOW,  xIN2=LOW
  Brake:    xIN1=HIGH, xIN2=HIGH

**STATUS: First TB6612 unit damaged — replacement needed.**
Cause: 12V motor supply reached AIN1/BIN1 logic input pins (max is 5.5V).
Symptom: xIN1 pins read ~2V when driven HIGH — below 3.5V logic threshold — CW direction non-functional.
Confirmed via multimeter: BIN1 = 11.9V with motor power connected.

BEFORE INSTALLING REPLACEMENT: verify VM wire has no breadboard bridge to AIN1 or BIN1.
After installing new chip: validate motor direction with teleop. If a motor runs reversed, swap its output wires (Red/White) at the TB6612 terminals.

---

## Encoder Wiring (DC12V 130RPM Amazon JGA25-371 — installed 2026-03-16)

Red    → Motor Power +
White  → Motor Power -
Blue   → Encoder VCC (3.3V–5V)
Black  → Encoder Ground
Yellow → Encoder Channel A
Green  → Encoder Channel B

Encoder Arduino pin mapping:
Left  A → D2 (INT0), Left  B → D4
Right A → D3 (INT1), Right B → D12

Encoder resolution:
11 PPR (motor shaft), 45:1 actual gear ratio (Amazon listing says 34:1 — inaccurate)
Firmware uses 2x quadrature → 11 × 2 × 45 = 990 base; validated value is 1010

Configured counts per rev in ROS: 1010
Re-validated 2026-03-17 (3 wall-guided runs: 1006/1016/1012, avg 1011)

To fine-tune after odometry test:
new_value = old_value × (actual_distance / reported_distance)

---

## Wheel Geometry (Controller Config)

Wheel separation: 0.179 m  (179mm center-to-center, measured 2026-03-16)
Wheel radius: 0.034 m  (68mm diameter measured; datasheet says 65mm)
Controller update rate: 30 Hz

---

## Odometry / EKF

/diff_cont/odom — raw wheel odometry from diff_drive_controller
/imu/imu        — fused IMU data from BNO055 (NDOF mode)
/odom           — EKF filtered output (robot_localization ekf_node, 20Hz)

EKF config: config/ekf.yaml
- frequency: 20Hz
- two_d_mode: true
- fuses: odom0=/diff_cont/odom + imu0=/imu/imu
- IMU orientation disabled (magnetometer unreliable on metal chassis)
- IMU angular velocity + linear accel enabled

---

## Known Working ros2_control Hardware Plugin

diffdrive_arduino/DiffDriveArduinoHardware

File:
articubot_one/description/ros2_control.xacro

Never use legacy class:
diffdrive_arduino/DiffDriveArduino

---

## Runtime Controller Names

diff_cont
joint_broad

cmd_vel remap target:
/diff_cont/cmd_vel_unstamped

---

## Power Architecture

Power distribution board: **DFR0205** (DFRobot DC-DC buck converter, 3.6–25V in, adjustable out, 5A/25W max)

```
12V LiPo/Lead-acid battery
├── DFR0205 regulated 5V ──────────→ Raspberry Pi (USB-C)
│       └── Pi USB port ───────────→ Arduino Nano (power + serial data, one cable)
│       └── Pi USB port ───────────→ ESP32-S3 (when in use, power + serial/OTA)
└── DFR0205 12V passthrough ───────→ TB6612 VM (motor power only)

TB6612 logic (VCC) powered separately:
  Arduino stack: VCC → Arduino 5V pin
  ESP32 stack:   VCC → ESP32 3V3 pin
```

Ground must be common between: Pi, Arduino/ESP32, TB6612, encoders, DFR0205.

---

## Known Good Bringup Sequence

1. Plug ESP32-S3 USB (ttyACM0) and RPLidar USB into Pi
2. Verify devices: ls /dev/ttyACM0 /dev/rplidar
3. Source workspace: source ~/mybot_ws/install/setup.bash && source ~/microros_ws/install/setup.bash
4. Launch robot: mybot-launch
5. On dev machine: source ~/dev_ws/install/setup.bash

mybot-launch alias (in ~/.bashrc on Pi):
Runs launch_robot.launch.py which starts micro_ros_agent, twist_mux, rplidar, realsense2_camera, robot_state_publisher

---

## SLAM Map

Saved: ~/mybot_ws/maps/my_map.pgm + my_map.yaml
Size: 200 × 136 cells @ 0.05 m/pix
Captured: 2026-03-18 via slam_toolbox online async mode, teleop-controlled

---

## Hardware Docs in Repo

Hardware/
├── adafruit-bno055-absolute-orientation-sensor.pdf  — BNO055 breakout datasheet
├── 4010_datasheet.pdf                               — fan/motor datasheet
├── DC12V Encoder Gear Motor.png                     — motor photo
├── motor.png                                        — motor photo
└── mybot/                                           — CAD renders
    ├── mybot_dim.png                                — chassis dimensions
    ├── mybot_front/back/left/right/top.png          — orthographic views
    └── mybot1.png                                   — isometric view

---

## Hardware Images Still Needed

• real robot wiring photo
• Arduino pin connection photo
• BNO055 mount photo
• encoder wire color photo
• wheel left/right orientation photo
• battery + power distribution photo
• USB/serial connection photo

---

## ESP32-S3 + micro-ROS (branch: feature/esp32-microros — all tests confirmed)

Hardware: ESP32-S3-DevKitC-1 on Lonely Binary ESP32-S3 Expansion Base.
Static IP: 192.168.86.43 | Hostname: esp32-mybot.local | OTA password: esp32ota
Replaces Arduino Nano + Pi-side BNO055/INA219. Pi EKF/Nav2/AMCL require no changes — same topics.

ESP32-S3 → TB6612 (Motor A = RIGHT, Motor B = LEFT):
```
VCC  → 3V3    (logic supply)
PWMA → GPIO10  (right motor speed, LEDC ch 0)
AIN1 → GPIO11  (right motor dir A)
AIN2 → GPIO12  (right motor dir B)
PWMB → GPIO13  (left motor speed, LEDC ch 1)
BIN1 → GPIO14  (left motor dir A)
BIN2 → GPIO15  (left motor dir B)
STBY → not wired (Adafruit breakout onboard pullup)
VM   → 12V motor supply
GND  → GND
```

ESP32-S3 → BNO055 + INA219 (shared I2C bus):
```
SDA  → GPIO8   (both devices)
SCL  → GPIO9   (both devices)
Vin  → 3V3
GND  → GND
BNO055 address: 0x28 (ADR unconnected)
INA219 address: 0x40 (A0/A1 unconnected)
```

Encoders → ESP32-S3 (INPUT_PULLUP, interrupt on A channel CHANGE):
```
Left  A → GPIO40,  Left  B → GPIO41
Right A → GPIO42,  Right B → GPIO39
```
ISR: Left A==B → forward, Right A!=B → forward. ENC_CPR=1010, radius=0.034m.

micro-ROS Transport — USB serial via native HWCDC:
```
ESP32-S3 native USB port → USB cable → Pi /dev/ttyACM0
build_flags = -DARDUINO_USB_CDC_ON_BOOT=1  (routes Serial to HWCDC)
WiFi used only for OTA and TelnetStream monitoring
```

micro-ROS agent (built from source in ~/microros_ws — not in apt for arm64):
```bash
source /opt/ros/humble/setup.bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0
```

Topics: publishes `/diff_cont/odom`, `/imu/imu`, `/battery_state`
        subscribes `/diff_cont/cmd_vel_unstamped`

---

## Future Hardware Paths

• Hoverboard motor platform migration

---

## Golden Rule

When robot stops moving:

Do not change:

• plugin name
• serial device
• encoder pins
• motor polarity
• controller YAML

all at once.

Change one variable.
Observe.
Repeat.

Robots obey physics.
Software obeys strings.
Confusing the two creates smoke.
