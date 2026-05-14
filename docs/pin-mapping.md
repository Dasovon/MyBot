# Pin Mapping

## Current Stack — Arduino Nano → Adafruit TB6612

Motor A (PWMA/AIN1/AIN2) drives the **RIGHT** motor.
Motor B (PWMB/BIN1/BIN2) drives the **LEFT** motor.

| TB6612 Pin | Arduino Pin | Function |
|------------|-------------|----------|
| VCC | 5V | Logic supply (sets threshold for all signal pins) |
| VM | 12V motor supply | Motor power |
| PWMA | D5 | Right motor speed (PWM) |
| AIN1 | D7 | Right motor **FORWARD** |
| AIN2 | D6 | Right motor **BACKWARD** |
| BIN1 | D8 | Left motor **FORWARD** |
| BIN2 | D9 | Left motor **BACKWARD** |
| PWMB | D10 | Left motor speed (PWM) |
| STBY | not wired | Adafruit breakout has onboard pullup — defaults HIGH (enabled) |
| GND | GND | Common ground |

Motor output wiring (critical — do NOT use GND pad between sections):
- Right motor wires → **AO1 + AO2** pads
- Left motor wires  → **BO1 + BO2** pads

Firmware define: `TB6612_MOTOR_DRIVER`
File: `src/ros_arduino_bridge/ROSArduinoBridge/ROSArduinoBridge.ino`

Firmware pin defines (motor_driver.h):
```
RIGHT_MOTOR_ENABLE   = 5   // PWMA
RIGHT_MOTOR_FORWARD  = 7   // AIN1
RIGHT_MOTOR_BACKWARD = 6   // AIN2
LEFT_MOTOR_ENABLE    = 10  // PWMB
LEFT_MOTOR_FORWARD   = 8   // BIN1
LEFT_MOTOR_BACKWARD  = 9   // BIN2
```

TB6612 direction truth table:
| xIN1 | xIN2 | Result |
|------|------|--------|
| HIGH | LOW  | Forward (OUT1=VM, OUT2=GND) |
| LOW  | HIGH | Reverse (OUT1=GND, OUT2=VM) |
| LOW  | LOW  | Coast |
| HIGH | HIGH | Brake |

Validated 2026-05-03: teleop `i`=forward, `j`/`l`=turn correctly.

### Encoder Pins (Arduino)

| Signal | Arduino Pin | Note |
|--------|-------------|------|
| Left encoder A | D2 | INT0 — hardware interrupt |
| Left encoder B | D4 | |
| Right encoder A | D3 | INT1 — hardware interrupt |
| Right encoder B | D12 | |

ISR direction (validated 2026-05-03):
- Left:  `A == B on CHANGE` → increment (forward = +)
- Right: `A != B on CHANGE` → increment (forward = +)

Velocity limits (my_controllers.yaml):
- linear max:  ±0.3 m/s
- angular max: ±3.35 rad/s  (= 2 × 0.3 / 0.179 — equal wheel speed at full linear and full spin)

Velocity tracking (validated 2026-05-03, 3 runs, robot free to move on floor):
  Speed   Forward  Spin
  25%     83%      69%   ← motor deadband at low PWM, normal
  50%     92%      88%
  75%     97%      93%
  100%    98%      96%
Left/right within 0.002 m/s. Operating range (50–100%) tracks 88–98% for both modes.

---

## Current Stack — BNO055 → Raspberry Pi

| BNO055 Pin | Pi Pin | Note |
|------------|--------|------|
| Vin | 3.3V (pin 1) | Adafruit breakout has onboard regulator |
| GND | GND (pin 6) | |
| SDA | GPIO2 / SDA (pin 3) | I2C bus 1 |
| SCL | GPIO3 / SCL (pin 5) | I2C bus 1 |
| ADR | not wired | → address 0x28 |
| RST, INT, PS0, PS1 | not wired | |

I2C address: `0x28`
Config: `src/articubot_one/config/bno055_params.yaml`

---

## ESP32-S3 Stack — Lonely Binary Expansion Base (branch: feature/esp32-microros)

Hardware: ESP32-S3-DevKitC-1 mounted on Lonely Binary ESP32-S3 Expansion Base.
All GPIO 3.3V logic. TB6612 VCC → 3V3 (no level shifter needed).

⚠️ GPIO NOT broken out on Lonely Binary board: 4, 5, 6, 7, 25, 26, 27, 32, 33, 43, 44 and most high-numbered pads.

