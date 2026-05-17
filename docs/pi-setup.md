# Raspberry Pi Setup — Full Restore Guide

Complete procedure for setting up the Pi from a blank SD card to a fully running robot stack.
Validated 2026-05-14 after full Ubuntu 22.04.5 reflash.

---

## 1. Flash SD Card

1. Download **Ubuntu Server 22.04.5 LTS (64-bit)** for Raspberry Pi from ubuntu.com
2. Flash with **Raspberry Pi Imager**:
   - Click the gear icon before writing
   - Set hostname: `mybot`
   - Enable SSH → use password authentication
   - Set username: `ryan`, password: `0508`
   - Configure WiFi (SSID: `FBI-Van`, password in credentials.h)
3. Insert SD card and boot Pi

---

## 2. Find Pi on Network

```bash
ping mybot.local
# or check router DHCP table — Pi registers as "mybot"
```

SSH in for the first time:
```bash
ssh ryan@mybot
# accept fingerprint, password: 0508
```

---

## 3. Update System

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

---

## 4. Install ROS 2 Humble

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install -y curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list
sudo apt update
sudo apt install -y ros-humble-ros-base ros-dev-tools
sudo apt install -y ros-humble-twist-mux ros-humble-robot-localization \
  ros-humble-rplidar-ros ros-humble-realsense2-camera ros-humble-realsense2-description
```

---

## 5. Clone and Build Workspace

```bash
mkdir -p ~/mybot_ws/src && cd ~/mybot_ws/src
git clone https://github.com/Dasovon/MyBot.git articubot_one
git clone -b humble https://github.com/joshnewans/diffdrive_arduino.git
git clone -b newans_ros2 https://github.com/joshnewans/serial.git

cd ~/mybot_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
```

---

## 6. Build micro-ROS Agent from Source

`ros-humble-micro-ros-agent` is not in apt for arm64. Must build from source.

```bash
mkdir -p ~/microros_ws/src && cd ~/microros_ws
git clone -b humble https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash

ros2 run micro_ros_setup create_agent_ws.sh
ros2 run micro_ros_setup build_agent.sh
```

Takes ~10–15 minutes on Pi 4.

---

## 7. Build librealsense with RSUSB Backend

The apt version uses the kernel UVC driver which causes `xioctl(UVCIOC_CTRL_QUERY)` timeouts that
break the RealSense color stream. Must build from source with `-DFORCE_RSUSB_BACKEND=ON`.

```bash
sudo apt remove ros-humble-librealsense2* -y
sudo apt install -y libusb-1.0-0-dev libssl-dev cmake libgtk-3-dev

git clone https://github.com/IntelRealSense/librealsense ~/librealsense
cd ~/librealsense && git checkout v2.56.4
mkdir build && cd build
cmake .. -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF \
  -DBUILD_GRAPHICAL_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
make -j2    # NOT -j4 — Pi 4 OOMs with 4 jobs
sudo make install && sudo ldconfig

# Reinstall ROS RealSense packages (they link against librealsense)
sudo apt install -y ros-humble-realsense2-camera ros-humble-realsense2-description

# Override the apt .so with the RSUSB build (ROS prepends its lib path — LD_LIBRARY_PATH won't work)
sudo cp /usr/local/lib/librealsense2.so.2.56.4 \
  /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4
```

Takes ~45–60 minutes on Pi 4.

---

## 8. udev Rules

```bash
sudo nano /etc/udev/rules.d/99-mybot.rules
```

Paste:
```
# RPLidar A1 (CP2102)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="rplidar"

# Arduino Nano (CH340)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="arduino"
```

Apply:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## 9. Enable SPI

**Note: `raspi-config` is not available on Ubuntu — edit the config file directly.**

```bash
grep -q "dtparam=spi=on" /boot/firmware/config.txt || \
  echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

After reboot, verify:
```bash
ls /dev/spidev*
# should show: /dev/spidev0.0  /dev/spidev0.1
```

---

## 10. Python Packages for OLED Display

```bash
sudo apt install -y python3-spidev python3-rpi.gpio python3-gpiozero python3-pil
```

---

## 11. User Groups — CRITICAL

