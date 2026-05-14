# Waveshare 2.42inch OLED Module

**Role in MyBot:** Robot status dashboard mounted on the chassis — shows battery voltage, velocity, estimated pose, and connection state at a glance without needing a laptop.

---

## Specs

| Parameter | Value |
|---|---|
| Display size | 2.42 inch diagonal |
| Resolution | 128 × 64 pixels |
| Controller IC | Solomon SSD1309 |
| Display color | White (also available: yellow) |
| Interface | SPI (default from factory) or I2C (resistor swap) |
| Connector | MX1.25 7-pin |
| Logic voltage | 3.3V or 5V (onboard XC6206 regulator → 3.3V to SSD1309) |
| Active display area | 55.01 × 27.49 mm |
| Module dimensions | 61.50 × 39.50 mm |
| Pixel size | 0.4 × 0.4 mm |

---

## Pin Descriptions (MX1.25 7-pin connector)

| Pin | Name | Function |
|---|---|---|
| 1 | VCC | Power input — 3.3V or 5V |
| 2 | GND | Ground |
| 3 | DIN | SPI: MOSI data in / I2C: SDA |
| 4 | CLK | SPI: SCLK clock / I2C: SCL |
| 5 | CS | SPI: chip select (active LOW) / I2C: tie to GND |
| 6 | DC | SPI: data/command select / I2C: address select (LOW=0x3C, HIGH=0x3D) |
| 7 | RST | Hardware reset (active LOW) — can tie to VCC if software reset not needed |

---

## Interface Selection

The module ships in **4-wire SPI mode** by default. Two 0Ω resistors on the PCB select the mode:

| Mode | Resistor position | Notes |
|---|---|---|
| SPI (default) | R1, R4 populated | DIN=MOSI, CLK=SCLK, CS and DC active |
| I2C | R2, R3 populated | DIN=SDA, CLK=SCL, CS→GND, DC sets address |

To switch to I2C: move R1→R2 and R4→R3 (requires soldering iron + steady hand, or order pre-configured).

---

## MyBot Wiring — Raspberry Pi, I2C mode (recommended)

Pi I2C bus 1 is completely free after the ESP32 migration (BNO055 and INA219 moved to ESP32). The display plugs straight into the existing I2C header.

| Module Pin | Signal | Raspberry Pi | Pi Physical Pin |
|---|---|---|---|
| VCC | 3.3V | 3.3V power | Pin 1 |
| GND | GND | Ground | Pin 6 |
| DIN | SDA | GPIO2 / SDA1 | Pin 3 |
| CLK | SCL | GPIO3 / SCL1 | Pin 5 |
| CS | — | GND | Pin 6 (or any GND) |
| DC | — | GND | → I2C address 0x3C |
| RST | — | 3.3V | Pin 1 (holds out of reset) |

> CS and DC are tied to GND permanently. RST tied high means no software reset — acceptable for a status display. Wire RST to a spare GPIO (e.g. GPIO24) if software reboot of the display is needed.

**Verify with:**
```bash
sudo i2cdetect -y 1    # should show 0x3C
```

---

## I2C Address

| DC pin | I2C Address |
|---|---|
| LOW (GND) | **0x3C** — recommended, matches luma.oled default |
| HIGH (3.3V) | 0x3D |

No conflict with any other device on the Pi I2C bus (BNO055 was 0x28, INA219 was 0x40 — both now live on the ESP32).

---

## Software — Raspberry Pi

The SSD1309 is register-compatible with the SSD1306 but requires explicit driver selection. The `luma.oled` Python library has native SSD1309 support.

**Install:**
```bash
sudo pip3 install luma.oled pillow
```

**Minimal test:**
```python
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1309
from luma.core.render import canvas

serial = i2c(port=1, address=0x3C)
device = ssd1309(serial)

with canvas(device) as draw:
    draw.text((0, 0), "MyBot online", fill="white")
```

**ROS 2 integration:** write a Python node that subscribes to `/battery_state`, `/diff_cont/odom`, and `/odom`, then renders to the display using Pillow. See `docs/oled-display-plan.md` for the full plan.

---

## Official docs

- Waveshare wiki: https://www.waveshare.com/wiki/2.42inch_OLED_Module
- Waveshare product page: https://www.waveshare.com/2.42inch-oled-module.htm
- SSD1309 datasheet: https://www.solomon-systech.com/product/ssd1309/
- luma.oled library: https://luma-oled.readthedocs.io/
