# OLED Display — Archived Notes

This file is kept only as a historical implementation note.

Use these canonical docs instead:
- [README.md](/home/ryan/dev_ws/src/articubot_one/README.md)
- [docs/pi-setup.md](/home/ryan/dev_ws/src/articubot_one/docs/pi-setup.md)
- [HARDWARE_MEMORY.md](/home/ryan/dev_ws/src/articubot_one/HARDWARE_MEMORY.md)
- `src/articubot_one/scripts/oled_display_node.py`

Current OLED behavior:
- starts at boot as `oled-display.service`
- reads battery telemetry directly from the ESP32 Telnet stream
- displays `IP`, `BAT`, `AGE` link uptime, `ESP32 ONLINE/OFFLINE`, and `ROS UP/DOWN`

Layout note:
- the data path is stable, but the final font size, spacing, and icon sizing are
  still being tuned
