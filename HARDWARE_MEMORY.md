# HARDWARE_MEMORY.md

## Robot Hardware Goal
Differential drive ROS 2 robot using Raspberry Pi + Arduino motor controller + serial ros2_control hardware interface.

---

## System Block Diagram

Dev Machine (ROS tools / teleop / RViz2 / Nav2)
        ⇅ WiFi / network (ROS_DOMAIN_ID=0)

Raspberry Pi (ROS 2 Humble) — 192.168.86.33
├── robot_state_publisher
├── ros2_control_node → diff_drive_controller → /diff_cont/odom
├── twist_mux
├── rplidar_node → /scan
├── bno055 → /imu/imu
├── ekf_filter_node (/diff_cont/odom + /imu/imu → /odom)
└── USB Serial → /dev/arduino → Arduino

Arduino Motor Controller
├── Reads wheel encoders
└── Drives motor driver

Motor Driver (L298N)
└── Left / Right DC Gear Motors (DC12V 130RPM JGA25-371, actual ratio 45:1)

RPLidar A1 M8
└── USB Serial → /dev/rplidar → rplidar_node

BNO055 IMU (Adafruit breakout)
└── I2C → /dev/i2c-1 → bno055 node → /imu/imu

---

## Serial Links

### Arduino
Device: /dev/arduino  (udev symlink → CH340, 1a86:7523, ttyUSB0)
Baud: 57600
Timeout (ros2_control config): 1000 ms
Test command: python3 -m serial.tools.miniterm /dev/arduino 57600

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

## Motor Driver Pin Mapping (Arduino → L298N)

ENA = 5
ENB = 10

IN1 = 6
IN2 = 7
IN3 = 8
IN4 = 9

Meaning:

ENA → left motor PWM enable
ENB → right motor PWM enable

IN1 / IN2 → left motor direction
IN3 / IN4 → right motor direction

Direction corrected in firmware (IN1↔IN2, IN3↔IN4 swapped so both wheels run forward).

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

## Power Architecture (Current Prototype)

Battery → Motor Driver → Motors
Battery → Buck Converter → Arduino + Encoder Logic
Battery → Buck Converter → Raspberry Pi USB‑C

Ground must be common between:
Pi
Arduino
Motor Driver
Encoders

---

## Known Good Bringup Sequence

1. Plug Arduino USB, RPLidar USB, and BNO055 I2C into Pi
2. Verify devices: ls /dev/arduino /dev/rplidar && sudo i2cdetect -y 1
3. Source workspace: source ~/mybot_ws/install/setup.bash
4. Launch robot (alias handles port clearing): mybot-launch
5. On dev machine: source ~/mybot_ws/install/setup.bash

mybot-launch alias (in ~/.bashrc on Pi):
Runs: sudo fuser -k /dev/arduino /dev/rplidar before launching

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

## Future Hardware Paths (Planned)

• Replace L298N with modern MOSFET driver
• ESP32 + micro‑ROS instead of Arduino
• Hoverboard motor platform migration
• RealSense perception

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
