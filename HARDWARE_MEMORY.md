# HARDWARE_MEMORY.md

## Robot Hardware Goal
Differential drive ROS 2 robot using Raspberry Pi + ESP32-S3 micro-ROS controller. The Arduino motor-controller path is legacy reference only.

---

## System Block Diagram

Dev Machine (ROS tools / teleop / RViz2 / Nav2 / EKF)
        ⇅ WiFi / network (ROS_DOMAIN_ID=0)

Raspberry Pi (ROS 2 Humble) — 192.168.86.33
├── robot_state_publisher
├── micro_ros_agent (serial /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00) ← ESP32-S3
├── twist_mux
├── rplidar_node → /scan (/dev/rplidar)
├── realsense2_camera_node → /camera/*
└── oled_display_node (systemd: oled-display.service, starts at boot)
    → SPI0: MOSI=GPIO10, SCLK=GPIO11, CE0=GPIO8, DC=GPIO25, RST=GPIO27

ESP32-S3-DevKitC-1 — 192.168.86.43 (WiFi OTA only)
├── Publishes: /diff_cont/odom (30Hz), /imu/imu (30Hz), /battery_state (1Hz)
├── Subscribes: /diff_cont/cmd_vel_unstamped
├── GPIO10-15 → TB6612 → Left/Right DC Gear Motors (JGA25-371, 45:1)
├── GPIO40/41 (Left enc A/B), GPIO42/39 (Right enc A/B)
└── I2C GPIO8/9 → BNO055 (0x28) + INA219 (0x40)

Legacy reference:
- `legacy/ros_arduino_bridge` + `diffdrive_arduino` remain in the repo for historical comparison only.

---

## Serial Links

### ESP32-S3 (micro-ROS)
Device: /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00  (HWCDC native USB)
Protocol: micro-ROS serial transport
Agent: `source ~/microros_ws/install/setup.bash && ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00`

### RPLidar
Device: /dev/rplidar  (udev symlink → CP2102, 10c4:ea60)
Baud: 115200

### udev rules file
/etc/udev/rules.d/99-mybot.rules

User must be in: dialout group

---

## BNO055 IMU

**Now on ESP32-S3 I2C (GPIO8/9) — NOT Pi I2C.**
The Pi-side bno055 ROS node has been removed; the ESP32 firmware reads the BNO055 directly
and publishes `/imu/imu` at 30Hz via micro-ROS (identical topic, EKF unchanged).

Address: 0x28 (ADR unconnected)
Wiring: SDA → GPIO8, SCL → GPIO9, Vin → 3.3V, GND → GND (shared I2C bus with INA219)

Physical mount position in base_link frame:
xyz = "0.004 -0.018 0.055" (80mm from front edge, 50mm from right edge, upper deck)

Axis validation (2026-05-03, when on Pi I2C — same physical mount, ESP32 reads same sensor):
- IMU x-axis = robot forward (accel positive on x when driving forward)
- IMU z-axis = robot yaw (gyro z negative for clockwise rotation)
- placement_axis_remap: P1 (confirmed correct)
- Circle test: gyro z = -0.494 rad/s at -0.525 rad/s commanded

ESP32 firmware config: orientation_covariance[0]=-1 so EKF ignores orientation (magnetometer
unreliable on metal chassis); angular velocity + linear accel enabled.

---

## Motor Driver Pin Mapping (Arduino → Adafruit TB6612)

Replaced L298N with Adafruit TB6612 breakout (2026-04-25). Validated 2026-05-03.

PWMA = D5   → right motor PWM speed   (Motor A = RIGHT)
AIN1 = D7   → right motor FORWARD
AIN2 = D6   → right motor BACKWARD
BIN1 = D8   → left motor FORWARD     (Motor B = LEFT)
BIN2 = D9   → left motor BACKWARD
PWMB = D10  → left motor PWM speed

STBY → not wired; Adafruit breakout has onboard pullup (defaults HIGH = enabled)

Motor output wiring:
  Right motor → AO1 + AO2  (both wires on MOTORA pads — NOT the GND pad between sections)
  Left motor  → BO1 + BO2  (both wires on MOTORB pads — NOT the GND pad between sections)

Firmware define: TB6612_MOTOR_DRIVER
File: legacy/ros_arduino_bridge/ROSArduinoBridge/ROSArduinoBridge.ino

Direction logic (TB6612 truth table):
  Forward:  xIN1=HIGH, xIN2=LOW + PWM
  Backward: xIN1=LOW,  xIN2=HIGH + PWM
  Coast:    xIN1=LOW,  xIN2=LOW
  Brake:    xIN1=HIGH, xIN2=HIGH

**STATUS: Replacement installed and validated 2026-05-03.**
Both motors run in both directions. Teleop confirmed: i=forward, j/l=turn.

History:
- First unit (2026-04-25): destroyed by 12V reaching AIN1/BIN1 logic pins (max 5.5V)
- Replacement: motor wires were on motor output pad + GND pad between sections instead of
  both on MOTORA/MOTORB pads → only one direction worked. Fixed by moving wires to correct pads.
- Left motor ran backward: swapped LEFT_MOTOR_FORWARD/BACKWARD (BIN1↔BIN2) in firmware.

---

## Encoder Wiring (DC12V 130RPM Amazon JGA25-371 — installed 2026-03-16)

Red    → Motor Power +
White  → Motor Power -
Blue   → Encoder VCC (3.3V–5V)
Black  → Encoder Ground
Yellow → Encoder Channel A
Green  → Encoder Channel B

Encoder Arduino pin mapping:
Left  A → D2 (INT0), Left  B → D4
Right A → D3 (INT1), Right B → D12

Encoder resolution:
11 PPR (motor shaft), 45:1 actual gear ratio (Amazon listing says 34:1 — inaccurate)
Firmware uses 2x quadrature → 11 × 2 × 45 = 990 base; validated value is 1010

Configured counts per rev in ROS: 1010
Re-validated 2026-03-17 (3 wall-guided runs: 1006/1016/1012, avg 1011)

To fine-tune after odometry test:
new_value = old_value × (actual_distance / reported_distance)

---

## Wheel Geometry (Controller Config)

Wheel separation: 0.179 m  (179mm center-to-center, measured 2026-03-16)
Wheel radius: 0.034 m  (68mm diameter measured; datasheet says 65mm)
Controller update rate: 30 Hz

Velocity limits (my_controllers.yaml):
  linear max:  0.3 m/s   (each wheel at 0.3 m/s)
  angular max: 3.35 rad/s  (= 2 × 0.3 / 0.179 — matched to linear for equal wheel speed)

Velocity tracking validation (2026-05-03, 3 consistent runs, robot free to move on floor):
  Speed   Forward  Spin
  25%     83%      69%   ← motor deadband at low PWM — normal for DC motors
  50%     92%      88%
  75%     97%      93%
  100%    98%      96%
Left/right wheels symmetric within 0.002 m/s across all steps.
Operating range (50–100%) tracks 88–98% for both modes.

Note: holding the robot body while spinning creates lateral tire scrub → hard plateau at ~0.085 m/s.
This is NOT a motor/firmware limit — robot must be free to rotate for normal behavior.

---

## Odometry / EKF

/diff_cont/odom — raw wheel odometry from diff_drive_controller
/imu/imu        — fused IMU data from BNO055 (NDOF mode)
/odom           — EKF filtered output (robot_localization ekf_node, 20Hz)

EKF config: config/ekf.yaml
- frequency: 20Hz
- two_d_mode: true
- fuses: odom0=/diff_cont/odom + imu0=/imu/imu
- IMU orientation disabled (magnetometer unreliable on metal chassis)
- IMU angular velocity + linear accel enabled

---

## Known Working ros2_control Hardware Plugin

diffdrive_arduino/DiffDriveArduinoHardware

File:
articubot_one/description/ros2_control.xacro

Never use legacy class:
diffdrive_arduino/DiffDriveArduino

---

## Runtime Controller Names

diff_cont
joint_broad

cmd_vel remap target:
/diff_cont/cmd_vel_unstamped

---

## Power Architecture

Power distribution board: **DFR0205** (DFRobot DC-DC buck converter, 3.6–25V in, adjustable out, 5A/25W max)

```
12V LiPo/Lead-acid battery
├── DFR0205 regulated 5V ──────────→ Raspberry Pi (USB-C)
│       ├── Pi USB port ───────────→ ESP32-S3 (power + serial/OTA, stable by-id path)
│       ├── Pi USB port ───────────→ RPLidar A1 (power + serial, /dev/rplidar)
│       ├── Pi USB 3.0 ────────────→ RealSense D435 (power + USB 3)
│       └── Pi 3.3V (GPIO) ────────→ Waveshare OLED (~20mA, SPI0)
└── DFR0205 12V passthrough ───────→ TB6612 VM (motor power only)

TB6612 logic VCC → ESP32 3V3 pin
```

Ground must be common between: Pi, ESP32-S3, TB6612, encoders, DFR0205.

---

## Known Good Bringup Sequence

1. Plug ESP32-S3 USB and RPLidar USB into Pi
2. Verify devices: ls /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00 /dev/rplidar
3. Source workspace: source ~/mybot_ws/install/setup.bash && source ~/microros_ws/install/setup.bash
4. Confirm robot-launch.service is active, or run `mybot-launch` for a manual restart
5. On dev machine: source ~/dev_ws/install/setup.bash

mybot-launch alias (in ~/.bashrc on Pi):
Runs launch_robot.launch.py which starts micro_ros_agent, twist_mux, rplidar, realsense2_camera, robot_state_publisher. The current launch path sends `twist_mux` directly to `/diff_cont/cmd_vel_unstamped`.
Low-level PID tuning is done on the ESP32 bench firmware in `src/esp32_microros/test/test_pid_bench`; the Pi bridge is for integration runs.

---

## SLAM Map

Saved: ~/mybot_ws/maps/my_map.pgm + my_map.yaml
Size: 200 × 136 cells @ 0.05 m/pix
Captured: 2026-03-18 via slam_toolbox online async mode, teleop-controlled

---

## Hardware Docs in Repo

Hardware/
├── adafruit-bno055-absolute-orientation-sensor.pdf  — BNO055 breakout datasheet
├── 4010_datasheet.pdf                               — fan/motor datasheet
├── DC12V Encoder Gear Motor.png                     — motor photo
├── motor.png                                        — motor photo
└── mybot/                                           — CAD renders
    ├── mybot_dim.png                                — chassis dimensions
    ├── mybot_front/back/left/right/top.png          — orthographic views
    └── mybot1.png                                   — isometric view

---

## Hardware Images Still Needed

• real robot wiring photo
• Arduino pin connection photo
• BNO055 mount photo
• encoder wire color photo
• wheel left/right orientation photo
• battery + power distribution photo
• USB/serial connection photo

---

## ESP32-S3 + micro-ROS (production — all tests confirmed)

Hardware: ESP32-S3-DevKitC-1 on Lonely Binary ESP32-S3 Expansion Base.
Static IP: 192.168.86.43 | Hostname: esp32-mybot.local | OTA password: esp32ota
Replaces Arduino Nano + Pi-side BNO055/INA219. Pi EKF/Nav2/AMCL require no changes — same topics.

ESP32-S3 → TB6612 (Motor A = RIGHT, Motor B = LEFT):
```
VCC  → 3V3    (logic supply)
PWMA → GPIO10  (right motor speed, LEDC ch 0)
AIN1 → GPIO11  (right motor dir A)
AIN2 → GPIO12  (right motor dir B)
PWMB → GPIO13  (left motor speed, LEDC ch 1)
BIN1 → GPIO14  (left motor dir A)
BIN2 → GPIO15  (left motor dir B)
STBY → not wired (Adafruit breakout onboard pullup)
VM   → 12V motor supply
GND  → GND
```

ESP32-S3 → BNO055 + INA219 (shared I2C bus):
```
SDA  → GPIO8   (both devices)
SCL  → GPIO9   (both devices)
Vin  → 3V3
GND  → GND
BNO055 address: 0x28 (ADR unconnected)
INA219 address: 0x40 (A0/A1 unconnected)
```

Encoders → ESP32-S3 (INPUT_PULLUP, interrupt on A channel CHANGE):
```
Left  A → GPIO40,  Left  B → GPIO41
Right A → GPIO42,  Right B → GPIO39
```
ISR: Left A==B → forward, Right A!=B → forward. ENC_CPR=1010, radius=0.034m.

micro-ROS Transport — USB serial via native HWCDC:
```
ESP32-S3 native USB port → USB cable → Pi stable by-id device
build_flags = -DARDUINO_USB_CDC_ON_BOOT=1  (routes Serial to HWCDC)
WiFi used only for OTA and TelnetStream monitoring
```

micro-ROS agent (built from source in ~/microros_ws — not in apt for arm64):
```bash
source /opt/ros/humble/setup.bash
source ~/microros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00
```

Topics: publishes `/diff_cont/odom`, `/imu/imu`, `/battery_state`
        subscribes `/diff_cont/cmd_vel_unstamped`

---

## Waveshare 2.42" OLED Display

**Hardware:** 128×64 white OLED, SSD1309 controller, SPI 4-wire mode (factory default).
**Mount:** Pi SPI0 bus (completely free — not shared with any other device).

Wiring (Pi BCM → Pi board pin):
```
VCC  → 3.3V      (pin 1)
GND  → GND       (pin 6)
DIN  → GPIO10    (pin 19, SPI0_MOSI)
CLK  → GPIO11    (pin 23, SPI0_SCLK)
CS   → GPIO8     (pin 24, SPI0_CE0)
DC   → GPIO25    (pin 22, RIGHT column row 11)
RST  → GPIO27    (pin 13)
```

⚠️ **DC pin 22 is the RIGHT column of row 11.** The left column of the same row is GPIO9/MISO (pin 21). Wrong pin = silent failure: no error, display stays dark.

**Driver:** spidev + RPi.GPIO directly. **Do NOT use luma.oled** — its `ssd1309` class is an empty alias for `ssd1306` and sends the SSD1306 charge pump command `0x8D 0x14` (undefined on SSD1309), which corrupts initialization silently.

SPI speed: **100kHz** (`max_speed_hz = 100000`). 1MHz is unreliable at cold boot.
SPI mode 3 (`sp.mode = 0b11`, CPOL=1, CPHA=1) required by Waveshare module.
Memory addressing: **page mode** (`0x20 0x02`) — must match `_show()` which uses `0xB0+page` commands.

**Cold-boot init quirks (all three must be handled):**
1. **GPIO group membership** — RPi.GPIO silently does nothing without `gpio`/`spi`/`dialout` groups.
   Symptoms: no exceptions, "Display init OK" logged, display completely dark.
   Diagnosis: probe DC pin (GPIO25/pin 22) with multimeter while running `GPIO.output(25, GPIO.HIGH)` — reads 0.2V instead of 3.3V. Fix: `sudo usermod -aG gpio,spi,i2c,dialout ryan` + log out/in.
2. **SPI controller priming** — first SPI transaction on a cold kernel init is unreliable.
   Fix: send dummy `0x00` byte while RST is LOW (display ignores it) before real init sequence.
3. **Display warmup** — send `0xA5` (all pixels ON) for 1s then `0xA4` (resume GDDRAM) to stabilize.

**Node:** `oled_display_node.py`
- Reads battery telemetry directly from the ESP32 Telnet stream at `esp32-mybot.local:23`
- Renders at 2Hz: IP, battery V/A, telemetry age, ESP32 link status, ROS status
- IP via UDP socket trick (not `gethostbyname` — returns 127.0.1.1 on Ubuntu 22.04)
- Status line: `ESP32 ONLINE` / `ESP32 OFFLINE`
- ROS line: `ROS UP` / `ROS DOWN`
- OLED layout is still being tuned; keep the data path stable, but expect font/spacing
  adjustments to continue.

**Systemd service:** `/etc/systemd/system/oled-display.service` (Pi only, not in git)
- `User=ryan` — requires ryan to be in gpio/spi/dialout groups (see above)
- `After=network.target` — start once basic networking is up; the node retries until ESP32 telemetry is available
- `Restart=always RestartSec=5`
- NOT in `launch_robot.launch.py` — systemd handles it independently

**Current OLED layout:**
1. `<Pi IP>`
2. `<voltage>V  <current>A`
3. `ROS OK  ESP OK`
4. `UPTIME mm:ss` or `h:mm:ss`

**Note:** the layout is not frozen yet. The battery feed is correct, but the
visual arrangement is still being refined.

```bash
sudo systemctl status oled-display
sudo systemctl restart oled-display
journalctl -u oled-display -f
```

**SPI interface verification:** `ls /dev/spidev*` → should show `/dev/spidev0.0`.
Enable SPI: `echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt && sudo reboot`
(raspi-config is not available on Ubuntu 22.04 — edit config.txt directly.)

---

## Future Hardware Paths

• Hoverboard motor platform migration

---

## Golden Rule

When robot stops moving:

Do not change:

• plugin name
• serial device
• encoder pins
• motor polarity
• controller YAML

all at once.

Change one variable.
Observe.
Repeat.

Robots obey physics.
Software obeys strings.
Confusing the two creates smoke.
