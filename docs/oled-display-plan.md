# OLED Display Integration Plan

**Hardware:** Waveshare 2.42inch OLED, 128×64, SSD1309 controller  
**Reference:** `Hardware/display/oled-2.42inch.md`

---

## Recommendation: Run on the Pi, SPI mode

**Why Pi, not ESP32:**

| Factor | Pi | ESP32 |
|---|---|---|
| Data richness | Full ROS graph: Nav2 status, EKF pose, battery, velocity | Only local sensor data; no Nav2 awareness |
| Implementation risk | Separate Python node — a crash can't affect motors | Adding display management to the real-time PID/micro-ROS loop adds complexity and timing risk |
| Library support | `luma.oled` has native SSD1309 SPI support; Pillow for layout | u8g2 works but embedded C layout code is significantly more work |
| Serial port | Serial free for normal use | Serial is owned by micro-ROS transport; debug output is TelnetStream only |
| Bus availability | SPI0 bus is completely free | I2C bus already used by BNO055 + INA219 |

**Why SPI, not I2C (on Pi):**  
The module ships in SPI mode — no resistor swap needed. SPI is faster and more reliable than I2C; at 2 Hz refresh rate the speed difference is irrelevant, but avoiding the PCB modification is a clear win.

---

## Wiring Summary

Module ships in SPI mode — use it as-is, no resistor swap needed.

```
Waveshare 2.42" OLED          Wire     Raspberry Pi (BCM → Board)
─────────────────────         ──────   ─────────────────────────
VCC  ──────────────────────→  Red   →  3.3V              (pin  1)
GND  ──────────────────────→  Black →  GND               (pin  6)
DIN  ──────────────────────→  Blue  →  GPIO10 SPI0_MOSI  (pin 19)
CLK  ──────────────────────→  Yellow→  GPIO11 SPI0_SCLK  (pin 23)
CS   ──────────────────────→  Orange→  GPIO8  SPI0_CE0   (pin 24)
DC   ──────────────────────→  Green →  GPIO25            (pin 22)
RST  ──────────────────────→  White →  GPIO27            (pin 13)
```

Confirm after wiring: `ls /dev/spidev*` should show `/dev/spidev0.0`.

---

## What to Display

128×64 pixels fits 5–6 lines of small text (8px font) or 3–4 lines of readable text (12px font). Suggested layout:

```
┌────────────────────────────────┐
│ MyBot          192.168.86.33   │  ← hostname / IP (static)
│ BAT  11.4V   0.12A             │  ← /battery_state  (1 Hz)
│ VEL  0.24m/s  0.0rad/s         │  ← /diff_cont/odom (sampled 2 Hz)
│ POS  x=1.23  y=0.87  θ=45°    │  ← /odom EKF filtered
│ ● NAVIGATING                   │  ← Nav2 action state or IDLE
└────────────────────────────────┘
```

States for the bottom status line:

| State | Display |
|---|---|
| Agent not connected | `✗ AGENT OFFLINE` |
| Connected, no goal | `● IDLE` |
| Actively navigating | `● NAVIGATING` |
| Goal reached | `✓ GOAL REACHED` |
| Nav2 not running | `● TELEOP` |

---

## Implementation Steps

### 1. Physical

- Wire to Pi SPI0 header per the wiring diagram above (no resistor swap — module ships in SPI mode)
- Enable SPI: `sudo raspi-config` → Interface Options → SPI → Enable → reboot
- Verify: `ls /dev/spidev*` should show `/dev/spidev0.0`

### 2. Install library on Pi

```bash
sudo pip3 install luma.oled pillow
```

Verify with a one-shot test before writing the ROS node:
```python
from luma.core.interface.serial import spi
from luma.oled.device import ssd1309
from luma.core.render import canvas
serial = spi(device=0, port=0, gpio_DC=25, gpio_RST=27)
device = ssd1309(serial)
with canvas(device) as draw:
    draw.text((0, 0), "MyBot online", fill="white")
```

### 3. Write `oled_display_node.py`

Location: `src/articubot_one/scripts/oled_display_node.py`

The node should:
- Subscribe to `/battery_state` (`sensor_msgs/BatteryState`) at 1 Hz
- Subscribe to `/diff_cont/odom` (`nav_msgs/Odometry`) — sample at display rate
- Subscribe to `/odom` (`nav_msgs/Odometry`) for EKF pose (x, y, θ)
- Optionally subscribe to a Nav2 action feedback topic for goal state
- Use a `create_timer(0.5, render_callback)` to refresh the display at 2 Hz — no need to re-render on every message
- Render with Pillow `ImageDraw` onto a 128×64 `Image`, then push to luma.oled device
- Handle display init failure gracefully (log warn, don't crash the node)

Key imports:
```python
from luma.core.interface.serial import spi
from luma.oled.device import ssd1309
from PIL import Image, ImageDraw, ImageFont
```

### 4. Register in CMakeLists.txt

```cmake
install(
  PROGRAMS scripts/oled_display_node.py
  DESTINATION lib/${PROJECT_NAME}
)
```

This is already the pattern used for `ina219_node.py`.

### 5. Add to `launch_robot.launch.py`

```python
oled = Node(
    package=package_name,
    executable='oled_display_node.py',
)
```

Add `oled` to the `LaunchDescription` return list. The node should start silently and show a "starting..." splash until topics arrive.

---

## Font note

The default PIL bitmap font is very small. For readable text on 128×64 load a TTF:
```python
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
```
`dejavu-fonts-ttf` is available on Raspberry Pi OS by default (`sudo apt install fonts-dejavu-core` if missing).

---

## What changes in the repo

| File | Change |
|---|---|
| `src/articubot_one/scripts/oled_display_node.py` | new — ROS 2 display node |
| `src/articubot_one/CMakeLists.txt` | add install for new script |
| `src/articubot_one/launch/launch_robot.launch.py` | add `oled` node |
| `Hardware/display/oled-2.42inch.md` | new — hardware reference |
| `docs/oled-display-plan.md` | this file |

No changes needed to URDF, EKF config, Nav2 params, or controller YAML.

---

## Future option: ESP32 fallback display

If a minimal always-on display is wanted independent of ROS (e.g. show WiFi/agent status even when Pi is booting), a second smaller OLED could be driven directly from the ESP32 over SPI using the u8g2 library. This is a separate future addition — do not mix it with the Pi display above.
