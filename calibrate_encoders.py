#!/usr/bin/env python3
"""
Encoder calibration helper.
Measures encoder counts per wheel revolution by talking directly to the Arduino.

Usage:
    python3 calibrate_encoders.py
"""

import serial
import time

PORT = "/dev/ttyUSB0"
BAUD = 57600


def send(ser, cmd):
    ser.write((cmd + "\r").encode())
    time.sleep(0.1)
    return ser.read_all().decode(errors="ignore").strip()


def read_encoders(ser):
    response = send(ser, "e")
    # Response format: "<left> <right>"
    parts = response.split()
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    raise ValueError(f"Unexpected response: {repr(response)}")


def main():
    print(f"Connecting to {PORT} at {BAUD} baud...")
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        time.sleep(2)  # let Arduino reset after connection
        ser.read_all()  # flush any startup noise

        print("\n--- Encoder Calibration ---\n")
        print("This will measure counts for ONE full wheel revolution.")
        print("Do one wheel at a time.\n")

        for wheel in ("LEFT", "RIGHT"):
            input(f"[{wheel}] Press ENTER to reset encoders, then rotate the {wheel.lower()} wheel exactly ONE full revolution...")

            send(ser, "r")
            time.sleep(0.1)
            l, r = read_encoders(ser)
            print(f"  Encoders reset → LEFT={l}  RIGHT={r}")

            input(f"  Rotate {wheel.lower()} wheel ONE full revolution, then press ENTER...")

            l, r = read_encoders(ser)
            count = l if wheel == "LEFT" else r
            print(f"  Counts after one rev → LEFT={l}  RIGHT={r}")
            print(f"  >>> {wheel} enc_counts_per_rev = {abs(count)}\n")

        print("Done. Update enc_counts_per_rev in:")
        print("  src/articubot_one/description/ros2_control.xacro")


if __name__ == "__main__":
    main()
