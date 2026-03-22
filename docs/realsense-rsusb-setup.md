# RealSense D435 — RSUSB Backend Setup

## Problem
The apt-installed `ros-humble-librealsense2` uses the kernel V4L2/UVC driver. On the Raspberry Pi 4, UVC extension unit queries (`xioctl(UVCIOC_CTRL_QUERY)`) time out, preventing the RGB camera from retrieving intrinsics. Depth works; color fails.

## Solution
Build librealsense **v2.56.4** from source with `FORCE_RSUSB_BACKEND=ON` (bypasses kernel UVC, uses libusb directly). Replace the apt `.so` with the custom build.

Must use **v2.56.4** — not latest. The apt `ros-humble-realsense2-camera` plugin links against `librealsense2.so.2.56` (SONAME). Building at any other minor version breaks linkage.

## Steps (run on Pi)

```bash
# 1. Remove apt librealsense
sudo apt remove ros-humble-librealsense2*

# 2. Install build deps
sudo apt install -y libusb-1.0-0-dev libssl-dev cmake libgtk-3-dev

# 3. Clone and checkout matching version
git clone https://github.com/IntelRealSense/librealsense ~/librealsense
cd ~/librealsense && git checkout v2.56.4

# 4. Configure
mkdir build && cd build
cmake .. -DFORCE_RSUSB_BACKEND=ON -DBUILD_EXAMPLES=OFF -DBUILD_GRAPHICAL_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release

# 5. Build — use -j2, NOT -j4 (Pi 4 OOMs and reboots with -j4)
nohup make -j2 > /tmp/librealsense_build.log 2>&1 &
# Monitor: tail -2 /tmp/librealsense_build.log (~30 min)

# 6. Install
sudo make install && sudo ldconfig

# 7. Reinstall ROS camera package (apt will pull back ros-humble-librealsense2)
sudo apt install -y ros-humble-realsense2-camera ros-humble-realsense2-description

# 8. Replace apt .so with our RSUSB build (same version/SONAME — safe)
sudo cp /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4 \
        /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4.bak
sudo cp /usr/local/lib/librealsense2.so.2.56.4 \
        /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so.2.56.4

# 9. Reload udev rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Verification

```bash
# Check RSUSB backend is active (look for messenger-libusb.cpp, NOT UVCIOC_CTRL_QUERY)
strings /tmp/robot_launch.log | grep -i 'messenger-libusb\|UVCIOC'

# Check both topics publishing at 15 FPS
source /opt/ros/humble/setup.bash
ros2 topic hz /camera/camera/color/image_raw
ros2 topic hz /camera/camera/depth/image_rect_raw
```

## Key Notes
- `LD_LIBRARY_PATH` tricks don't work — ROS `setup.bash` prepends `/opt/ros/humble/lib/aarch64-linux-gnu` which overrides ldconfig
- D435 may not re-enumerate after Pi reboot — physically replug USB if `lsusb | grep 8086` shows nothing
- Backup of original apt .so saved at `.so.2.56.4.bak`
- Udev rules file: `/etc/udev/rules.d/99-realsense-libusb.rules` (product ID `0b07` included)

## Hardware Info
- Device: Intel RealSense D435 (ID 8086:0b07)
- Bus: USB 3.2 Gen 1 (Bus 002)
- FW: 5.17.0.10, Serial: 244622071235
- Streams: Depth Z16 640x480@15fps, Color RGB8 640x480@15fps
