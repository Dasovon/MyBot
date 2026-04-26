# MyBot

ROS 2 Humble differential drive robot — Raspberry Pi 4 + Arduino Nano, with Nav2 autonomous navigation, RPLidar A1, BNO055 IMU, and Intel RealSense D435 depth camera.

Based on the [Articulated Robotics](https://articulatedrobotics.xyz/category/build-a-mobile-robot-with-ros/) tutorial series.

## Hardware

| Component | Details |
|-----------|---------|
| Compute | Raspberry Pi 4 |
| Motor controller | Arduino Nano (ros_arduino_bridge firmware) |
| Motor driver | Adafruit TB6612FNG |
| Motors | DC12V 130RPM JGA25-371 (45:1 gear ratio) |
| Lidar | RPLidar A1 M8 |
| IMU | Adafruit BNO055 (I2C, 0x28) |
| Camera | Intel RealSense D435 (RSUSB backend) |

## Architecture

Two-machine split: Pi runs hardware drivers, dev machine runs navigation and computation.

| Component | Machine |
|-----------|---------|
| ros2_control, motors, encoders | Pi |
| RPLidar, BNO055 IMU, RealSense | Pi |
| EKF (robot_localization) | Dev |
| Nav2 (AMCL, planner, controller) | Dev |
| RViz2 | Dev |

## Quick Start

```bash
# 1. Pi — hardware
ssh ryan@mybot "source ~/mybot_ws/install/setup.bash && ros2 launch articubot_one launch_robot.launch.py"

# 2. Dev — EKF
ros2 launch articubot_one dev_launch.py

# 3. Dev — localization
ros2 launch articubot_one localization_launch.py

# 4. Dev — Nav2
ros2 launch articubot_one navigation_launch.py

# 5. Dev — RViz2
rviz2
# Set Fixed Frame: map. Use 2D Pose Estimate to init AMCL, then Nav2 Goal to navigate.
```

## Workspace Structure

```
src/
├── articubot_one/      # Main robot package (launch, config, URDF/xacro)
├── ros_arduino_bridge/ # Arduino firmware (motor control, encoders, PID)
├── diffdrive_arduino/  # ros2_control hardware plugin  [branch: humble]
├── serial/             # Serial library  [branch: newans_ros2]
└── esp32_microros/     # Experimental: ESP32 + micro-ROS (branch: feature/esp32-microros)
```

## Docs

| File | Contents |
|------|---------|
| `CLAUDE.md` | Full project documentation, fix history, current status |
| `HARDWARE_MEMORY.md` | Wiring, pin mapping, block diagram |
| `docs/workflow.md` | Launch sequence, emergency stop, end-of-session routine |
| `docs/pin-mapping.md` | Pin tables for Arduino and ESP32 hardware paths |
| `docs/realsense-rsusb-setup.md` | RealSense RSUSB backend build procedure |
