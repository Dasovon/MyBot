# Floor Test Tuning Log

This log tracks each floor-test iteration, the firmware or launch changes that caused the result, and the measured outcome. Keep raw Telnet captures for detailed review, but use this file as the tuning history.

## Analysis Rule

Future tuning decisions should compare the latest three completed tests whenever three comparable results exist. Until then, compare all available completed tests. Each entry should include the firmware constants or launch changes under test so regressions can be traced to a specific change.

## Current Test Protocol

Robot stack:

- Pi: `mybot` / `192.168.86.33`
- ESP32 Telnet: `esp32-mybot.local:23`
- Dev workspace: `/home/ryan/dev_ws`
- Repo: `/home/ryan/dev_ws/src/articubot_one`

Motion sequence as of Floor Test 3:

1. Forward return test: command `linear.x = 0.35`, stop when both wheels reach `4728` counts, nominal 1.0 m forward
2. Backward return test: command `linear.x = -0.35`, stop when both wheels reach `4728` counts, nominal 1.0 m backward
3. Left rotation: command `angular.z = 1.5`, stop when both wheels reach `2659` counts, nominal 360 degrees left
4. Right rotation: command `angular.z = -1.5`, stop when both wheels reach `2659` counts, nominal 360 degrees right

Count math:

```text
WHEEL_RADIUS = 0.034 m
WHEEL_DIAMETER = 0.068 m = 68 mm
WHEEL_CIRCUMFERENCE = 0.2136 m
ENC_CPR = 1010 counts/rev
1 meter = 4728 counts
360-degree in-place turn = pi * WHEEL_SEP = 0.5623 m per wheel = 2659 counts
```

Goal:

- Robot should attempt to end in the same physical spot and heading.
- Use physical displacement and heading error as part of the report, in addition to encoder/velocity metrics.

Each move is followed by a zero command and a 2 second settle.

CSV logging defaults to active-motion samples only to avoid thousands of low-value zero-command rows.

Safety rule:

- Every automated test runner exit must publish zero Twist to upstream motion command paths: `/cmd_vel_joy` and `/cmd_vel`.
- Direct zero publishing to `/diff_cont/cmd_vel_unstamped` is disabled by default because creating a second publisher on the micro-ROS command topic can perturb FastDDS/micro-ROS matching. Use `--stop-output-topic` only as an explicit emergency/debug path.
- Do not leave background `ros2 topic pub` processes running over SSH. If a manual probe is needed, use a bounded command or verify and kill the publisher PID immediately.
- If motors continue after a test or probe, send repeated zero commands first, then stop or kill the Pi motion stack.

Previous short-test sequence used for Floor Test 1 and Floor Test 2:

1. Forward: `linear.x = 0.10`, `angular.z = 0.0`, 1.5 seconds
2. Backward: `linear.x = -0.10`, `angular.z = 0.0`, 1.5 seconds
3. Left spin: `linear.x = 0.0`, `angular.z = 0.5`, 1.5 seconds
4. Right spin: `linear.x = 0.0`, `angular.z = -0.5`, 1.5 seconds

## Baseline Before Floor Test 1

Firmware constants:

```text
KP = 28.0
KI = 9.0
KD = 0.0
KI_MAX = 24.0
START_PWM_SEED = 120.0
RUN_PWM_FLOOR = 72.0
RUN_PWM_FLOOR_ACTUAL = 2.0
RUN_PWM_START_HOLD_MS = 400
CMD_TIMEOUT_MS = 3000
ARM_ZERO_HOLD_MS = 1000
VEL_ALPHA = 0.2
REVERSAL_COAST_VEL = 3.0
CMD_FRESH_FOR_PING_MS = 750
```

Relevant stability fixes already applied:

- `twist_mux` and `vel_smoother.py` use UDP-only FastDDS profile `src/articubot_one/config/fastdds_no_shm.xml`.
- `micro_ros_agent` stays on default FastDDS.
- `now = millis()` is refreshed immediately after `rclc_executor_spin_some()` to avoid unsigned timeout underflow.
- Agent-lost handler calls `reset_motion_state()`.
- Connected-state ping is suppressed while command traffic is fresh: `cmd_age < CMD_FRESH_FOR_PING_MS`.

## Floor Test 1

Date: 2026-05-17

Raw Telnet capture:

```text
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/archive-short-protocol/floor_test_1.log
```

Change under test:

