# ESP32-S3-DevKitC-1

![ESP32-S3-DevKitC-1 pinout](esp32-s3-pinout.jpg)

**Role in MyBot:** Replacement for Arduino Nano + Pi-side BNO055/INA219 (branch: `feature/esp32-microros`). Handles motor control, quadrature encoders, IMU, and power monitoring over micro-ROS serial transport. Supports WiFi OTA firmware updates.

**Expansion base:** Lonely Binary ESP32-S3 expansion board (CH340 USB-serial chip).

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

| GPIO | TB6612 | Function |
|---|---|---|
| 25 | PWMA | RIGHT motor speed (PWM) |
| 26 | AIN2 | RIGHT motor direction B |
| 27 | AIN1 | RIGHT motor direction A |
| 32 | BIN1 | LEFT motor direction A |
| 33 | BIN2 | LEFT motor direction B |
| 14 | PWMB | LEFT motor speed (PWM) |
| 3V3 | VCC | TB6612 logic supply (3.3V — no level shifter needed) |

### Quadrature encoders

| GPIO | Signal | Note |
|---|---|---|
| 36 | Left encoder A | Input only, interrupt capable |
| 39 | Left encoder B | Input only |
| 34 | Right encoder A | Input only, interrupt capable |
| 35 | Right encoder B | Input only |

> Input-only pins (34–39) cannot drive output but are fine for encoder reading. Encoder outputs are push-pull — no pull resistors needed.

### micro-ROS serial transport

| GPIO | Function |
|---|---|
| 43 (TX) / 44 (RX) | UART0 — USB serial to Pi (micro-ROS) |

Connected via USB cable to Pi → `/dev/ttyUSB0`. Baud: 115200.

---

## Pins to avoid

| GPIO | Reason |
|---|---|
| 19, 20 | USB-OTG (used for programming on some configurations) |
| 35, 36, 37 | Internal SPI flash/PSRAM — **do not use** on WROOM-1 modules |
| 43, 44 | UART0 (TX/RX) — used by micro-ROS transport |
| 0, 45, 46 | Strapping pins — state matters at boot |
| 38 | RGB LED (v1.1 board) |

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
| `/diff_cont/odom` | `nav_msgs/Odometry` | ~20 Hz |
| `/imu/imu` | `sensor_msgs/Imu` | ~20 Hz |
| `/battery_state` | `sensor_msgs/BatteryState` | 1 Hz |

Subscribed: `/diff_cont/cmd_vel_unstamped` (`geometry_msgs/Twist`)

---

## micro-ROS agent (on Pi)

```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
```

---

## Official docs

- User guide: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/
- ESP32-S3 datasheet: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
- PlatformIO board: https://docs.platformio.org/en/latest/boards/espressif32/esp32-s3-devkitc-1.html
- micro-ROS Arduino: https://github.com/micro-ROS/micro_ros_arduino
