# ESP32 Motor PID Tuning Guide

## Our Setup

| Component | Value |
|---|---|
| Robot | Differential drive, JGA25-371 130RPM 45:1 |
| Controller | ESP32-S3 bench mode for tuning; micro-ROS + Pi for integration |
| Wheel diameter | 68 mm |
| Wheel radius | 0.034 m |
| Wheel separation | 0.179 m |
| Encoder CPR | 1010 counts/rev |
| Control loop | 30 Hz (33 ms/tick) |
| Pi-side smoother | repo custom `vel_smoother.py` in the launch path for integration runs; not used by the ESP32 bench |
| Telnet monitor | `nc esp32-mybot.local 23` |
| Enc log format | `[enc] tgt=L/R act=L/R filt=L/R` (rad/s, 1 Hz) |

**Key difference from standard tuning**: the Pi launch stack includes the repo's
`vel_smoother.py`, which limits step changes before the ESP32 sees them and now
requires a stable zero hold at boot before it forwards motion. The ESP32 still
applies its own timeout, integral preseed, and motor PWM sustain/reversal
handling. Kd is still not useful for startup in this robot because the EMA
encoder filter adds lag and the motors have a hard deadband. Startup mechanism
is **integral preseed** instead.
The ESP32 also requires a short stable zero hold after boot or reconnect before
it will arm motion, so a single startup zero cannot immediately re-enable motion.
For low-level motor tuning, use the ESP32 bench firmware in
`src/esp32_microros/test/test_pid_bench` and capture logs on the dev machine
over telnet. The Pi stays out of this loop until the wheel motion is already
smooth.

**Current test note**: the one-turn encoder test was stalling in a stop-and-go
pattern. I added a sustain-floor in the motor controller, raised the test log
rate, and added adaptive rotation targets so the run can extend from 1 to 3
revolutions when the wheel stays in motion. The latest rerun reached a full
rotation again, so the next step is to tighten smoothness before longer tests.
The current controller also holds the sustain floor through the first part of a
fresh move, so the bridge opening should not kick the wheels immediately.

For the exact Claude Code CLI task script, see
[claude_code_pid_test_instructions.md](./claude_code_pid_test_instructions.md).

### Claude Code CLI Runner

If you are using Claude Code CLI, keep the run focused on the same live path
described above:

1. Use the ESP32 bench first.
2. Use the bridge profile only after bench motion is smooth.
3. Log `cnt`, `tgt`, `act`, `filt`, `pwm`, and `bat`.
4. Watch velocity traces before extending from 1 to 3 revolutions.
5. Stop the motors after every run.

The bridge profile should prove command delivery at zero first, then measure
active-motion smoothness. Bursty velocity is still the blocker if motion pulses.

---

## Step 0 — Use The ESP32 Bench First

Before tuning anything on the Pi stack, confirm the direct ESP32 bench path:

```bash
# Terminal 1: monitor the ESP32 over telnet
nc esp32-mybot.local 23

# Terminal 2: tell the ESP32 to run a bench test
#   t = PID bench
#   p = power sweep
#   r = reset encoders
#   s = stop motors
```

**Pass**: telnet shows `[bench]` lines with `tgt=7.35/7.35` and counts rising
smoothly through the run.
**Fail**: counts or velocity stall in bursts.

The bench firmware is in `src/esp32_microros/test/test_pid_bench`. It logs the
encoder actuals, filtered speed, PWM, and battery directly on the ESP32. Use a
dev machine to capture and graph that output. Do not pull the Pi into this stage.
The bench auto-starts after boot, runs the PID segment, then continues into the
power sweep, so no manual keypress is needed.

For Pi-to-ESP32 communication checks, use the same Python runner with
`--profile bridge`. It logs the same battery, odom, IMU, encoder, and command
fields, but the command sequence is shorter and focuses on command delivery,
stop recovery, and boot-zero behavior rather than gain tuning.
The bridge profile starts with forward motion, then stop, reverse, stop, turn,
stop so the preflight can prove the ESP32 logged a received command before the
rest of the sequence runs.

