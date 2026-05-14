# ESP32-S3-DevKitC-1

![ESP32-S3-DevKitC-1 pinout](esp32-s3-pinout.jpg)

**Role in MyBot:** Active production motor controller. Replaces the Arduino Nano + Pi-side BNO055/INA219. Handles motor control, quadrature encoders, IMU, and power monitoring over micro-ROS serial transport. Supports WiFi OTA firmware updates.

**Expansion base:** Lonely Binary ESP32-S3 expansion board.

---

## Specs

| Parameter | Value |
|---|---|
| SoC | ESP32-S3 (Xtensa LX7 dual-core @ 240MHz) |
| Flash | 8MB |
| PSRAM | 2MB |
| WiFi | 802.11 b/g/n (2.4GHz) |
| Bluetooth | BLE 5.0 |
| GPIO | 45 programmable pins |
| ADC | 20× channels (ADC1 and ADC2) |
| PWM | Any GPIO via LEDC peripheral |
| I2C | Any GPIO (hardware: default SDA=8, SCL=9 on DevKitC-1) |
| UART | Multiple (UART0 on GPIO43/44) |
| USB | USB-OTG on GPIO19/20 |
| Operating voltage | 3.3V logic |
| Input voltage | 5V via USB |
| Dimensions | 55.4 × 25.4 mm |

---

## Pinout

![ESP32-S3-DevKitC-1 pinout](esp32-s3-pinout.jpg)

### ⚠️ Important: GPIO22 is NOT exposed on the DevKitC-1

The DevKitC-1 board does not break out GPIO22 (standard ESP32 I2C SCL default). Use **GPIO8/9** for I2C instead — confirmed working on bench.

---

## MyBot pin assignments

### I2C bus (BNO055 + INA219)

| GPIO | Function | Device |
|---|---|---|
| **8** | SDA | BNO055 (0x28), INA219 (0x40) |
| **9** | SCL | BNO055 (0x28), INA219 (0x40) |

> Confirmed working on bench with both devices. GPIO8/9 are the default I2C pins for the ESP32-S3-DevKitC-1.

### TB6612 motor driver

Motor A (PWMA/AIN1/AIN2) = **RIGHT** | Motor B (PWMB/BIN1/BIN2) = **LEFT**

| GPIO | TB6612 | Function |
|---|---|---|
| 10 | PWMA | RIGHT motor speed (PWM, LEDC ch 0) |
| 11 | AIN1 | RIGHT motor direction A |
| 12 | AIN2 | RIGHT motor direction B |
| 13 | PWMB | LEFT motor speed (PWM, LEDC ch 1) |
| 14 | BIN1 | LEFT motor direction A |
| 15 | BIN2 | LEFT motor direction B |
| 3V3 | VCC | TB6612 logic supply (3.3V — no level shifter needed) |

LEDC uses the legacy Arduino ESP32 API (`ledcSetup` / `ledcAttachPin` / `ledcWrite`), channel 0 = right, channel 1 = left.

### Quadrature encoders

All encoder pins set `INPUT_PULLUP`. Interrupts fire on CHANGE of the A channel only.

| GPIO | Signal | Note |
|---|---|---|
| 40 | Left encoder A | `attachInterrupt` on CHANGE |
| 41 | Left encoder B | Read in ISR |
| 42 | Right encoder A | `attachInterrupt` on CHANGE |
| 39 | Right encoder B | Read in ISR |

ISR direction: Left `A == B on CHANGE` → forward (+) | Right `A != B on CHANGE` → forward (+)

Constants: `ENC_CPR = 1010`, `wheel_radius = 0.034 m`, `wheel_separation = 0.179 m`

### micro-ROS serial transport

ESP32-S3 native USB port (HWCDC) → USB cable → Pi `/dev/ttyACM0`.

Required build flag: `-DARDUINO_USB_CDC_ON_BOOT=1` (routes `Serial` to the native HWCDC controller on GPIO19/20).

WiFi is used **only** for OTA flashing and TelnetStream wireless monitoring — not for micro-ROS.

---

## Pins to avoid

| GPIO | Reason |
|---|---|
| 19, 20 | Native USB D−/D+ — HWCDC micro-ROS transport; leave for USB |
| 35, 36, 37 | Internal SPI flash/PSRAM — **do not use** on WROOM-1 modules |
| 43, 44 | UART0 TX/RX — not broken out on Lonely Binary board |
| 0, 45, 46 | Strapping pins — state matters at boot |
| 38 | RGB LED (v1.1 board) |
| 4, 5, 6, 7 | Not broken out on Lonely Binary board |
| 25, 26, 27, 32, 33 | Not broken out on Lonely Binary board |

---

## OTA flash workflow

### First flash (USB)

```bash
cd src/esp32_microros/test/test_bno055
pio run -e esp32-s3 --target upload
```

If upload fails: hold **BOOT** button → click Upload → release on "Connecting…"

### All subsequent flashes (WiFi OTA)

```bash
pio run -e esp32-s3-ota --target upload
```

OTA endpoint: `esp32-mybot.local` (IP: `192.168.86.43`)

### Wireless serial monitor

```bash
nc esp32-mybot.local 23        # netcat (Linux / Git Bash)
telnet esp32-mybot.local       # telnet
# Windows: PuTTY → Raw, port 23
```

---

## credentials.h (gitignored — create manually)

Required by every test sketch. Place at `src/esp32_microros/test/<sketch>/src/credentials.h`:

```cpp
#pragma once
#define WIFI_SSID     "your-ssid"
#define WIFI_PASSWORD "your-password"
#define OTA_PASSWORD  "esp32ota"
```

---

## PlatformIO environments

| Environment | Board | Use |
|---|---|---|
| `esp32-s3` | esp32-s3-devkitc-1 | USB flash (first time) |
| `esp32-s3-ota` | esp32-s3-devkitc-1 | OTA flash (all future) |

---

## micro-ROS topics published

| Topic | Type | Rate |
|---|---|---|
| `/diff_cont/odom` | `nav_msgs/Odometry` | 30 Hz |
| `/imu/imu` | `sensor_msgs/Imu` | 30 Hz |
| `/battery_state` | `sensor_msgs/BatteryState` | 1 Hz |

Subscribed: `/diff_cont/cmd_vel_unstamped` (`geometry_msgs/Twist`)

---

## micro-ROS agent (on Pi)

Built from source in `~/microros_ws` (`ros-humble-micro-ros-agent` not available in apt for arm64).

```bash
source /opt/ros/humble/setup.bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0
```

---

## Official docs

- User guide: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/
- ESP32-S3 datasheet: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
- PlatformIO board: https://docs.platformio.org/en/latest/boards/espressif32/esp32-s3-devkitc-1.html
- micro-ROS Arduino: https://github.com/micro-ROS/micro_ros_arduino