RPi.GPIO and spidev require the user to be in the correct groups. **Without this, GPIO/SPI scripts
run silently with no errors but pins never actually change state** — this will look exactly like a
hardware failure and is extremely difficult to diagnose.

```bash
sudo usermod -aG gpio,spi,i2c,dialout ryan
```

**Then log out and log back in** — group changes do not take effect in the current session:
```bash
exit
ssh ryan@mybot
# verify:
groups
# should include: gpio spi i2c dialout
```

### How to verify groups are working

Run this without sudo — if GPIO25 reads ~3.3V, groups are active:
```bash
python3 - << 'EOF'
import RPi.GPIO as GPIO, time
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(25, GPIO.OUT)
GPIO.output(25, GPIO.HIGH)
time.sleep(5)
GPIO.output(25, GPIO.LOW)
GPIO.cleanup()
EOF
```

Probe Pi pin 22 to GND with a multimeter. Should read ~3.3V during the 5-second window.
If it reads near 0V, you're either missing a group or haven't re-logged in yet.

### Why sudo isn't the answer

The oled-display.service runs as user `ryan` (not root). If you rely on sudo, the systemd service
will fail. The group membership approach is correct — sudo is only needed for system admin tasks.

---

## 12. Passwordless Sudo

Required for the `mybot-launch` alias and some robot bringup scripts:

```bash
echo "ryan ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/ryan
sudo chmod 440 /etc/sudoers.d/ryan
```

---

## 13. SSH Key from Dev Machine

Run this on the **dev machine** (not Pi) to install your SSH key:

```bash
ssh-copy-id ryan@mybot
```

After this, SSH from the dev machine no longer requires a password.

If re-flashing and getting a host key mismatch error:
```bash
ssh-keygen -f ~/.ssh/known_hosts -R mybot
ssh-keygen -f ~/.ssh/known_hosts -R 192.168.86.33
```

---

## 14. .bashrc Setup

```bash
cat >> ~/.bashrc << 'EOF'

source /opt/ros/humble/setup.bash
source ~/mybot_ws/install/setup.bash
source ~/microros_ws/install/setup.bash
export ROS_DOMAIN_ID=0

alias mybot-launch='sudo fuser -k /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00 2>/dev/null; source ~/microros_ws/install/setup.bash && ros2 launch articubot_one launch_robot.launch.py'
EOF
source ~/.bashrc
```

---

## 15. OLED Display systemd Service

### 15a. Service file

The service file lives on the Pi only (not in git). Create it after verifying the display works:

```bash
sudo nano /etc/systemd/system/oled-display.service
```

Paste:
```ini
[Unit]
Description=OLED Display Node
After=network.target

[Service]
Type=simple
User=ryan
Environment="PYTHONUNBUFFERED=1"
ExecStart=/bin/bash -c "source /opt/ros/humble/setup.bash && source /home/ryan/mybot_ws/install/setup.bash && ros2 run articubot_one oled_display_node.py"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The OLED service starts with normal network bring-up and retries until the ESP32 feed is available.
On this Pi, `systemd-networkd-wait-online.service` is overridden to a 10-second timeout so boot
does not sit for two minutes waiting on full network-online state.

`Restart=always` / `RestartSec=5` work together with the 30-second data timeout built into the node:
if no ESP32 data arrives, the node exits and systemd restarts it. Repeat until `mybot-launch` is running.

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable oled-display
sudo systemctl start oled-display
sudo systemctl status oled-display
```

Monitor logs:
```bash
journalctl -u oled-display -f
```

---

## 16. Robot Stack Auto-Launch Service

This service starts `micro_ros_agent` automatically at boot — no manual `mybot-launch` needed.
Camera and lidar are opt-in launch arguments now, and motion is opt-in via `enable_motion:=true`, so unplugged hardware
does not take down the stack and the robot will not drive at boot. Create it after the robot stack is working correctly with `mybot-launch`.
The service now targets the stable ESP32 USB by-id path, not a hardcoded `/dev/ttyACM0`.

```bash
sudo nano /etc/systemd/system/robot-launch.service
```