- First run after connection fixes.
- No PID/preseed tuning changes yet.

Result summary:

| Move | Encoder delta L/R | Symmetry | Target | Avg filtered actual | Result |
|---|---:|---:|---:|---:|---|
| Forward `0.10 m/s` | `+2280 / +2326` | `2.0%` divergence | `+2.94 / +2.94 rad/s` | `+3.40 / +3.44 rad/s` | Symmetric, too fast |
| Backward `-0.10 m/s` | `-1352 / -1317` | `2.6%` divergence | `-2.94 / -2.94 rad/s` | `-3.41 / -3.39 rad/s` | Symmetric, too fast |
| Left spin `+0.5 rad/s` | `-1451 / +1398` | ratio `-1.04` | `-1.32 / +1.32 rad/s` | `-2.46 / +2.38 rad/s` | Symmetric, much too fast |
| Right spin `-0.5 rad/s` | `+879 / -811` | ratio `-1.08` | `+1.32 / -1.32 rad/s` | `+2.38 / -2.13 rad/s` | Symmetric, too fast |

Connection:

- `1` agent-lost line occurred during the setup restart window.
- `0` agent-lost events during motion.
- `0` `armed=0` events during motion.

Battery:

- Start: `12.48 V`
- End: `12.45 V`
- Min observed: `12.42 V`

Analysis:

- Connection stability passed.
- L/R symmetry was good.
- Main problem was speed overshoot, especially spin commands.
- Root cause was attributed to `START_PWM_SEED = 120`, because the preseed formula makes first-tick output equal `START_PWM_SEED` regardless of low target speed.

Decision after Test 1:

- Do not change L/R calibration.
- Reduce startup/preseed aggressiveness and integral clamp.

## Floor Test 2

Date: 2026-05-17

Raw Telnet capture:

```text
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/archive-short-protocol/floor_test_2.log
```

Change under test:

```text
KI_MAX:         24.0 -> 12.0
START_PWM_SEED: 120.0 -> 60.0
RUN_PWM_FLOOR:  72.0 -> 55.0
```

Unchanged:

```text
KP = 28.0
KI = 9.0
KD = 0.0
VEL_ALPHA = 0.2
RUN_PWM_FLOOR_ACTUAL = 2.0
RUN_PWM_START_HOLD_MS = 400
```

Result summary:

| Move | Encoder delta L/R | Symmetry | Target | Avg filtered actual | Result |
|---|---:|---:|---:|---:|---|
| Forward `0.10 m/s` | `+1153 / +1142` | `1.0%` divergence | `+2.94 / +2.94 rad/s` | `+2.57 / +2.45 rad/s` | Symmetric, slightly slow |
| Backward `-0.10 m/s` | `-347 / -347` | `0.0%` divergence | `-2.94 / -2.94 rad/s` | `-1.66 / -1.63 rad/s` | Symmetric, too slow |
| Left spin `+0.5 rad/s` | `-597 / +886` | ratio `-0.67` | `-1.32 / +1.32 rad/s` | `-1.50 / +1.37 rad/s` | Closer speed, asymmetric |
| Right spin `-0.5 rad/s` | `+542 / -524` | ratio `-1.03` | `+1.32 / -1.32 rad/s` | `+1.86 / -1.76 rad/s` | Symmetric, slightly fast |

Connection:

- `1` agent-lost line occurred during the setup restart window.
- `0` agent-lost events during motion.
- `0` `armed=0` events during motion.

Battery:

- Start: `12.44 V`
- End: `12.42 V`
- Min observed: `12.38 V`

Observations:

- Startup burst was greatly reduced.
- Forward tracking is near usable but slightly slow.
- Backward is now significantly under target.
- Right spin symmetry is good and speed is much closer than Test 1.
- Left spin speed is closer than Test 1, but left/right count symmetry worsened.
- Apparent large count jumps in logs still look like dropped Telnet log lines because calculated `act` values remained plausible.

Current tuning state after Test 2:

```text
KP = 28.0
KI = 9.0
KD = 0.0
KI_MAX = 12.0
START_PWM_SEED = 60.0
RUN_PWM_FLOOR = 55.0
RUN_PWM_FLOOR_ACTUAL = 2.0
RUN_PWM_START_HOLD_MS = 400
VEL_ALPHA = 0.2
CMD_FRESH_FOR_PING_MS = 750
```

Open questions for next tuning decision:

