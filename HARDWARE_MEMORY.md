# HARDWARE_MEMORY.md

## Robot Hardware Goal
Differential drive ROS 2 robot using Raspberry Pi + Arduino motor controller + serial ros2_control hardware interface.

---

## System Block Diagram

Dev Machine (ROS tools / teleop / Nav2)
        ⇅ WiFi / network

Raspberry Pi (ROS 2 Humble)
├── robot_state_publisher
├── ros2_control_node
├── diff_drive_controller
├── twist_mux
└── USB Serial → Arduino

Arduino Motor Controller
├── Reads wheel encoders
└── Drives motor driver

Motor Driver (L298N — prototype stage)
└── Left / Right DC Gear Motors

---

## Serial Link

Device:
/dev/ttyUSB0

Baud:
57600

Timeout (ros2_control config):
1000 ms

User must be in:
dialout group

Test command:
python3 -m serial.tools.miniterm /dev/ttyUSB0 57600

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

---

## Encoder Wiring (DC12V 130RPM Amazon Gear Motors — installed 2026-03-16)

Red   → Motor Power +
White → Motor Power -
Blue  → Encoder VCC (3.3V–5V)
Black → Encoder Ground
Yellow → Encoder Channel A
Green  → Encoder Channel B

Encoder Arduino pin mapping:
Left  A → D2 (INT0), Left  B → D4
Right A → D3 (INT1), Right B → D12

Encoder resolution:
11 PPR (motor shaft), ~50:1 gear ratio
Configured counts per rev in ROS:
1100 (measured via serial readback 2026-03-16; pending odometry validation)

To fine-tune after odometry test:
new_value = 1100 × (actual_distance / reported_distance)

---

## Wheel Geometry (Controller Config)

Wheel separation:
0.297 m

Wheel radius:
0.0325 m (65mm diameter confirmed from datasheet)

Controller update rate:
30 Hz

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

1. Plug Arduino USB
2. Verify device:
   ls /dev/ttyUSB*
3. Test serial stream
4. Source ROS
5. Launch robot

---

## Hardware Images Claude Should Always Index

REAL PHOTOS — highest priority memory

• robot base top view  
• robot base underside  
• motor driver wiring close‑up  
• Arduino pin connection photo  
• encoder wire color photo  
• wheel left vs right orientation  
• battery + power distribution  
• USB cable routing  
• block diagram sketch  

---

## Future Hardware Paths (Planned)

Possible upgrades:

• Replace L298N with modern MOSFET driver  
• ESP32 + micro‑ROS instead of Arduino  
• Hoverboard motor platform migration  
• IMU integration (BNO055)  
• RPLidar navigation stack  
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