Paste:
```ini
[Unit]
Description=Robot Launch (micro_ros_agent + sensors)
After=network.target

[Service]
Type=simple
User=ryan
Environment="PYTHONUNBUFFERED=1"
ExecStartPre=/bin/bash -c "rm -f /dev/shm/fastrtps_* && sudo fuser -k /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00 2>/dev/null; sleep 1"
ExecStart=/bin/bash -c "source /opt/ros/humble/setup.bash && source /home/ryan/mybot_ws/install/setup.bash && source /home/ryan/microros_ws/install/setup.bash && ros2 launch articubot_one launch_robot.launch.py"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`ExecStartPre` kills any stale process holding the ESP32 USB serial device and waits 1 s for the bridge to settle.
`Restart=on-failure` (not `always`) — does not restart on clean exit (e.g., intentional stop).

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable robot-launch
sudo systemctl start robot-launch
sudo systemctl status robot-launch
```

Monitor logs:
```bash
journalctl -u robot-launch -f
```

**Boot sequence (fully automatic):**
1. Pi boots → `robot-launch.service` starts `micro_ros_agent` on the ESP32 USB by-id path
2. `oled-display.service` starts after basic networking → reads battery telemetry directly from the ESP32 Telnet stream
3. ESP32 boots → pings for 30 s → resets via watchdog if no agent → on next boot finds agent → connects
4. Display shows `IP`, `BAT`, `AGE`, `ESP32 ONLINE/OFFLINE`, and `ROS UP/DOWN` once telemetry is available; motion remains disabled until `enable_motion:=true` is used

No manual intervention needed after power-on.

### Display layout

The OLED is intentionally compact and ordered top-to-bottom as:

1. `<Pi IP>`
2. `<voltage>V  <current>A`
3. `ROS OK  ESP OK`
4. `UPTIME mm:ss` or `h:mm:ss`

This layout is still being tuned. The battery feed is correct and direct from
the ESP32, but spacing and icon sizing may still change.

---

## 17. Restore SLAM Map

Copy the saved map from the dev machine or backup:

```bash
mkdir -p ~/mybot_ws/maps
scp ryan@dev:~/mybot_ws/maps/my_map.* ~/mybot_ws/maps/
```

---

## 18. Verify Everything

### Check SPI devices exist
```bash
ls /dev/spidev*
```

### Check udev symlinks after plugging in hardware
```bash
ls /dev/rplidar /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00
```

### Launch robot stack
```bash
mybot-launch
```

Expected output: micro_ros_agent connects, `/diff_cont/odom`, `/imu/imu`, `/battery_state` publishing.
Motion is off by default; to drive, pass `enable_motion:=true` to the launch file.
For low-level motor tuning, use the ESP32 bench firmware in `src/esp32_microros/test/test_pid_bench`; keep that off the Pi bridge.
To enable sensors when they are physically connected, pass `enable_lidar:=true enable_camera:=true` to the launch file.
The OLED status display reads battery telemetry directly from the ESP32 Telnet stream, so it can stay useful even when the ROS bridge is not active.

### Check OLED service
```bash
sudo systemctl status oled-display
```

### Check robot-launch service
```bash
sudo systemctl status robot-launch
```

Expected: `active (running)` — if failed, check `journalctl -u robot-launch -n 20`.

---

## Files Not in Git (must recreate manually)

| File | Purpose |
|------|---------|
| `/etc/systemd/system/oled-display.service` | OLED display boot service |
| `/etc/systemd/system/robot-launch.service` | Auto-launch robot stack at boot |
| `/etc/sudoers.d/ryan` | Passwordless sudo |
| `/etc/udev/rules.d/99-mybot.rules` | Device symlinks |
| `~/mybot_ws/maps/my_map.pgm` + `.yaml` | Saved SLAM map |
| `~/microros_ws/` | micro-ROS agent (built from source) |
| `~/librealsense/` | librealsense source build |

---

## Common Issues

### SSH host key mismatch after reflash
```bash
ssh-keygen -f ~/.ssh/known_hosts -R mybot
ssh-keygen -f ~/.ssh/known_hosts -R 192.168.86.33
```

### GPIO/SPI works with sudo but fails without it
Groups not active in current session. Log out and back in after `usermod -aG`.

### RealSense color stream fails (xioctl timeout)
librealsense was installed from apt (kernel UVC backend). Rebuild from source with `FORCE_RSUSB_BACKEND=ON` per section 7. The D435 may also need a physical replug after Pi reboot.

