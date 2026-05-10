# Adafruit TB6612FNG Motor Driver

![TB6612 Breakout](https://cdn-shop.adafruit.com/970x728/2448-07.jpg)

**Role in MyBot:** Dual H-bridge motor driver. Receives PWM + direction signals from the Arduino Nano (or ESP32-S3) and drives both DC gear motors. Replaces the L298N used in earlier builds.

---

## Specs

| Parameter | Value |
|---|---|
| IC | Toshiba TB6612FNG |
| Motor supply (VM) | 4.5V – 13.5V |
| Logic supply (VCC) | 2.7V – 5.5V |
| Continuous output current | 1.2A per channel |
| Peak output current | 3.2A per channel |
| PWM frequency | up to 100 kHz |
| Standby current | 0.1 µA |
| Dimensions (Adafruit breakout) | 26.7 × 19.3 mm |

---

## Pinout

![TB6612 Pinout](https://cdn-learn.adafruit.com/assets/assets/000/102/733/medium800/adafruit_products_TB6612_top.jpg)

```
              Adafruit TB6612FNG Breakout
         ┌─────────────────────────────────┐
    VM  ─┤  Motor voltage (4.5–13.5V)      │
   VCC  ─┤  Logic voltage (2.7–5.5V)       │
   GND  ─┤  Ground                         │
  STBY  ─┤  Standby (HIGH=run, LOW=stop)   │
         │                                 │
  AIN1  ─┤  Motor A direction 1            │──┐  Motor A
  AIN2  ─┤  Motor A direction 2            │  ├─ (RIGHT)
  PWMA  ─┤  Motor A speed (PWM)            │  │
  MOTOA ─┤  Motor A output +               │──┘
  MOTOA ─┤  Motor A output −               │
         │                                 │
  BIN1  ─┤  Motor B direction 1            │──┐  Motor B
  BIN2  ─┤  Motor B direction 2            │  ├─ (LEFT)
  PWMB  ─┤  Motor B speed (PWM)           │  │
  MOTOB ─┤  Motor B output +               │──┘
  MOTOB ─┤  Motor B output −               │
         └─────────────────────────────────┘
```

---

## Direction truth table

| xIN1 | xIN2 | Result |
|---|---|---|
| HIGH | LOW | Forward (CW) |
| LOW | HIGH | Reverse (CCW) |
| LOW | LOW | Coast (free spin) |
| HIGH | HIGH | Brake (short circuit stop) |

---

## MyBot wiring — Arduino Nano stack

Motor A = **RIGHT** motor | Motor B = **LEFT** motor

| TB6612 Pin | Arduino Pin | Function |
|---|---|---|
| VM | 12V (from DFR0205 passthrough) | Motor power |
| VCC | 5V | Logic supply (must match MCU voltage) |
| GND | GND | Common ground |
| PWMA | D5 | RIGHT motor speed (PWM) |
| AIN2 | D6 | RIGHT motor direction B |
| AIN1 | D7 | RIGHT motor direction A |
| BIN1 | D8 | LEFT motor direction A |
| BIN2 | D9 | LEFT motor direction B |
| PWMB | D10 | LEFT motor speed (PWM) |
| STBY | — | Adafruit onboard 10kΩ pullup — leave unwired (defaults HIGH = enabled) |

**Motor A outputs** → RIGHT motor (Red = +, White = −)
**Motor B outputs** → LEFT motor (Red = +, White = −)

---

## MyBot wiring — ESP32-S3 stack

| TB6612 Pin | ESP32 GPIO | Function |
|---|---|---|
| VM | 12V (from DFR0205 passthrough) | Motor power |
| VCC | 3V3 | Logic supply (3.3V — no level shifter needed) |
| GND | GND | Common ground |
| PWMA | 25 | RIGHT motor speed (PWM) |
| AIN2 | 26 | RIGHT motor direction B |
| AIN1 | 27 | RIGHT motor direction A |
| BIN1 | 32 | LEFT motor direction A |
| BIN2 | 33 | LEFT motor direction B |
| PWMB | 14 | LEFT motor speed (PWM) |
| STBY | — | Leave unwired |

---

## ⚠️ Damage warning

**First unit was destroyed** (2026-04-25): the 12V VM wire accidentally bridged to AIN1/BIN1 logic pins on the breadboard. Maximum safe logic input is VCC + 0.5V = **5.5V** (Arduino stack) or **3.8V** (ESP32 stack). 12V destroyed the input gates instantly.

**Symptom:** xIN1 pins read ~2V when driven HIGH — below logic threshold — CW direction non-functional. xIN2 pins unaffected.

**Before installing any replacement chip:** verify VM wire has no breadboard bridge to any signal pin.

---

## Firmware

```cpp
// ROSArduinoBridge — motor_driver.h
#define TB6612_MOTOR_DRIVER

// Pin assignments (Motor A = RIGHT, Motor B = LEFT)
#define RIGHT_MOTOR_ENABLE   5   // PWMA
#define RIGHT_MOTOR_FORWARD  6   // AIN2
#define RIGHT_MOTOR_BACKWARD 7   // AIN1
#define LEFT_MOTOR_ENABLE    10  // PWMB
#define LEFT_MOTOR_FORWARD   9   // BIN2
#define LEFT_MOTOR_BACKWARD  8   // BIN1
```

---

## Official docs

- Adafruit product page: https://www.adafruit.com/product/2448
- Adafruit learn guide: https://learn.adafruit.com/adafruit-tb6612-h-bridge-dc-stepper-motor-driver-breakout
- TB6612FNG datasheet: https://cdn-shop.adafruit.com/datasheets/TB6612FNG_v8_en.pdf
