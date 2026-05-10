# Raspberry Pi 4 Model B

![Raspberry Pi 4 GPIO](raspberry-pi-4-gpio.png)

**Role in MyBot:** Main compute board. Runs ROS 2 Humble, hardware drivers (rplidar, bno055, realsense2_camera, ros2_control), and receives navigation commands from the dev machine over WiFi.

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
| GPIO2 (SDA1) | 3 | I2C bus 1 data | BNO055 SDA, INA219 SDA |
| GPIO3 (SCL1) | 5 | I2C bus 1 clock | BNO055 SCL, INA219 SCL |
| 3.3V | 1 | Logic supply | BNO055 Vin, INA219 Vin |
| 5V | 2 | — | (not used externally) |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 | Ground | Common ground |

### USB port assignments

| USB port | Device | Baud / Protocol |
|---|---|---|
| USB 3.0 | Intel RealSense D435 | USB 3.2 |
| USB 2.0 | Arduino Nano (via CH340) | UART 57600 → `/dev/arduino` |
| USB 2.0 | RPLidar A1 (via CP2102) | UART 115200 → `/dev/rplidar` |
| USB 2.0 | ESP32-S3 (when in use) | UART 115200 → micro-ROS |

---

## udev symlinks

```
/dev/arduino  →  ttyUSB* (CH340,  1a86:7523)
/dev/rplidar  →  ttyUSB* (CP2102, 10c4:ea60)
```

Rules file: `/etc/udev/rules.d/99-mybot.rules`

---

## I2C devices on bus 1

```bash
sudo i2cdetect -y 1
```

| Address | Device |
|---|---|
| 0x28 | Adafruit BNO055 IMU |
| 0x40 | Adafruit INA219 power monitor |

---

## Power

- Input: 5V USB-C from DFR0205 regulated output
- Minimum current: 3A recommended (Pi 4 can draw up to 3A under full load with USB peripherals)
- USB port budget: ~1.2A total across all USB 2.0 ports; USB 3.0 ports provide higher current for RealSense

---

## ROS 2 setup

- Workspace: `~/mybot_ws`
- Launch: `mybot-launch` (bash alias — clears serial ports, then launches `launch_robot.launch.py`)
- Nodes running on Pi: `robot_state_publisher`, `ros2_control_node`, `diff_cont`, `joint_broad`, `twist_mux`, `rplidar_composition`, `bno055`, `realsense2_camera_node`, `ina219_node`

---

## Official docs

- Product page: https://www.raspberrypi.com/products/raspberry-pi-4-model-b/
- GPIO reference: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio
- Pinout interactive: https://pinout.xyz/
