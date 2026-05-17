# Autonomous Multi-Sensor Mobile Robot System Specification

Version: 1.0  
Platform Type: Distributed ROS 2 Autonomous Mobile Robot (AMR)

---

# 1. Project Overview

## Goal

Build a distributed autonomous mobile robot capable of:

- Autonomous mapping
- Autonomous navigation
- Multi-sensor SLAM
- Obstacle avoidance
- Semantic perception
- Environmental monitoring
- Distributed ROS 2 processing
- Expandable AI integration

The robot architecture is intentionally designed to resemble a modern commercial AMR rather than a simple hobby robot.

---

# 2. High-Level System Architecture

```text
                    Development PC
          (SLAM / Nav2 / AI / RViz / Logging)
                           ↑
                   Wi-Fi / Ethernet
                           ↑
                   Raspberry Pi
        (Sensor bridge / ROS interface / drivers)
                           ↑
                     USB Serial
                           ↑
                      ESP32-S3
      (Motion controller / telemetry / safety)
                           ↑
                       TB6612FNG
                           ↑
                         Motors
```

---

# 3. Core Design Philosophy

## Layered Robotics Architecture

The system is divided into three major layers.

| Layer | Responsibility |
|---|---|
| ESP32-S3 | Real-time control and safety |
| Raspberry Pi | Sensor and hardware bridge |
| Development PC | High-level autonomy and AI |

---

## Core Philosophy

```text
ESP32-S3:
    Reflexes

Raspberry Pi:
    Nervous system

Development PC:
    Brain
```

---

# 4. Minimum Viable Robot (MVP)

The robot is considered operational when it can:

- Drive reliably
- Publish odometry
- Create a stable map
- Avoid collisions
- Stop safely on timeout
- Stream telemetry
- Operate safely without the development PC

---

# 5. Hardware Architecture

## Core Hardware

| Component | Purpose | Connected To |
|---|---|---|
| ESP32-S3 | Motion controller | Pi via USB |
| Raspberry Pi | Sensor bridge | ESP32 + sensors |
| Development PC | High-level compute | Pi over network |
| TB6612FNG | Motor driver | ESP32 |
| Wheel encoders | Odometry | ESP32 |
| RPLIDAR | 2D geometry | Pi |
| RealSense D435 | RGB-D perception | Pi |
| BNO055 | IMU | ESP32 I2C |
| INA219 | Battery monitor | ESP32 I2C |
| BME680 | Environmental sensing | ESP32 I2C |

---

# 6. Electrical Architecture

## Shared Ground Requirement

All systems must share a common ground.

```text
Battery -
ESP32 GND
Pi GND
TB6612 GND
Sensor GND
```

Failure to maintain common ground can cause:
- Serial communication errors
- Sensor instability
- PWM noise
- Motor glitches

---

## I2C Bus

The ESP32-S3 hosts the primary I2C bus.

```text
ESP32-S3 I2C Bus
├── INA219
├── BNO055
└── BME680
```

---

# 7. ESP32-S3 Motion Controller

## Purpose

The ESP32-S3 acts as a dedicated embedded robot base controller.

Responsibilities:
- Motor control
- Encoder counting
- PID velocity control
- Sensor polling
- Telemetry generation
- Safety enforcement

---

# 8. ESP32 Firmware Responsibilities

## Core Systems

```text
1. Motor controller
2. Encoder reader
3. PID velocity loop
4. Serial command parser
5. INA219 battery monitor
6. BNO055 IMU reader
7. BME680 environmental reader
8. Safety watchdog
```

---

# 9. ESP32 Firmware Timing Architecture

## Fast Loop (50–100 Hz)

Handles:
- Encoder updates
- PID calculations
- PWM output

---

## Medium Loop (50 Hz)

Handles:
- IMU updates
- Telemetry generation

---

## Slow Loop (1–5 Hz)

Handles:
- INA219 reads
- BME680 reads
- Environmental telemetry

---

## Safety Loop

Runs continuously.

Handles:
- Timeout detection
- Fault monitoring
- Emergency stop logic

---

# 10. Motion Control Philosophy

## Closed Loop Velocity Control

The robot uses:
- Encoder feedback
- PID velocity control
- Wheel velocity targets

NOT:
- Open-loop PWM power control

Goal:

```text
Accurate wheel velocity tracking
```

---

# 11. Encoder Architecture

Encoders use:
- Hardware interrupts
- Local ESP32 processing

The ESP32 handles:
- Tick counting
- Velocity estimation
- Wheel odometry generation

---

# 12. Motor Driver Architecture

## TB6612FNG

Responsibilities:
- PWM motor driving
- Direction control
- Differential drive output

---

## Motor Direction Logic

### Forward

```text
IN1 HIGH
IN2 LOW
```

### Reverse

```text
IN1 LOW
IN2 HIGH
```

### Brake

```text
IN1 HIGH
IN2 HIGH
```

### Coast

```text
IN1 LOW
IN2 LOW
```

---

# 13. Serial Communication Architecture