---

## Step 1 — Put Robot on Blocks

Wheels must spin freely. This lets you observe controller behavior without the
robot driving away or hitting walls.

---

## Step 2 — Baseline Test

Run the automated bridge test script to capture a baseline before changing anything:

```bash
# On dev machine
ros2 run articubot_one pid_sequence_test.py --profile bridge --output /home/ryan/dev_ws/bridge_log.csv
```

Or manually:
```bash
source /opt/ros/humble/setup.bash

# Open telnet in another terminal: nc esp32-mybot.local 23

# Slow forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.10}, angular: {z: 0.0}}' --rate 10
# Wait 4 seconds, then stop:
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'
```

Record: does the command arrive cleanly, does motion stop when asked, and does the bridge stay quiet at boot until it is armed?

---

## Step 3 — Tune Kp (P only first)

Set in `src/esp32_microros/src/main.cpp`:
```cpp
static constexpr float KP     = 20.0f;  // start here
static constexpr float KD     =  0.0f;
static constexpr float KI     =  0.0f;
static constexpr float KI_MAX = 10.0f;
```

Flash: `cd src/esp32_microros && pio run -e esp32-s3-ota --target upload`

Restart agent: `ssh ryan@mybot "sudo systemctl restart robot-launch.service"`

**What to look for in `[enc]` logs:**

| Symptom | Meaning | Fix |
|---|---|---|
| `tgt≠0` but `filt≈0`, motor doesn't spin | Kp too low — P output below deadband (~45 PWM) | Increase Kp |
| Motor starts but `filt` lags far behind `tgt` | Kp too low for tracking | Increase Kp |
| `filt` bounces ±around `tgt` at similar or higher amplitude | Kp too high — oscillating | Decrease Kp |
| `filt` rises quickly, settles near `tgt` | Good Kp |  |

**Deadband math**: Kp × error must exceed ~45 PWM. With a direct command path,
the first PID update from rest can still be too small to overcome motor deadband.
In practice with preseed: Kp=20 works because preseed pre-fills integral for
startup. Without preseed or Ki, Kp needs to be much higher to self-start.

**Good starting range**: Kp = 20–40

---

## Step 4 — Add Ki (integral)

Once Kp is set and motor tracks reasonably:

```cpp
static constexpr float KI     = 5.0f;   // start here
static constexpr float KI_MAX = 10.0f;  // Ki × KI_MAX = max integral contribution
```

**What Ki fixes:**
- Steady-state error (motor runs slower than commanded)
- Startup deadband (integral winds up until it overcomes friction)

**Preseed**: when target transitions from 0 to non-zero, integral is preset so
the first active PID update lands near `START_PWM_SEED` PWM. This gives the
motor a clean start without waiting for integral to wind up.
The controller now also holds the sustain floor through the first part of a
fresh move, so the output does not collapse back under the deadband as soon as
the wheel begins to spin.

```cpp
static constexpr float START_PWM_SEED = 55.0f;  // first-tick PWM (above ~45 deadband)
```

**What to look for:**

| Symptom | Meaning | Fix |
|---|---|---|
| Motor starts instantly, tracks target | Good Ki | — |
| `filt` slowly creeps above `tgt` after settling | Ki too high — windup | Decrease Ki or KI_MAX |
| Slow hunting (oscillation at ~0.5–2 Hz) | Ki too high | Decrease Ki |
| Motor barely responds to stop command | KI_MAX too high (windup) | Decrease KI_MAX |

**Good starting range**: Ki = 3–10, KI_MAX = 5–15

If the robot creeps after stopping or feels sloppy at zero-command transitions,
drop `KI_MAX` to `5.0f` first. That is the first knob I would turn before Kp.

---

## Step 5 — Add Kd (only if needed)

