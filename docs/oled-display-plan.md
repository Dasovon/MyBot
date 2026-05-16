# OLED Display — Implementation Notes

**Hardware:** Waveshare 2.42inch OLED, 128×64, SSD1309 controller  
**Reference:** `Hardware/display/oled-2.42inch.md`  
**Status:** Complete and running as `oled-display.service`

---

## Design Decisions

**Why Pi, not ESP32:**

| Factor | Pi | ESP32 |
|---|---|---|
| Data richness | Full ROS graph: Nav2 status, EKF pose, battery, velocity | Only local sensor data; no Nav2 awareness |
| Implementation risk | Separate Python node — a crash can't affect motors | Adding display to the real-time PID/micro-ROS loop adds timing risk |
| Bus availability | SPI0 completely free | I2C bus already used by BNO055 + INA219 |

**Why spidev + RPi.GPIO directly (not luma.oled):**  
`luma.oled`'s `ssd1309` class is an empty alias for `ssd1306`. It sends the SSD1306 charge pump command (`0x8D 0x14`) which is undefined on the SSD1309 and corrupts initialization. The display initialises silently, sends data without error, but shows nothing.

**Why systemd service (not in launch_robot.launch.py):**  
The display starts at boot showing connection status before the robot launch runs. If it were in the launch file, the display would be dark until the operator manually launches the stack.

---

## Wiring

```
Waveshare 2.42" OLED          Wire     Raspberry Pi (BCM → Board)
─────────────────────         ──────   ─────────────────────────
VCC  ──────────────────────→  Red   →  3.3V              (pin  1)
GND  ──────────────────────→  Black →  GND               (pin  6)
DIN  ──────────────────────→  Blue  →  GPIO10 SPI0_MOSI  (pin 19)
CLK  ──────────────────────→  Yellow→  GPIO11 SPI0_SCLK  (pin 23)
CS   ──────────────────────→  Orange→  GPIO8  SPI0_CE0   (pin 24)
DC   ──────────────────────→  Green →  GPIO25            (pin 22, RIGHT column)
RST  ──────────────────────→  White →  GPIO27            (pin 13)
```

> **Note:** GPIO25 (DC) is pin 22, which is on the **right** column of the header, row 11. GPIO9/MISO is the left column of the same row — don't confuse them.

Enable SPI (one-time): `sudo raspi-config` → Interface Options → SPI → Enable

---

## Display Layout

```
┌────────────────────────────────┐
│ IP 192.168.86.33               │  ← Pi IP via UDP socket trick (not gethostbyname)
│ BAT 11.4V  0.12A               │  ← ESP32 telnet telemetry
│ AGE 00:00:12                   │  ← time since last battery update
│ ESP32 ONLINE                   │  ← direct ESP32 telemetry link status
│ ROS UP                         │  ← robot-launch.service state
└────────────────────────────────┘
```

Status line states:

| State | Display |
|---|---|
| Fresh battery telemetry | `ESP32 ONLINE` |
| Stale or missing telemetry | `ESP32 OFFLINE` |

ROS line states:

| State | Display |
|---|---|
| `robot-launch.service` active | `ROS UP` |
| `robot-launch.service` inactive | `ROS DOWN` |

---

## Software Install

```bash
sudo pip3 install spidev pillow
# RPi.GPIO ships with Ubuntu 22.04 (python3-rpi.gpio)
```

---

## Pixel Rendering Convention

The SSD1309 uses page-based addressing. The `_show()` method in `oled_display_node.py` mirrors the Waveshare driver:

- PIL image uses **white background** (`Image.new('1', ..., 1)`) and **black text** (`fill=0`)
- Black pixels (0) in PIL → bit set → inverted → `0xFF` sent → **pixels lit on display**
- White pixels (1) in PIL → bit clear → inverted → `0x00` sent → pixels off

This means the display shows dark background with lit text.

---

## Systemd Service

File: `/etc/systemd/system/oled-display.service`

```ini
[Unit]
Description=MyBot OLED Display Node
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ryan
ExecStart=/bin/bash -c 'source /opt/ros/humble/setup.bash && source /home/ryan/mybot_ws/install/setup.bash && ros2 run articubot_one oled_display_node.py'
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Service commands
sudo systemctl status oled-display
sudo systemctl restart oled-display
journalctl -u oled-display -f
```

---

## Known Issues / Lessons Learned

- **luma.oled doesn't work for SSD1309** — see Design Decisions above. Use spidev directly.
- **DC wire must be pin 22 (right column, row 11)** — not pin 21 (left column, row 11, which is GPIO9/MISO). Silent failure: no error, no display.
- **`socket.gethostbyname(socket.gethostname())` returns `127.0.1.1`** on Ubuntu 22.04 due to `/etc/hosts`. Use UDP socket trick instead:
  ```python
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.connect(('8.8.8.8', 80))
  ip = s.getsockname()[0]
  s.close()
  ```
- **SPI mode 3 required** (`sp.mode = 0b11`) — Waveshare module requires CPOL=1, CPHA=1.
- **OLED now reads battery directly from the ESP32 telnet stream** — the screen no longer depends on the ROS battery topic.