- Whether `START_PWM_SEED = 60` is too low for backward motion under floor load.
- Whether `RUN_PWM_FLOOR = 55` is too low for reverse direction or low-speed spin.
- Whether left spin asymmetry is mechanical/traction, encoder noise, or tuning interaction.
- Whether a direction-specific floor or a slightly higher floor is needed before changing PID gains.

## Invalid Count-Based Attempts

Date: 2026-05-17

Files:

```text
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/invalid-cmd-vel-route/
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/debug-command-path-2026-05-17/
```

What happened:

- Initial count-based baseline attempts used `/cmd_vel`; ROS showed the route at higher levels, but ESP32 Telnet targets stayed at zero, so those CSVs are not valid motion baselines.
- Follow-up troubleshooting used `/cmd_vel_joy` and direct `/diff_cont/cmd_vel_unstamped` probes. A manual SSH-launched publisher was not killed cleanly and motors continued turning until repeated zero commands and process kills stopped motion.

Changes made after this:

- `pid_sequence_test.py` now logs active-motion samples only by default.
- `pid_sequence_test.py` now records `turn_angular_rads` in CSV metadata.
- `pid_sequence_test.py` now supports angular-only `one_turn` commands.
- `pid_sequence_test.py` now sends encoder reset over the existing Telnet monitor socket.
- `pid_sequence_test.py` briefly published zero Twist to `/cmd_vel_joy`, `/cmd_vel`, and `/diff_cont/cmd_vel_unstamped` during `force_stop()`, but later testing showed direct output-topic publishers can poison later micro-ROS command delivery.
- `pid_sequence_test.py` now skips the nonzero preflight for `one_turn`; counted tests reset encoders after arming, then go directly into the active counted move.
- `pid_sequence_test.py` now defaults `force_stop()` to `/cmd_vel_joy` and `/cmd_vel` only; `--stop-output-topic` exists for explicit emergency/debug use.

Decision:

- Do not use these CSVs for PID tuning.
- Restart the robot launch stack before the next valid baseline.
- Use only the bounded test runner for motion tests; avoid manual background publishers during floor testing.

## Partial Per-Move Restart Attempt

Date: 2026-05-17

Files:

```text
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/debug-command-path-2026-05-17/per-move-restart-attempt/
```

Change under test:

- Pi-local runner.
- Runner forced UDP-only with `FASTRTPS_DEFAULT_PROFILES_FILE=fastdds_no_shm.xml`.
- Robot stack restarted before each segment.
- Runner still had direct `/diff_cont/cmd_vel_unstamped` zero publisher enabled in `force_stop()`.

Result:

| Segment | ESP32 targets | Motion | Use for tuning |
|---|---:|---:|---|
| Baseline 1 forward | nonzero | yes | partial/debug only |
| Baseline 1 backward | zero | no | no |
| Baseline 1 left 360 | zero | no | no |
| Baseline 1 right 360 | zero | no | no |
| Baseline 2 forward | zero | no | no |
| Baseline 2 backward | zero | no | no |

Analysis:

- One fresh-stack forward run can work.
- After a runner exits while it has created a direct publisher on `/diff_cont/cmd_vel_unstamped`, later ESP32 command delivery frequently fails even after Pi-side stack restarts.
- Treat this as a bridge/DDS matching blocker, not a PID result.

Decision:

- Remove direct output-topic zero publisher from the default runner stop path.
- Retry valid baselines with upstream zero stops only.

## Upstream-Only Stop Attempt

Date: 2026-05-17

Files:

```text
/home/ryan/dev_ws/src/articubot_one/docs/test-results/floor-tests/debug-command-path-2026-05-17/upstream-stop-attempt/
```

Change under test:

- Direct `/diff_cont/cmd_vel_unstamped` stop publisher removed from the default runner stop path.
- Pi-local runner still forced UDP-only.
- Robot stack restarted before the attempt.

Result:

| Segment | ESP32 targets | Motion | Use for tuning |
|---|---:|---:|---|
| Baseline 1 forward | zero | no | no |
| Baseline 1 backward | zero | no | no |
| Baseline 1 left 360 | zero | no | no |
| Baseline 1 right 360 | zero | no | no |

Analysis:

- Once the bridge entered the bad state, Pi-side stack restarts were not enough to restore command delivery.
- The ESP32 continued publishing Telnet/encoder/battery data, but its command subscription did not receive nonzero commands.
- This is not a PID tuning condition. It is a DDS/micro-ROS command delivery blocker.