## Communication Philosophy

The robot initially uses:

```text
Simple USB serial communication
```

NOT:
- micro-ROS
- DDS
- XRCE-DDS

during early development.

Goal:
- Simplicity
- Stability
- Easy debugging

---

# 14. Serial Protocol

## Pi → ESP32 Commands

```text
V left_rad_s right_rad_s
STOP
PING
```

Examples:

```text
V 3.20 3.20
V -2.00 2.00
V 0.00 0.00
```

---

## ESP32 → Pi Telemetry

### Encoder Telemetry

```text
ENC left_ticks right_ticks
```

### Velocity Telemetry

```text
VEL left_rad_s right_rad_s
```

### IMU Telemetry

```text
IMU roll pitch yaw
```

### Battery Telemetry

```text
BAT voltage current power
```

### Environmental Telemetry

```text
ENV temp humidity pressure gas
```

### Error Telemetry

```text
ERR error_code
```

---

# 15. INA219 Battery Monitoring

## Purpose

The INA219 continuously monitors:
- Battery voltage
- Current draw
- Power usage

---

## Critical Design Rule

Battery monitoring must operate independently from:
- ROS
- Nav2
- Wi-Fi
- Development PC

The ESP32 must always know battery state.

---

## Battery Safety Logic

```text
If voltage < warning threshold:
    publish warning

If voltage < cutoff threshold:
    stop motors
```

---

# 16. BNO055 IMU Integration

## Purpose

Provides:
- Orientation
- Heading
- Rotation tracking

Used by:
- robot_localization
- Odometry fusion
- Navigation

---

# 17. BME680 Environmental Monitoring

## Purpose

Provides:
- Temperature
- Humidity
- Pressure
- Gas/VOC sensing

---

## Environmental Telemetry

```text
ENV 23.4 48.2 1008.6 114523
```

Meaning:
- temperature
- humidity
- pressure
- gas resistance

---

# 18. Raspberry Pi Architecture

## Purpose

The Pi acts as:
- Sensor bridge
- ROS interface
- Driver host
- Local networking node

---

## Pi Responsibilities

```text
serial bridge
LiDAR driver
RealSense driver
basic ROS nodes
network bridge
local safety handling
```

---

# 19. Development PC Architecture

## Purpose

The development PC acts as:
- Mission control
- SLAM server
- AI server
- Debugging workstation

---

## Development PC Responsibilities

```text
SLAM Toolbox
Nav2
RViz
YOLO
point cloud processing
rosbag
mapping
AI
```

---

# 20. Recommended Development PC

## Operating System

```text
Ubuntu 22.04 LTS
ROS 2 Humble
```

---

## Recommended Hardware

| Component | Recommendation |
|---|---|
| CPU | Modern multi-core CPU |
| RAM | 16–32 GB |
| GPU | NVIDIA RTX preferred |
| Storage | SSD |
| Networking | Ethernet preferred |

---

# 21. Distributed Compute Architecture

## Compute Distribution

| Device | Responsibilities |
|---|---|
| ESP32 | Motion + safety |
| Pi | Sensor bridge |
| Dev PC | SLAM + AI |

---

## Safety Philosophy

The robot must remain safe if:
- Wi-Fi disconnects
- Development PC crashes
- ROS graph fails

Critical rule:

```text
Development PC failure != dangerous robot
```

---

# 22. SLAM System Architecture

## Robot Classification

This robot is a:

```text
Hybrid 2D/3D Multi-Sensor SLAM Robot
```

using:
- 2D LiDAR
- RGB-D depth camera
- IMU
- Wheel odometry

---

# 23. LiDAR Problem Statement

The LiDAR is mounted low to the floor.

This causes detection of:
- Chair legs
- Boxes
- Shoes
- Furniture edges

as false walls.

---

# 24. SLAM Philosophy

Correct architecture:

```text
LiDAR for geometry
+
Depth camera for validation
+
Sensor fusion for classification
```

---

# 25. Recommended SLAM Stack

## Current

```text
slam_toolbox
```

Best for:
- Stable 2D mapping
- Nav2 integration
- Easier debugging

---

## Future

```text
RTAB-Map
```

Best for:
- RGB-D fusion
- Visual loop closure
- Semantic mapping

---

# 26. robot_localization

## Purpose

Fuses:
- Wheel encoders
- IMU
- Visual odometry later

into:

```text
/odom
```

---

## Importance

Reliable odometry improves:
- SLAM quality
- Navigation
- Loop closure
- Localization

---

# 27. Layered Sensor Fusion

## Layer 1 — Motion Fusion

Inputs:
- Encoders
- BNO055

Output:
```text
/odom
```

---

## Layer 2 — Mapping Fusion

Inputs:
- LiDAR
- RealSense depth

Goal:
```text
Wall validation
```

---

## Layer 3 — Semantic Fusion

Future systems:
- YOLO
- Object classification
- Semantic segmentation

Goal:
```text
"What is this obstacle?"
```

---

