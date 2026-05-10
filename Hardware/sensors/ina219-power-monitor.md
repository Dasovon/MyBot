# Adafruit INA219 Current Sensor

![INA219 Breakout](https://cdn-shop.adafruit.com/970x728/904-07.jpg)

**Role in MyBot:** High-side DC current and voltage monitor. Measures battery bus voltage and current draw, publishes `/battery_state` at 1Hz. Currently connected to Pi I2C — will move to ESP32-S3 I2C bus in the ESP32 migration.

---

## Specs

| Parameter | Value |
|---|---|
| IC | Texas Instruments INA219B |
| Measurement | High-side voltage + current via I2C |
| Voltage range | 0 – 26V DC (bus voltage) |
| Current range (default) | ±3.2A (0.8mA resolution) |
| Current range (min gain) | ±400mA (0.1mA resolution) |
| Sense resistor | 0.1Ω, 1% precision (onboard) |
| Interface | I2C |
| I2C base address | 0x40 |
| Additional addresses | 0x41, 0x44, 0x45 (via A0/A1 pads) |
| Logic voltage | 3.3V – 5V |
| Precision | 1% |
| Dimensions | 25.7 × 17.9 mm |

---

## Pinout

```
        Adafruit INA219 Breakout
   ┌─────────────────────────────┐
   │  VCC  │ Logic power 3–5V   │
   │  GND  │ Ground              │
   │  SDA  │ I2C data            │
   │  SCL  │ I2C clock           │
   │  VIN+ │ High-side + input   │──→ Battery +
   │  VIN− │ High-side − input   │──→ Load +
   └─────────────────────────────┘
```

Current flows **from VIN+ through the 0.1Ω shunt resistor to VIN−**.
Place in series with the positive supply rail to the load being measured.

---

## I2C address configuration

Solder bridge the A0/A1 pads on the PCB to change address:

| A1 | A0 | I2C Address |
|---|---|---|
| open | open | **0x40** (default — MyBot) |
| open | bridge | 0x41 |
| bridge | open | 0x44 |
| bridge | bridge | 0x45 |

Up to 4 INA219 boards can share one I2C bus.

---

## MyBot wiring — Raspberry Pi (current)

| INA219 Pin | Raspberry Pi | Note |
|---|---|---|
| VCC | 3.3V (pin 1) | |
| GND | GND (pin 6) | |
| SDA | GPIO2 / SDA1 (pin 3) | I2C bus 1 |
| SCL | GPIO3 / SCL1 (pin 5) | I2C bus 1 |
| VIN+ | Battery positive rail | high side in |
| VIN− | Load positive (after shunt) | high side out |

Shares bus with BNO055 (addr 0x28). INA219 is at 0x40.

## MyBot wiring — ESP32-S3 (feature branch)

| INA219 Pin | ESP32 GPIO | Note |
|---|---|---|
| VCC | 3V3 | |
| GND | GND | |
| SDA | GPIO8 | Shared with BNO055 — confirmed working |
| SCL | GPIO9 | |
| VIN+/VIN− | Battery rail | same as above |

Confirmed on bench: INA219 at 0x40 reads 11.4V / ~50mA simultaneously with BNO055 at 0x28.

---

## Verify on Pi

```bash
sudo i2cdetect -y 1                  # confirm 0x40 present
ros2 topic echo /battery_state       # check voltage/current data
```

---

## Measurement at time of bench test

| Measurement | Value |
|---|---|
| Bus voltage | 11.4V |
| Current | ~50mA |
| Load | ESP32-S3 + sensors (no motors) |

---

## Official docs

- Adafruit product page: https://www.adafruit.com/product/904
- Adafruit learn guide: https://learn.adafruit.com/adafruit-ina219-current-sensor-breakout
- INA219 datasheet: https://cdn-shop.adafruit.com/datasheets/ina219.pdf