Current blocker:

- Need to restore reliable `/cmd_vel_joy -> twist_mux -> vel_smoother.py -> /diff_cont/cmd_vel_unstamped -> micro_ros_agent -> ESP32` delivery before collecting three valid baselines.
- Next likely recovery step is an ESP32 reset or full micro-ROS agent plus ESP32 reconnect cycle, then a single short route validation before baselines.

## DDS Multi-Invocation Blocker Root Cause and Fix

Date: 2026-05-17

Root cause:

- Each separate `ros2 run pid_sequence_test.py --profile one_turn` invocation creates a new DDS
  participant. When the process exits, that participant tears down. The micro-ROS agent's DDS
  matching for `/diff_cont/cmd_vel_unstamped` enters a degraded state after participant churn.
- After the first post-recovery invocation works, every following invocation fails: ESP32 Telnet
  is alive and streaming encoder/battery data, and `bridge_cmd_count` shows commands arriving in
  the ESP32's `[cmd]` lines, but `enc_tgt_l/r = 0.0` and the motors do not move. The subscription
  is present at the DDS layer but the command values are zeroed at the micro-ROS bridge level.
- Direct publishing from the dev machine (a separate network UDP path) continues to work
  during this degraded state, confirming the blocker is Pi-local participant churn, not the
  network path.

Fix:

- Added `--profile floor_baseline` to `pid_sequence_test.py`.
- Runs all four canonical counted moves inside one process: fwd 1m → bwd 1m → left 360° → right 360°.
- DDS participant is created once per baseline pass and torn down only after all four moves complete.
- The encoder is reset between each counted step via the existing Telnet monitor socket.
- A warmup period (default 0.5 s via `--warmup`) separates each move to let the robot settle.
- Between steps the state machine goes: stop → encoder reset → warmup → active (counted) → stop → ...

Canonical baseline command:

```bash
# On dev machine — Pi stack must be running with enable_motion:=true
# Stop OLED first:
ssh ryan@mybot "sudo systemctl stop oled-display.service"

ros2 run articubot_one pid_sequence_test.py \
  --profile floor_baseline \
  --turn-linear 0.35 \
  --floor-spin-rate 1.5 \
  --stop-hold 2.0 \
  --warmup 0.5 \
  --output ~/dev_ws/floor_baseline_$(date +%Y%m%d_%H%M%S).csv

# After tests:
ssh ryan@mybot "sudo systemctl restart oled-display.service"
```

Expected per-step count targets at 1010 CPR:

| Move | linear.x | angular.z | goal counts |
|---|---:|---:|---:|
| fwd_1m | +0.35 | 0.0 | 4728 |
| bwd_1m | -0.35 | 0.0 | 4728 |
| left_360 | 0.0 | +1.5 | 2659 |
| right_360 | 0.0 | -1.5 | 2659 |

Validity check: all four steps must reach their count target (not time out) for the data to be
usable for PID tuning. A timed-out step means command delivery is still broken.

## OLED Display Freeze During Motor Tuning

Date: 2026-05-17

Symptom:

- The chassis OLED stopped updating while floor-test automation was being run.

Cause:

- `oled_display_node.py` reads battery telemetry directly from the ESP32 Telnet stream.
- The ESP32 Telnet server only supports one useful client at a time.
- The floor-test runner also uses the ESP32 Telnet stream for encoder counts, targets, actual velocity, and filtered velocity.
- During motor tuning, the OLED service and the test runner can fight over the same Telnet stream. The display can show stale data, and the runner can collect stale or missing encoder samples.

Temporary motor-tuning fix:

```bash
# Before motor tuning / floor-test captures:
ssh ryan@mybot "sudo systemctl stop oled-display.service"

# After motor tuning:
ssh ryan@mybot "sudo systemctl restart oled-display.service"
```

Operational rule until the display data path is redesigned:

- Keep `oled-display.service` stopped while running encoder-count-based motor tests.
- Restart `oled-display.service` after tests so the display updates again.
- Do not treat OLED staleness during motor tuning as a motor-control failure.

Deferred permanent fix:

- Move the OLED battery/status data path off the exclusive ESP32 Telnet stream.
- Better options: publish a lightweight status topic, write a small local status cache on the Pi from ROS/agent state, or make a single Telnet multiplexer process that fans ESP32 telemetry out to both OLED and test tooling.
