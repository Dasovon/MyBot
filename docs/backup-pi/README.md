# Pi Backup — 2026-05-21

Snapshot of all Pi-side files that are NOT tracked in the main repo.
Created before dev machine root password recovery attempt.

## Files in this backup

| File | Pi path | Notes |
|------|---------|-------|
| `robot-launch.service` | `/etc/systemd/system/robot-launch.service` | Auto-starts robot stack at boot |
| `oled-display.service` | `/etc/systemd/system/oled-display.service` | Auto-starts OLED display at boot |
| `99-mybot.rules` | `/etc/udev/rules.d/99-mybot.rules` | udev symlinks for rplidar + ESP32 |
| `bashrc` | `~/.bashrc` | Includes mybot-launch alias and ROS source lines |
| `bash_aliases` | `~/.bash_aliases` | Additional aliases |
| `my_map.yaml` | `~/mybot_ws/maps/my_map.yaml` | SLAM map metadata |
| `my_map.pgm.b64` | `~/mybot_ws/maps/my_map.pgm` | SLAM map image (base64 encoded) |
| `fastdds_no_shm.xml` | local config reference | Already in repo at config/ |

## Pi state at backup time

- OS: Raspberry Pi OS (64-bit), hostname: mybot, IP: 192.168.86.33
- ROS: Humble (apt), workspace: ~/mybot_ws
- micro-ROS agent: built from source at ~/microros_ws
- librealsense: v2.56.4 built from source at ~/librealsense, FORCE_RSUSB_BACKEND=ON
- ESP32 firmware: latest from this repo, flashed via OTA
- Services enabled: robot-launch.service, oled-display.service
- User: ryan, groups include gpio, spi, i2c, dialout

## Restore robot-launch.service

```bash
sudo cp robot-launch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable robot-launch.service
sudo systemctl start robot-launch.service
```

## Restore oled-display.service

```bash
sudo cp oled-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oled-display.service
sudo systemctl start oled-display.service
```

## Restore udev rules

```bash
sudo cp 99-mybot.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Restore SLAM map

```bash
mkdir -p ~/mybot_ws/maps
cp my_map.yaml ~/mybot_ws/maps/
base64 -d my_map.pgm.b64 > ~/mybot_ws/maps/my_map.pgm
```

## Restore ryan sudoers (NOPASSWD for hardware commands)

```bash
echo 'ryan ALL=(ALL) NOPASSWD: /usr/bin/fuser, /bin/fuser' | sudo tee /etc/sudoers.d/ryan
sudo chmod 440 /etc/sudoers.d/ryan
```

## Rebuild micro-ROS agent (if ~/microros_ws lost)

See docs/pi-setup.md for full rebuild steps.
Key: ros-humble-micro-ros-agent is NOT in apt for arm64 — must build from source.

## Rebuild librealsense (if ~/librealsense lost)

```bash
git clone https://github.com/IntelRealSense/librealsense ~/librealsense
cd ~/librealsense && git checkout v2.56.4
mkdir build && cd build
cmake .. -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF -DBUILD_GRAPHICAL_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
make -j2 && sudo make install && sudo ldconfig
sudo apt install ros-humble-realsense2-camera ros-humble-realsense2-description
sudo cp /usr/local/lib/librealsense2.so.2.56.4 /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4
```

## Pi ROS packages installed (via apt)

See the list at the bottom — all installable via:
```bash
sudo apt install -y ros-humble-robot-localization ros-humble-navigation2 \
  ros-humble-nav2-bringup ros-humble-realsense2-camera-msgs \
  ros-humble-realsense2-description ros-humble-rplidar-ros \
  ros-humble-twist-mux ros-humble-controller-manager \
  ros-humble-diff-drive-controller ros-humble-joint-state-broadcaster
```
