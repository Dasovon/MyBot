# Movement Validation — 1 Meter Odometry Test

Goal: Drive forward 1 meter, check `/odom` x position, fine-tune `enc_counts_per_rev` if needed.

Current value: `enc_counts_per_rev = 1100` (measured via serial readback, not yet validated)

---

## Step 1 — Launch the robot (on Pi)

```bash
source /opt/ros/humble/setup.bash && source ~/mybot_ws/install/setup.bash
ros2 launch articubot_one launch_robot.launch.py
```

Wait for both controllers to spawn before continuing:
```
[spawner-5]: Loaded diff_cont
[spawner-6]: Loaded joint_broad
```

---

## Step 2 — Monitor odometry (separate terminal)

```bash
source /opt/ros/humble/setup.bash && source ~/mybot_ws/install/setup.bash
ros2 topic echo /odom --field pose.pose.position
```

Note the starting x value (should be ~0.0).

---

## Step 3 — Check encoder signs before driving

```bash
ros2 topic echo /joint_states
```

Push the robot forward by hand a small amount. Both `left_wheel_joint` and `right_wheel_joint` positions should **increase (go positive)**.

- If left goes **negative** for forward motion → encoder direction is inverted. Note it and continue; fix is in Step 7 below.
- If right goes **negative** for forward motion → same issue on right side.

---

## Step 4 — Drive forward 1 meter

Start teleop in a third terminal:

```bash
source /opt/ros/humble/setup.bash && source ~/mybot_ws/install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

- Place a tape measure on the floor.
- Drive forward slowly (~0.1–0.2 m/s) for exactly **1.0 m** measured on the floor.
- Stop the robot.
- Read the x value from the `/odom` terminal.

---

## Step 5 — Calculate correction

Let `R` = the x delta reported by `/odom`, `A` = actual distance driven, `C` = current enc_counts_per_rev.

```
new_enc_counts_per_rev = round(C × (R / A))
```

Logic: if odom under-reports (R < A), enc_counts_per_rev is set too high — decrease it.
If odom over-reports (R > A), enc_counts_per_rev is set too low — increase it.

Example with C=1100, A=1.0m:
| Reported x (R) | New enc_counts_per_rev |
|---|---|
| 0.85 | 935 |
| 0.90 | 990 |
| 0.95 | 1045 |
| 1.00 | 1100 — no change needed |
| 1.05 | 1155 |
| 1.10 | 1210 |

If R is within ~2% of 1.0 (i.e. 0.98–1.02), the current value is close enough and no change is needed.

---

## Step 6 — Apply correction (if needed)

Edit this file:
```
src/articubot_one/description/ros2_control.xacro
```

Line 14 — change the value:
```xml
<param name="enc_counts_per_rev">NEW_VALUE</param>
```

Because this project uses `--symlink-install`, xacro changes take effect on next launch — **no rebuild needed**. Just stop and re-launch the robot, then repeat Steps 2–5 to confirm.

---

## Step 7 — Fix inverted encoder direction (if needed)

If Step 3 showed a wheel counting negative for forward motion, the encoder A/B phases are swapped.

**Option A (hardware):** Swap the Yellow and Green encoder wires for that wheel at the Arduino.

**Option B (firmware):** In `src/ros_arduino_bridge/ROSArduinoBridge/encoder_driver.ino`, find the ISR for the affected wheel and flip the condition:
- Change `if (A == B) pos++` → `if (A != B) pos++` (or vice versa)

After a firmware change, reflash:
```bash
fuser -k /dev/ttyUSB0 2>/dev/null
/home/ryan/bin/arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
/home/ryan/bin/arduino-cli upload --fqbn arduino:avr:nano:cpu=atmega328old --port /dev/ttyUSB0 ~/mybot_ws/src/ros_arduino_bridge/ROSArduinoBridge
```

---

## Watch-outs

- **Robot curves/drifts**: `enc_counts_per_rev` applies equally to both wheels. Drift means one wheel is physically slower or has different tire contact. Check PID or tighten/loosen wheel contact.
- **Teleop feels slow**: Max velocity is capped at 0.5 m/s in `my_controllers.yaml` — intentional for this tuning phase.
- **Serial not found**: Check `ls /dev/ttyUSB*` and confirm Arduino is connected. ROS launch will fail if `/dev/ttyUSB0` is missing.
- **Controllers don't spawn**: Wait the full 3-second delay built into `launch_robot.launch.py`. If they still don't appear, check the launch terminal for hardware plugin errors.

---

## After validation

Once `/odom` x ≈ 1.0 m for a 1 m drive:

1. Update `enc_counts_per_rev` in `ros2_control.xacro` to the final validated value.
2. Update `CLAUDE.md` current status section with the validated value.
3. Next step per tutorial: **mount RPLidar → SLAM with slam_toolbox**.
