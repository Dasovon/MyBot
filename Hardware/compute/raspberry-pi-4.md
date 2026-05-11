# Raspberry Pi 4 Model B

![Raspberry Pi 4 GPIO](raspberry-pi-4-gpio.png)

**Role in MyBot:** Main compute board. Runs ROS 2 Humble, hardware drivers (micro_ros_agent, rplidar, realsense2_camera), and receives navigation commands from the dev machine over WiFi.

---

## Specs

| Parameter | Value |
|---|---|
| SoC | Broadcom BCM2711, Quad-core Cortex-A72 @ 1.8GHz |
| RAM | 4GB LPDDR4-3200 |
| OS | Ubuntu 22.04 LTS (64-bit) |
| GPIO | 40-pin header |
| USB | 2× USB 3.0, 2× USB 2.0 |
| Power input | 5V DC via USB-C (3A minimum) |
| Networking | 802.11ac WiFi, Bluetooth 5.0, Gigabit Ethernet |
| I2C | I2C bus 1 on GPIO2 (SDA) / GPIO3 (SCL) |

---

## GPIO Pinout

![Raspberry Pi 4 GPIO pinout](raspberry-pi-4-gpio.png)

### Key pins used by MyBot

| GPIO | Pin # | Function | Connected to |
|---|---|---|---|
| 5V | 2 | Power | (USB-C from DFR0205) |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 | Ground | Common ground |

> BNO055 and INA219 are now on the ESP32-S3 I2C bus (GPIO8/9), not the Pi. Pi I2C pins are unused.

### USB port assignments

| USB port | Device | Baud / Protocol |
|---|---|---|
| USB 3.0 | Intel RealSense D435 | USB 3.2 |
| USB 2.0 | ESP32-S3 (HWCDC native USB) | micro-ROS → `/dev/ttyACM0` |
| USB 2.0 | RPLidar A1 (via CP2102) | UART 115200 → `/dev/rplidar` |

---

## udev symlinks

```
/dev/rplidar  →  ttyUSB* (CP2102, 10c4:ea60)
```

Rules file: `/etc/udev/rules.d/99-mybot.rules`

> `/dev/ttyACM0` is the ESP32-S3 HWCDC device — no udev symlink needed (it always appears as `ttyACM0` when it is the only HWCDC device).

---

## Power

- Input: 5V USB-C from DFR0205 regulated output
- Minimum current: 3A recommended (Pi 4 can draw up to 3A under full load with USB peripherals)
- USB port budget: ~1.2A total across all USB 2.0 ports; USB 3.0 ports provide higher current for RealSense

---

## ROS 2 setup

- Workspace: `~/mybot_ws`
- Launch: `mybot-launch` (bash alias — launches `launch_robot.launch.py`)
- micro-ROS agent workspace: `~/microros_ws` (built from source — not in apt for arm64)
- Nodes running on Pi: `robot_state_publisher`, `micro_ros_agent`, `twist_mux`, `rplidar_composition`, `realsense2_camera_node`

> EKF (`robot_localization`) and Nav2 run on the dev machine, not the Pi.

---

## Official docs

- Product page: https://www.raspberrypi.com/products/raspberry-pi-4-model-b/
- GPIO reference: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio
- Pinout interactive: https://pinout.xyz/
