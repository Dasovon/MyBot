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

## Experimental Stack — ESP32-DevKitC (branch: feature/esp32-microros)

All ESP32 GPIO are 3.3V logic. TB6612 VCC → 3V3 (no level shifter needed).
Pins GPIO6–11 are internal flash — never use. GPIO1/3 are USB serial (micro-ROS transport).

### ESP32 → TB6612

| TB6612 Pin | ESP32 GPIO | Function |
|------------|------------|----------|
| VCC | 3V3 | Logic supply |
| VM | 12V motor supply | Motor power |
| PWMA | GPIO25 | Right motor speed (PWM) |
| AIN2 | GPIO26 | Right motor direction B |
| AIN1 | GPIO27 | Right motor direction A |
| BIN1 | GPIO32 | Left motor direction A |
| BIN2 | GPIO33 | Left motor direction B |
| PWMB | GPIO14 | Left motor speed (PWM) |
| STBY | not wired | Onboard pullup — defaults enabled |
| GND | GND | Common ground |

Note: GPIO14 is a strapping pin (JTAG TMS) but safe for PWM at runtime.

### ESP32 → BNO055

| BNO055 Pin | ESP32 GPIO | Note |
|------------|------------|------|
| Vin | 3V3 | Adafruit board has onboard regulator + level shifters |
| GND | GND | |
| SDA | GPIO21 | I2C default SDA |
| SCL | GPIO22 | I2C default SCL |
| ADR | not wired | → address 0x28 |

### Encoder Pins (ESP32)

Input-only pins used — no internal pullup/pulldown, but encoder outputs are push-pull so none needed.

| Signal | ESP32 GPIO | Note |
|--------|------------|------|
| Left encoder A | GPIO36 (VP) | Input only, interrupt capable |
| Left encoder B | GPIO39 (VN) | Input only |
| Right encoder A | GPIO34 | Input only, interrupt capable |
| Right encoder B | GPIO35 | Input only |

ISR direction (matches validated Arduino firmware):
- Left: `A == B on CHANGE` → forward (+)
- Right: `A != B on CHANGE` → forward (+)

### micro-ROS Transport

USB serial (GPIO1/3, UART0) at 115200 baud.

Agent command on Pi:
```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
```

Topics published by ESP32: `/diff_cont/odom`, `/imu/imu`
Topic subscribed by ESP32: `/diff_cont/cmd_vel_unstamped`

---

## ESP32 GPIO Quick Reference — Pins to Avoid

| GPIO | Reason to avoid |
|------|----------------|
| 1, 3 | UART0 (USB serial) — used by micro-ROS transport |
| 6–11 | Internal SPI flash — do not use |
| 34–39 | Input only — cannot be outputs (fine for encoders) |
| 0, 2, 5, 12, 15 | Strapping pins — state matters at boot; avoid for signals that are driven at startup |
| 16, 17 | Used by PSRAM on WROVER modules — avoid if using WROVER |