### micro_ros_agent not found
`source ~/microros_ws/install/setup.bash` missing. Add to `.bashrc` (section 14) or the mybot-launch alias handles it.

### Display works on service restart but dark on cold power cycle
Three separate cold-boot issues — all must be fixed:

**1. GPIO group membership (most common cause)**
RPi.GPIO silently does nothing if the user isn't in the gpio/spi/dialout groups. No exceptions
are thrown. "Display init OK" is logged. The display stays completely dark.
Diagnosis: probe DC pin (pin 22) to GND with multimeter while running `GPIO.output(25, GPIO.HIGH)`.
Should read ~3.3V. If it reads ~0.2V, groups are missing or the session predates the `usermod`.
Fix: `sudo usermod -aG gpio,spi,i2c,dialout ryan` then log out and back in.

**2. SPI controller not primed at cold boot**
The first SPI transaction after a fresh kernel SPI controller init is unreliable. The init sequence
runs without errors but commands don't reach the display. Fixed in `oled_display_node.py` with a
dummy `0x00` byte sent while RST is LOW (display ignores it) before the real init sequence.

**3. SPI speed too high at cold boot**
1MHz is unreliable while the Pi SPI hardware is still settling at cold boot. Node uses 100kHz.

### Display shows all-white and stays white
Init sequence sent `0xA5` (all-pixels-on) but the `0xA4` (resume-to-GDDRAM) was missing or
the addressing mode is wrong. Check that `_init_display` sends `0x20 0x02` (page mode) — not
`0x20 0x00` (horizontal mode). The `_show()` method uses page addressing commands (`0xB0+page`)
which only work in page mode.

### SPI device not found (`/dev/spidev0.0` missing)
SPI not enabled. Check `/boot/firmware/config.txt` for `dtparam=spi=on`, reboot.

### Display shows STARTING or ESP32 OFFLINE
The display no longer depends on DDS. It reads battery telemetry directly from the ESP32 Telnet
stream, so the only reasons it should show `STARTING` or `ESP32 OFFLINE` are: the ESP32 is not
powered, Wi-Fi has not come up, or the Telnet telemetry stream has gone stale.

**Self-healing fix (built into `oled_display_node.py`):** if no ESP32 battery telemetry is received
within 30 s, the node calls `os._exit(1)`. Systemd (`Restart=always`, `RestartSec=5`) restarts it.
The cycle repeats until the ESP32 telemetry stream is available again.

**No action needed** — this is automatic. Just boot the Pi, then run `mybot-launch` as normal. The
oled node will show data within 35 s of the ESP32 connecting.

If you want immediate data without waiting for the auto-restart cycle:
```bash
sudo systemctl restart oled-display   # after mybot-launch is running
```

### Display stops updating during motor tuning
The OLED service and the motor-test runner both read the ESP32 Telnet stream. The ESP32 Telnet
server is effectively single-client, so motor tuning can starve or stale the OLED data feed.

Temporary fix while tuning motors:
```bash
sudo systemctl stop oled-display.service      # before encoder-count floor tests
sudo systemctl restart oled-display.service   # after tests
```

Long-term fix: move OLED status off the exclusive ESP32 Telnet stream, or add a Pi-side telemetry
multiplexer that owns the ESP32 Telnet connection and fans data out to the OLED and test tooling.

### ESP32 not reconnecting after Pi reboot (requires manual reset button)
HWCDC (native USB) gets into an inconsistent state when the Linux USB host re-enumerates during
reboot. The ESP32 enters WAITING state but `rmw_uros_ping_agent()` always times out because the
USB CDC layer is confused.

**Self-healing fix (built into firmware):** if in WAITING state for > 30 s with no agent,
`esp_restart()` is called. This fully reinitializes the USB peripheral — the host picks up the ESP32 USB device again and micro_ros_agent reconnects automatically.

**No action needed** — just power-cycle or reboot normally. With `robot-launch.service` running,
the full boot sequence is automatic (see §16).

### luma.oled — do not use
luma.oled's `ssd1309` class is an empty alias for `ssd1306`. It sends the SSD1306 charge pump
command `0x8D 0x14` which is undefined on the SSD1309 and corrupts initialization silently.
Use spidev + RPi.GPIO directly as in `oled_display_node.py`.