Board pin rows:
- Left side:  3V3, GND, 15, 16, 17, 18, 8, 3, 46, 9, 10, 11, 12, 13, 14
- Right side: 3V3, GND, 1, 2, 42, 41, 40, 39, 38, 37, 36, 35, 0, 45, 48, 47, 21, 20, 19

### ESP32-S3 → TB6612 (confirmed working)

Motor A (PWMA/AIN1/AIN2) = **RIGHT** | Motor B (PWMB/BIN1/BIN2) = **LEFT**

| TB6612 Pin | ESP32-S3 GPIO | Board side | Function |
|------------|---------------|------------|----------|
| VCC | 3V3 | Left | Logic supply |
| VM | 12V motor supply | — | Motor power |
| PWMA | 10 | Left | Right motor speed (PWM, LEDC ch 0) |
| AIN1 | 11 | Left | Right motor direction A |
| AIN2 | 12 | Left | Right motor direction B |
| PWMB | 13 | Left | Left motor speed (PWM, LEDC ch 1) |
| BIN1 | 14 | Left | Left motor direction A |
| BIN2 | 15 | Left | Left motor direction B |
| STBY | not wired | — | Adafruit breakout pullup — defaults enabled |
| GND | GND | Left | Common ground |

LEDC API (ESP32-S3 Arduino framework uses legacy API):
```cpp
ledcSetup(ch, 1000, 8);   // channel, freq Hz, resolution bits
ledcAttachPin(pin, ch);
ledcWrite(ch, duty);       // 0–255
```

### ESP32-S3 → Encoders (confirmed working)

Pins pulled up with `INPUT_PULLUP`. Both interrupt on CHANGE of the A channel only.

| Signal | GPIO | Board side | Note |
|--------|------|------------|------|
| Left enc A | 40 | Right | `attachInterrupt` on CHANGE |
| Left enc B | 41 | Right | Read in ISR |
| Right enc A | 42 | Right | `attachInterrupt` on CHANGE |
| Right enc B | 39 | Right | Read in ISR |

ISR direction (validated):
- Left:  `A == B on CHANGE` → forward (+)
- Right: `A != B on CHANGE` → forward (+)

Constants: `ENC_CPR = 1010`, `wheel_radius = 0.034 m`

### ESP32-S3 → BNO055 + INA219 (confirmed working)

Both devices share the I2C bus on GPIO 8/9.

| Device | Pin | ESP32-S3 GPIO | Board side |
|--------|-----|---------------|------------|
| BNO055 | Vin | 3V3 | Left |
| BNO055 | GND | GND | Left |
| BNO055 | SDA | 8 | Left |
| BNO055 | SCL | 9 | Left |
| BNO055 | ADR | not wired | — → address 0x28 |
| INA219 | Vin | 3V3 | Left |
| INA219 | GND | GND | Left |
| INA219 | SDA | 8 | Left |
| INA219 | SCL | 9 | Left |
| INA219 | A0/A1 | not wired | — → address 0x40 |

### micro-ROS Transport (confirmed working)

ESP32-S3 connected to Pi via native USB port. The native USB JTAG controller (HWCDC) appears as `/dev/ttyACM0` on the Pi.

Required build flag: `build_flags = -DARDUINO_USB_CDC_ON_BOOT=1`
(The board definition already sets `ARDUINO_USB_MODE=1` for HWCDC; CDC_ON_BOOT routes `Serial` to it.)

WiFi is used only for OTA flashing and TelnetStream wireless monitoring — NOT for micro-ROS.

Agent setup on Pi (built from source in `~/microros_ws`):
```bash
source /opt/ros/humble/setup.bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0
```

Topics published by ESP32: `/diff_cont/odom`, `/imu/imu`, `/battery_state`
Topic subscribed by ESP32: `/diff_cont/cmd_vel_unstamped`

### ESP32-S3 GPIO Quick Reference — Pins to Avoid (Lonely Binary board)

| GPIO | Reason |
|------|--------|
| 4, 5, 6, 7 | Not broken out on Lonely Binary board |
| 25, 26, 27, 32, 33 | Not broken out on Lonely Binary board |
| 43, 44 | UART0 TX/RX — not broken out |
| 19, 20 | Native USB D−/D+ — leave for USB |
| 45, 46 | Strapping pins — avoid signals driven at boot |
| 0 | Strapping pin (boot mode) |
