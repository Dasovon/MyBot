# OLED Display Integration Plan

**Hardware:** Waveshare 2.42inch OLED, 128×64, SSD1309 controller  
**Reference:** `Hardware/display/oled-2.42inch.md`

---

## Recommendation: Run on the Pi, I2C mode

**Why Pi, not ESP32:**

| Factor | Pi | ESP32 |
|---|---|---|
| I2C bus availability | Bus 1 is completely free after ESP32 migration | Bus already used by BNO055 + INA219; SPI would need 5 free GPIOs on a tight board |
| Data richness | Full ROS graph: Nav2 status, EKF pose, battery, velocity | Only local sensor data; no Nav2 awareness |
| Implementation risk | Separate Python node — a crash can't affect motors | Adding display management to the real-time PID/micro-ROS loop adds complexity and timing risk |
| Library support | `luma.oled` has native SSD1309 I2C support; Pillow for layout | u8g2 works but embedded C layout code is significantly more work |
| Serial port | Serial free for normal use | Serial is owned by micro-ROS transport; debug output is TelnetStream only |
| Wiring | 4 wires to existing I2C header | 5 wires (SPI) or I2C shared with sensors already at I2C limit |

**Why I2C, not SPI (on Pi):**  
The Pi's SPI bus is currently unused, but I2C requires only 4 wires and plugs directly into the existing Pi I2C header (GPIO2/3) with no additional GPIO use. The SSD1309 at I2C runs fine for a low-refresh-rate status display.

---

## Wiring Summary

Module ships in SPI mode — **resistor swap required before wiring** (move R1→R2 and R4→R3 on the PCB).

```
Waveshare 2.42" OLED          Raspberry Pi
─────────────────────         ────────────
VCC  ──────────────────────→  3.3V  (pin 1)
GND  ──────────────────────→  GND   (pin 6)
DIN  ──────────────────────→  GPIO2 / SDA1 (pin 3)
CLK  ──────────────────────→  GPIO3 / SCL1 (pin 5)
CS   ──────────────────────→  GND   (any)
DC   ──────────────────────→  GND   (any)  → address 0x3C
RST  ──────────────────────→  3.3V  (pin 1)
```

Confirm after wiring: `sudo i2cdetect -y 1` should show `3c`.

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

- Perform resistor swap on the OLED PCB (SPI → I2C)
- Wire to Pi I2C header (see wiring diagram above)
- Run `sudo i2cdetect -y 1` to confirm `3c` appears

### 2. Install library on Pi

```bash
sudo pip3 install luma.oled pillow
```

Verify with a one-shot test before writing the ROS node:
```python
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1309
from luma.core.render import canvas
serial = i2c(port=1, address=0x3C)
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
from luma.core.interface.serial import i2c
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