# 28. Permanent vs Temporary Obstacles

## Permanent Structure

Examples:
- Drywall
- Door frames

---

## Temporary Obstacles

Examples:
- Shoes
- Humans
- Chairs
- Boxes

The robot should distinguish between:
- structure
- clutter

---

# 29. Nav2 Costmap Architecture

## Static Layer

Source:
```text
SLAM Toolbox
```

Contains:
- Permanent structure

---

## Obstacle Layer

Source:
```text
LiDAR
```

Contains:
- Immediate collision geometry

---

## Voxel Layer

Source:
```text
RealSense
```

Contains:
- 3D obstacle information

---

## Semantic Layer (Future)

Source:
```text
YOLO
```

Contains:
- Semantic obstacle classification

---

# 30. TF2 Architecture

## Purpose

TF2 answers:

```text
"Where is everything relative to everything else?"
```

---

# 31. Core TF Tree

```text
map
 └── odom
      └── base_link
           ├── laser
           ├── imu_link
           ├── camera_link
           │     └── camera_depth_frame
           ├── left_wheel
           └── right_wheel
```

---

# 32. Critical TF Frames

| Frame | Purpose |
|---|---|
| map | Global environment |
| odom | Local motion estimate |
| base_link | Robot body |
| laser | LiDAR frame |
| camera_link | Camera frame |
| imu_link | IMU frame |

---

# 33. Critical TF Relationship

```text
map → odom → base_link
```

This transform chain is the heart of mobile robotics.

---

# 34. URDF Architecture

## Purpose

Defines:
- Robot geometry
- Sensor positions
- Frame hierarchy
- Wheel joints

---

## Key Frames

```text
base_link
laser
camera_link
imu_link
```

---

# 35. TF Debugging Tools

## View TF Tree

```bash
ros2 run tf2_tools view_frames
```

---

## Echo Transforms

```bash
ros2 run tf2_ros tf2_echo base_link laser
```

---

## RViz TF Display

Enable:
```text
TF display
```

inside RViz.

---

# 36. ROS 2 Topic Architecture

| Topic | Publisher | Consumer |
|---|---|---|
| /cmd_vel | Nav2 | serial bridge |
| /odom | robot_localization | Nav2 |
| /scan | RPLIDAR | slam_toolbox |
| /camera/depth/points | RealSense | voxel layer |
| /imu | ESP32 bridge | robot_localization |
| /battery_state | ESP32 bridge | monitoring nodes |

---

# 37. ROS Workspace Architecture

```text
robot_ws/
├── src/
│   ├── esp32_serial_bridge/
│   ├── robot_bringup/
│   ├── robot_description/
│   ├── robot_navigation/
│   ├── robot_slam/
│   └── robot_msgs/
```

---

# 38. Startup Architecture

## ESP32 Startup

```text
Initialize I2C
Initialize motors
Initialize telemetry
Initialize encoders
Enable safety systems
```

---

## Raspberry Pi Startup

```text
Launch sensor drivers
Launch serial bridge
Connect sensors
```

---

## Development PC Startup

```text
Launch Nav2
Launch SLAM
Launch RViz
Launch AI nodes
```

---

# 39. Networking Architecture

## Development

Preferred:
```text
Ethernet
```

---

## Mobile Operation

Preferred:
```text
Wi-Fi
```

---

# 40. Timing Requirements

| System | Target Rate |
|---|---|
| PID loop | 100 Hz |
| IMU | 50 Hz |
| LiDAR | 10 Hz |
| RealSense | 30 FPS |
| Nav2 control | 20 Hz |

---

# 41. Additional Recommended Sensors

## High Priority

- Cliff sensors
- Bumper switches
- Time-of-flight sensors

---

## Medium Priority

- Better IMU
- Battery fuel gauge
- Docking beacon

---

## Advanced

- Thermal camera
- UWB
- Microphone array

---

# 42. Known Engineering Challenges

## Low LiDAR Position

Problem:
- False wall generation

Mitigation:
- RealSense validation
- Layered costmaps

---

## TF Complexity

Problem:
- Sensor alignment issues

Mitigation:
- URDF
- RViz TF debugging
- Careful transform validation

---

## Distributed ROS Complexity

Problem:
- Networking instability
- Topic synchronization

Mitigation:
- Reliable networking
- Layered architecture
- Local safety systems

---

# 43. Development Workflow

## Recommended Learning Order

1. TF2
2. robot_localization
3. Nav2 costmaps
4. Point cloud processing
5. RTAB-Map

---

## Recommended Development Order

1. Reliable motor control
2. Stable odometry
3. Reliable SLAM
4. Correct TF tree
5. Nav2 integration
6. RealSense fusion
7. Semantic perception

---

# 44. Long-Term System Vision

The final robot architecture should resemble:

```text
Commercial autonomous mobile robot architecture
```

including:
- Distributed compute
- Embedded control
- Multi-sensor fusion
- Semantic perception
- Autonomous navigation
- Environmental monitoring

rather than a simple hobby robot.
