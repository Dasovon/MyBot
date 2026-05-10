# MyBot Hardware

Complete hardware reference for the MyBot differential drive robot.

---

## System Overview

```
                        ┌─────────────────────────────┐
                        │       12V Battery            │
                        └────────────┬────────────────┘
                                     │
                        ┌────────────▼────────────────┐
                        │   DFR0205 Power Distribution │
                        │   3.6–25V in │ 5A / 25W max │
                        └──┬─────────────────────┬────┘
                           │ 5V regulated         │ 12V passthrough
                    ┌──────▼──────┐        ┌──────▼──────────┐
                    │ Raspberry   │        │ TB6612 VM        │
                    │ Pi 4 (5V)  │        │ (motor power)    │
                    └──┬──┬──┬───┘        └──────┬──────────┘
                USB-A  │  │  │                   │
          ┌────────────┘  │  └──────────┐  ┌─────▼─────┐
          │               │             │  │ TB6612FNG  │
   ┌──────▼──────┐  ┌─────▼─────┐      │  └──┬──────┬──┘
   │ Arduino     │  │ RPLidar   │      │     │      │
   │ Nano (USB)  │  │ (USB)     │      │  ┌──▼──┐ ┌─▼───┐
   └──────┬──────┘  └───────────┘      │  │ L   │ │ R   │
          │ UART 57600                  │  │ mot │ │ mot │
          │                             │  └──┬──┘ └──┬──┘
   ┌──────▼──────────────────────┐      │     │        │
   │ ros_arduino_bridge firmware │  I2C │ encoders  encoders
   │ PID + encoders + TB6612     │      │
   └─────────────────────────────┘      │
                                        │ I2C bus 1 (GPIO2/3)
                               ┌────────▼────────────────────┐
                               │  BNO055 (0x28)              │
                               │  INA219 (0x40) [temporary]  │
                               │  RealSense D435 (USB 3.2)   │
                               └─────────────────────────────┘
```

> **ESP32 migration in progress** (`feature/esp32-microros`): ESP32-S3 will replace the Arduino Nano and Pi-side I2C sensors. See [microcontroller/esp32-s3-devkitc-1.md](microcontroller/esp32-s3-devkitc-1.md).

---

## Component Index

| Component | File | Status |
|---|---|---|
| Raspberry Pi 4 | [compute/raspberry-pi-4.md](compute/raspberry-pi-4.md) | Production |
| Arduino Nano | [compute/arduino-nano.md](compute/arduino-nano.md) | Production |
| ESP32-S3-DevKitC-1 | [microcontroller/esp32-s3-devkitc-1.md](microcontroller/esp32-s3-devkitc-1.md) | In progress |
| Adafruit TB6612FNG | [motor-system/tb6612-driver.md](motor-system/tb6612-driver.md) | Production |
| JGA25-371 Motors | [motor-system/jga25-371-motors.md](motor-system/jga25-371-motors.md) | Production |
| Adafruit BNO055 | [sensors/bno055-imu.md](sensors/bno055-imu.md) | Production |
| Adafruit INA219 | [sensors/ina219-power-monitor.md](sensors/ina219-power-monitor.md) | Production |
| RPLidar A1 M8 | [sensors/rplidar-a1.md](sensors/rplidar-a1.md) | Production |
| Intel RealSense D435 | [camera/realsense-d435.md](camera/realsense-d435.md) | Production |
| DFRobot DFR0205 | [power/dfr0205.md](power/dfr0205.md) | Production |

---

## Power Budget

| Rail | Consumers | Peak draw |
|---|---|---|
| 12V (passthrough) | TB6612 VM (motors) | ~2A per motor under load |
| 5V (regulated) | Raspberry Pi 4 | up to 3A |
| Pi USB (5V) | Arduino Nano | ~50mA |
| Pi USB (5V) | RPLidar A1 | ~400mA |
| Pi USB (5V) | RealSense D435 | ~900mA |
| Pi USB (5V) | ESP32-S3 | ~250mA peak |
| Pi I2C 3.3V | BNO055 | ~12mA |
| Pi I2C 3.3V | INA219 | ~1mA |

> DFR0205 is rated 5A @ 5V / 25W max. Pi + USB peripherals approach this limit — avoid running all USB devices simultaneously at full load.

---

## CAD Renders

See [`mybot/`](mybot/) for chassis orthographic views and dimensions.

| File | View |
|---|---|
| [mybot1.png](mybot/mybot1.png) | Isometric |
| [mybot_front.png](mybot/mybot_front.png) | Front |
| [mybot_back.png](mybot/mybot_back.png) | Back |
| [mybot_left.png](mybot/mybot_left.png) | Left |
| [mybot_right.png](mybot/mybot_right.png) | Right |
| [mybot_top.png](mybot/mybot_top.png) | Top |
| [mybot_dim.png](mybot/mybot_dim.png) | Dimensions |
