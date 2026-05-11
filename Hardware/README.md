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
   │ ESP32-S3    │  │ RPLidar   │      │     │      │
   │ (HWCDC USB) │  │ (USB)     │      │  ┌──▼──┐ ┌─▼───┐
   └──────┬──────┘  └───────────┘      │  │ L   │ │ R   │
          │ micro-ROS /dev/ttyACM0     │  │ mot │ │ mot │
          │                             │  └──┬──┘ └──┬──┘
   ┌──────▼──────────────────────┐      │     │        │
   │ micro_ros_agent             │  GPIO│  encoders  encoders
   │ /diff_cont/odom 30Hz        │  10-15(TB6612)
   │ /imu/imu 30Hz               │  40/41/42/39(enc)
   │ /battery_state 1Hz          │
   └─────────────────────────────┘
   
   ESP32-S3 I2C (GPIO8/9):
   ┌────────────────────────────┐
   │  BNO055 (0x28)             │
   │  INA219 (0x40)             │
   └────────────────────────────┘

   RealSense D435 → Pi USB 3.0 (separate)
```

---

## Component Index

| Component | File | Status |
|---|---|---|
| Raspberry Pi 4 | [compute/raspberry-pi-4.md](compute/raspberry-pi-4.md) | Production |
| ESP32-S3-DevKitC-1 | [microcontroller/esp32-s3-devkitc-1.md](microcontroller/esp32-s3-devkitc-1.md) | Production |
| Arduino Nano | [compute/arduino-nano.md](compute/arduino-nano.md) | Retired (replaced by ESP32-S3) |
| Adafruit TB6612FNG | [motor-system/tb6612-driver.md](motor-system/tb6612-driver.md) | Production |
| JGA25-371 Motors | [motor-system/jga25-371-motors.md](motor-system/jga25-371-motors.md) | Production |
| Adafruit BNO055 | [sensors/bno055-imu.md](sensors/bno055-imu.md) | Production (on ESP32 I2C) |
| Adafruit INA219 | [sensors/ina219-power-monitor.md](sensors/ina219-power-monitor.md) | Production (on ESP32 I2C) |
| RPLidar A1 M8 | [sensors/rplidar-a1.md](sensors/rplidar-a1.md) | Production |
| Intel RealSense D435 | [camera/realsense-d435.md](camera/realsense-d435.md) | Production |
| DFRobot DFR0205 | [power/dfr0205.md](power/dfr0205.md) | Production |

---

## Power Budget

| Rail | Consumers | Peak draw |
|---|---|---|
| 12V (passthrough) | TB6612 VM (motors) | ~2A per motor under load |
| 5V (regulated) | Raspberry Pi 4 | up to 3A |
| Pi USB (5V) | ESP32-S3-DevKitC-1 | ~250mA peak |
| Pi USB (5V) | RPLidar A1 | ~400mA |
| Pi USB 3.0 (5V) | RealSense D435 | ~900mA |
| ESP32 3.3V | BNO055 | ~12mA |
| ESP32 3.3V | INA219 | ~1mA |

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
