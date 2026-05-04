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

Motor Driver (Adafruit TB6612)
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

## Motor Driver Pin Mapping (Arduino → Adafruit TB6612)

Replaced L298N with Adafruit TB6612 breakout (2026-04-25). Validated 2026-05-03.

PWMA = D5   → right motor PWM speed   (Motor A = RIGHT)
AIN1 = D7   → right motor FORWARD
AIN2 = D6   → right motor BACKWARD
BIN1 = D8   → left motor FORWARD     (Motor B = LEFT)
BIN2 = D9   → left motor BACKWARD
PWMB = D10  → left motor PWM speed

STBY → not wired; Adafruit breakout has onboard pullup (defaults HIGH = enabled)

Motor output wiring:
  Right motor → AO1 + AO2  (both wires on MOTORA pads — NOT the GND pad between sections)
  Left motor  → BO1 + BO2  (both wires on MOTORB pads — NOT the GND pad between sections)

Firmware define: TB6612_MOTOR_DRIVER
File: src/ros_arduino_bridge/ROSArduinoBridge/ROSArduinoBridge.ino

Direction logic (TB6612 truth table):
  Forward:  xIN1=HIGH, xIN2=LOW + PWM
  Backward: xIN1=LOW,  xIN2=HIGH + PWM
  Coast:    xIN1=LOW,  xIN2=LOW
  Brake:    xIN1=HIGH, xIN2=HIGH

**STATUS: Replacement installed and validated 2026-05-03.**
Both motors run in both directions. Teleop confirmed: i=forward, j/l=turn.

History:
- First unit (2026-04-25): destroyed by 12V reaching AIN1/BIN1 logic pins (max 5.5V)
- Replacement: motor wires were on motor output pad + GND pad between sections instead of
  both on MOTORA/MOTORB pads → only one direction worked. Fixed by moving wires to correct pads.
- Left motor ran backward: swapped LEFT_MOTOR_FORWARD/BACKWARD (BIN1↔BIN2) in firmware.

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

Velocity limits (my_controllers.yaml):
  linear max:  0.3 m/s   (each wheel at 0.3 m/s)
  angular max: 3.35 rad/s  (= 2 × 0.3 / 0.179 — matched to linear for equal wheel speed)

Velocity tracking validation (2026-05-03, 3 consistent runs, robot free to move on floor):
  Speed   Forward  Spin
  25%     83%      69%   ← motor deadband at low PWM — normal for DC motors
  50%     92%      88%
  75%     97%      93%
  100%    98%      96%
Left/right wheels symmetric within 0.002 m/s across all steps.
Operating range (50–100%) tracks 88–98% for both modes.

Note: holding the robot body while spinning creates lateral tire scrub → hard plateau at ~0.085 m/s.
This is NOT a motor/firmware limit — robot must be free to rotate for normal behavior.

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

## ESP32 + micro-ROS (Experimental — branch: feature/esp32-microros)

Firmware scaffold at `src/esp32_microros/` (PlatformIO project).
Replaces Arduino + direct Pi I2C with a single ESP32 handling motors and BNO055.
Pi-side stack (EKF, Nav2, AMCL) requires no changes — same topics.

ESP32-DevKitC → TB6612:
```
VCC  → 3V3   (logic threshold — must match MCU voltage)
PWMA → GPIO25  (right motor speed)
AIN2 → GPIO26  (right motor dir B)
AIN1 → GPIO27  (right motor dir A)
BIN1 → GPIO32  (left motor dir A)
BIN2 → GPIO33  (left motor dir B)
PWMB → GPIO14  (left motor speed)
STBY → not wired (onboard pullup)
VM   → 12V motor supply
```

ESP32-DevKitC → BNO055:
```
SDA  → GPIO21
SCL  → GPIO22
Vin  → 3V3
GND  → GND
```

Encoders → ESP32 (input-only pins, no pullup needed):
```
Left  A → GPIO36,  Left  B → GPIO39
Right A → GPIO34,  Right B → GPIO35
```

To test: run micro-ROS agent on Pi instead of ros2_control/bno055 nodes:
```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
```

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
