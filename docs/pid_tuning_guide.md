# ESP32 Motor PID Tuning Guide

## Our Setup

| Component | Value |
|---|---|
| Robot | Differential drive, JGA25-371 130RPM 45:1 |
| Controller | ESP32-S3 → micro-ROS → Pi |
| Wheel diameter | 68 mm |
| Wheel radius | 0.034 m |
| Wheel separation | 0.179 m |
| Encoder CPR | 1010 counts/rev |
| Control loop | 30 Hz (33 ms/tick) |
| Pi-side smoother | none in current deployment; `twist_mux` feeds the ESP32 directly |
| Telnet monitor | `nc esp32-mybot.local 23` |
| Enc log format | `[enc] tgt=L/R act=L/R filt=L/R` (rad/s, 1 Hz) |

**Key difference from standard tuning**: the ESP32 sees direct `cmd_vel` targets
from `twist_mux`, then applies its own timeout, integral preseed, and motor PWM
slew/reversal handling. Kd is still not useful for startup in this robot because
the EMA encoder filter adds lag and the motors have a hard deadband.
Startup mechanism is **integral preseed** instead.

**Current test note**: the one-turn encoder test now reaches a full wheel
rotation, but the motion is still stop-and-go instead of smooth continuous
drive. Fix that first before spending more time on PID gain changes or longer
rotation tests.

---

## Step 0 — Verify the Pipeline First

Before tuning anything, confirm commands reach the ESP32:

```bash
# Terminal 1: monitor ESP32 over telnet
nc esp32-mybot.local 23

# Terminal 2: send a command and watch tgt in telnet
source /opt/ros/humble/setup.bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.2}, angular: {z: 0.0}}' --rate 10
```

**Pass**: telnet shows `tgt=5.88/5.88` (0.2 m/s → 5.88 rad/s each wheel).
**Fail**: tgt stays 0.00 even though motors spin — pipeline broken.
  Fix: `ssh ryan@mybot "sudo systemctl restart robot-launch.service"` then retry.

**Stop motors between every test:**
```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'
```

For repeatable comparisons, use the test runner:
```bash
ros2 run articubot_one pid_sequence_test.py --profile rebound --output /home/ryan/dev_ws/pid_sequence_log.csv
```
It publishes a fixed sequence, forces a zero-command stop after every move, logs the
robot response to CSV for graphing, and connects to the ESP32 telnet encoder stream
so the wheel response is measured directly. The final summary reports commanded
speed, odom response, encoder actuals, and battery power draw. By default it publishes
to `/cmd_vel_raw`, which matches the active teleop path in the current launch stack.
Pass `--command-topic /diff_cont/cmd_vel_unstamped` if you temporarily bypass the
smoother.

---

## Step 1 — Put Robot on Blocks

Wheels must spin freely. This lets you observe controller behavior without the
robot driving away or hitting walls.

---

## Step 2 — Baseline Test

Run the automated test script to capture a baseline before changing anything:

```bash
# On dev machine
python3 ~/dev_ws/src/articubot_one/scripts/pid_tune_test.py
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

Record: does motor start promptly? Does it track target? Does it oscillate?

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
the first PID update lands near `START_PWM_SEED` PWM. This ensures the motor
starts immediately without waiting for integral to wind up.

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

Pi-side smoother: none in current deployment. If you add one later, keep its limits
consistent with the ESP32 firmware and retune from scratch.

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

# 5. Run test (from dev machine)
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

Latest count-based test:

- Target: 1010 counts
- Observed stop: about 1098 / 1095 counts
- Result: full rotation confirmed
- Behavior: the wheel advanced in bursts, not a smooth continuous turn

That stop-and-go motion is the next problem to fix. Do not move to the
three-rotation test until the one-turn motion is smooth enough to hold a
continuous spin without visible pulsing.
