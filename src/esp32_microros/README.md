# esp32_microros

**ESP32-S3 + micro-ROS firmware for MyBot** — replaces the Arduino Nano motor controller and Pi-side BNO055/INA219 I2C nodes with a single ESP32-S3, publishing identical ROS 2 topics over micro-ROS serial transport.

[![Branch](https://img.shields.io/badge/branch-feature%2Fesp32--microros-blue)](https://github.com/Dasovon/MyBot/tree/feature/esp32-microros)
[![Framework](https://img.shields.io/badge/firmware-PlatformIO-purple?logo=platformio)](https://platformio.org/)
[![micro-ROS](https://img.shields.io/badge/micro--ROS-Humble-orange)](https://micro.ros.org/)
[![Board](https://img.shields.io/badge/board-ESP32--S3--DevKitC--1-red)](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/hw-reference/esp32s3/user-guide-devkitc-1.html)

> This is a feature branch of [MyBot](../../README.md). The Pi-side EKF, Nav2, and AMCL stack require **zero changes** — the ESP32 publishes the same topics the Arduino stack did.

---

## Hardware

| Component | Part | Notes |
|---|---|---|
| MCU | ESP32-S3-DevKitC-1 | on Lonely Binary expansion base |
| Motor driver | Adafruit TB6612FNG | Motor A = RIGHT, Motor B = LEFT |
| Motors | JGA25-371 DC12V 130RPM | 45:1 gear ratio, 11 PPR quadrature encoder |
| IMU | Adafruit BNO055 | I2C addr 0x28, NDOF fusion mode |
| Power monitor | Adafruit INA219 | I2C addr 0x40, shared bus with BNO055 |

---

## Bench Test Status

Work through the test sketches in order before using the full firmware.

| Sketch | What it tests | Status |
|---|---|---|
| [`test_bno055`](test/test_bno055/) | BNO055 + INA219 over I2C, WiFi OTA, telnet monitor | ✅ confirmed |
| [`test_encoders`](test/test_encoders/) | Quadrature encoder pulse counting and direction | ⬜ pending |
| [`test_motors`](test/test_motors/) | TB6612 motor control with safety checklist | ⬜ pending |
| [`test_microros`](test/test_microros/) | micro-ROS serial transport, heartbeat publisher | ⬜ pending |
| [`src/main.cpp`](src/main.cpp) | Full firmware: motors + encoders + PID + BNO055 + micro-ROS | ⬜ pending |

---

## Pin Mapping

### I2C (BNO055 + INA219) — ESP32-S3-DevKitC-1

> GPIO22 is not exposed on the DevKitC-1 board. Use GPIO8/9 instead of the ESP32 I2C defaults.

| Signal | GPIO | Addr |
|---|---|---|
| SDA | 8 | — |
| SCL | 9 | — |
| BNO055 | — | 0x28 |
| INA219 | — | 0x40 |

### TB6612 Motor Driver

| TB6612 | GPIO | Function |
|---|---|---|
| VCC | 3V3 | Logic supply (3.3V — no level shifter needed) |
| PWMA | 25 | RIGHT motor speed (PWM) |
| AIN2 | 26 | RIGHT motor direction B |
| AIN1 | 27 | RIGHT motor direction A |
| BIN1 | 32 | LEFT motor direction A |
| BIN2 | 33 | LEFT motor direction B |
| PWMB | 14 | LEFT motor speed (PWM) |
| STBY | — | Adafruit pullup — leave unwired |
| VM | 12V motor supply | separate from logic supply |

⚠️ First TB6612 unit damaged — 12V reached AIN1/BIN1 logic pins (max VCC+0.5V = 5.5V). Before installing replacement: verify VM wire has no breadboard bridge to AIN1 or BIN1.

### Quadrature Encoders

Input-only pins — encoder outputs are push-pull so no pull resistors needed.

| Signal | GPIO | Note |
|---|---|---|
| Left encoder A | 36 (VP) | interrupt capable |
| Left encoder B | 39 (VN) | input only |
| Right encoder A | 34 | interrupt capable |
| Right encoder B | 35 | input only |

ISR direction (matches validated Arduino firmware):
- Left: `A == B on CHANGE` → forward (+)
- Right: `A != B on CHANGE` → forward (+)

### Pins to avoid

| GPIO | Reason |
|---|---|
| 1, 3 | UART0 (USB serial) — used for micro-ROS transport |
| 6–11 | Internal SPI flash |
| 0, 2, 5, 12, 15 | Strapping pins — state matters at boot |
| 34–39 | Input only — fine for encoders, cannot drive output |

---

## Software Dependencies

- [PlatformIO](https://platformio.org/) (VS Code extension or CLI)
- micro-ROS for Arduino — Humble branch
- Adafruit BNO055 `^1.6.3`
- Adafruit Unified Sensor `^1.1.14`
- Adafruit INA219 `^1.2.1`
- TelnetStream `^1.3.0` (wireless serial monitor)

All declared in each sketch's `platformio.ini` — PlatformIO installs them automatically.

---

## Setup

### 1. credentials.h (gitignored — create manually)

Each test sketch needs a `src/credentials.h`:

```cpp
#pragma once
#define WIFI_SSID     "your-ssid"
#define WIFI_PASSWORD "your-password"
#define OTA_PASSWORD  "esp32ota"
```

### 2. First flash (USB)

```bash
cd src/esp32_microros/test/test_bno055   # or whichever sketch
pio run -e esp32-s3 --target upload
```

If upload fails: hold the **BOOT** button on the ESP32, click Upload, release when "Connecting…" appears. The CH340 driver must be installed (Lonely Binary expansion base uses CH340, not CP2102).

### 3. All future flashes (OTA — WiFi)

Once the board has WiFi credentials flashed, all updates go over the air:

```bash
pio run -e esp32-s3-ota --target upload
```

OTA target IP is `192.168.86.43` (`esp32-mybot.local`). Update `upload_port` in `platformio.ini` if the IP changes.

### 4. Wireless serial monitor

```bash
nc esp32-mybot.local 23          # Linux / macOS / Git Bash
telnet esp32-mybot.local         # alternative
# Windows: PuTTY → Connection Type: Raw, Port: 23
```

---

## Running Each Test Sketch

### test_bno055 ✅

Connects to WiFi, starts OTA + telnet monitor, then reads BNO055 (orientation, calibration) and INA219 (voltage, current) every second.

Expected serial output:
```
[WiFi] Connected — 192.168.86.43
[OTA] Ready
--- BNO055 ---
Euler: 12.4 / -0.3 / 0.1  Calib: S3 G0 A0 M0
--- INA219 ---
Bus: 11.44V  Shunt: 0.12mV  Current: 50.3mA
```

Calibration: move the sensor in a figure-8 pattern until `S3 G3 A3 M3`.

### test_encoders ⬜

Wire left and right encoders, then drive wheels by hand. Confirms:
- Pulse counts increment for forward rotation (positive)
- Left and right directions are independent
- No missed pulses at speed

### test_motors ⬜

⚠️ Run the on-screen safety checklist before powering motors. Confirms:
- Both motors spin in the correct direction (forward command = forward motion)
- PWM speed control responds correctly
- TB6612 does not overheat

### test_microros ⬜

Requires the micro-ROS agent running on the Pi:

```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
```

Confirms micro-ROS transport is alive by publishing a `/heartbeat` counter and subscribing to a test topic.

---

## Full Firmware (src/main.cpp)

Run after all four test sketches pass.

**Topics published:**

| Topic | Type | Rate |
|---|---|---|
| `/diff_cont/odom` | `nav_msgs/Odometry` | ~20 Hz |
| `/imu/imu` | `sensor_msgs/Imu` | ~20 Hz |
| `/battery_state` | `sensor_msgs/BatteryState` | 1 Hz |

**Topic subscribed:**

| Topic | Type |
|---|---|
| `/diff_cont/cmd_vel_unstamped` | `geometry_msgs/Twist` |

**On Pi — start the agent instead of the normal hardware nodes:**

```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
```

Then launch the rest of the stack normally (EKF, Nav2, RViz2) — no changes needed.

**To switch back to Arduino stack:** unplug ESP32, plug in Arduino, use `mybot-launch`.

---

## Verify topics are live

```bash
ros2 topic hz /diff_cont/odom        # expect ~20 Hz
ros2 topic hz /imu/imu               # expect ~20 Hz
ros2 topic echo /diff_cont/odom --once
```

---

## Related docs

- [MyBot README](../../README.md) — full robot stack overview
- [docs/pin-mapping.md](../../docs/pin-mapping.md) — complete Arduino + ESP32 wiring tables
- [CLAUDE.md](../../CLAUDE.md) — fix history, current status, Windows setup guide