> **Warning for our system**: Kd interacts badly with the EMA velocity filter.
> The filter adds lag — when velocity is rising, the filtered value lags behind
> actual, making the derivative underestimate the rate of change. This causes
> overshoot at startup and oscillation at steady state.
>
> Only use Kd if you observe oscillation that Ki alone cannot fix.
> If you do use it: start small (Kd = 1–3) and increase slowly.

```cpp
static constexpr float KD = 0.0f;  // default — leave at 0
```

---

## Step 6 — On-Floor Straight-Line Test

Once wheels-up tuning is good, put robot on floor:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard \
  --ros-args -p repeat_rate:=10.0
```

Command straight forward (~0.15 m/s). Watch if it curves.

| Symptom | Meaning |
|---|---|
| Curves right | Left wheel faster, or right wheel weaker |
| Curves left | Right wheel faster, or left wheel weaker |

**Do NOT adjust Kp/Ki asymmetrically** to fix a curve. First verify:
- `enc_counts_per_rev` correct (1010 for our motors)
- `wheel_radius` correct (0.034 m)
- `wheel_separation` correct (0.179 m)
- Motor/encoder directions correct

Mechanical asymmetry (friction, wiring resistance) can be trimmed with a small
Ki offset on the lagging wheel — but fix hardware first.

---

## Recommended Starting Values

These are the first values to flash and test. They are not final — adjust based
on what you observe on the floor.

```cpp
KP             = 20.0f
KD             =  0.0f
KI             =  5.0f
KI_MAX         = 10.0f   // ← adjust this first if stop feel is wrong
START_PWM_SEED = 55.0f
VEL_ALPHA      =  0.2f   // EMA filter — keep, suppresses encoder EMI noise
REVERSAL_COAST_VEL = 3.0f  // rad/s
CMD_TIMEOUT_MS     = 1000  // ms
```

Pi-side smoother: `vel_smoother.py` is in the current launch path for integration
runs. Keep its limits consistent with the ESP32 firmware and retune from scratch
if you change either side.

### Stop-feel tuning

**If the robot feels slow to stop or creeps after releasing a key**: lower `KI_MAX`
first — high KI_MAX means the integral is wound up and keeps pushing even after
the command goes to zero. Halve KI_MAX (e.g., 10 → 5) before touching Kp.

**If the robot still creeps after lowering KI_MAX**: lower Ki slightly (5 → 3).

**Do not lower Kp to fix stop behavior** — Kp only affects how hard the motor
is driven relative to current error. KI_MAX is what limits the integral windup
that causes creep.

---

## Flash + Test Cycle

```bash
# 1. Edit constants in src/esp32_microros/src/main.cpp
# 2. Flash OTA
cd ~/dev_ws/src/articubot_one/src/esp32_microros
pio run -e esp32-s3-ota --target upload

# 3. Restart agent (ESP32 OTA reboot confuses micro_ros_agent)
ssh ryan@mybot "sudo systemctl restart robot-launch.service"

# 4. Open telnet monitor
nc esp32-mybot.local 23

# 5. Make sure the command path has seen a stable zero hold since boot
#    before the first move command.

# 6. Run test (from dev machine)
source /opt/ros/humble/setup.bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.15}, angular: {z: 0.0}}' --rate 10
# Observe [enc] lines — stop after 5 seconds:
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'
```

**Reading the telnet log:**
```
[enc] tgt=4.41/4.41 act=4.15/4.22 filt=4.38/4.40
        ^^^^^^^^^^^     ^^^^^^^^^^      ^^^^^^^^^^^^
        wheel targets   raw encoder     EMA-filtered
        (rad/s L/R)     velocity        velocity (used by PID)
```

Good tracking: `filt` within ~10–15% of `tgt`, stable, not oscillating.

### Current one-turn result

Latest count-based test after the sustain-floor fix:

- Target: 1010 counts
- Observed stop: about 1432 / 1447 counts
- Result: full rotation confirmed again
- Behavior: the wheel now keeps moving through the turn instead of stalling

Use this as the new baseline. The next pass should graph velocity and let the
adaptive rotation test extend naturally toward 3 revolutions when motion stays
healthy.
