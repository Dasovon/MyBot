# MyBot

ROS 2 Humble differential drive robot stack for a Raspberry Pi + Arduino robot.

## Stack
- ROS 2 Humble on Raspberry Pi
- `ros2_control` + `diffdrive_arduino` hardware interface
- Arduino Nano motor controller via USB serial
- L298N motor driver
- Differential drive base

## Quick Start

```bash
source /opt/ros/humble/setup.bash
source ~/mybot_ws/install/setup.bash
ros2 launch articubot_one launch_robot.launch.py
```

## Workspace Structure

```
src/
├── articubot_one/      # Main robot package (launch, config, description)
├── ros_arduino_bridge/ # Arduino firmware
├── diffdrive_arduino/  # ros2_control hardware plugin (clone: joshnewans/diffdrive_arduino @ humble)
└── serial/             # Serial library (clone: joshnewans/serial @ newans_ros2)
```

See `CLAUDE.md` for full project documentation.
