# Claude Code CLI PID Test Instructions

Use this as the working script for the next Claude Code CLI session. The goal
is to evaluate wheel motion directly on the ESP32, before any more Pi-side
integration work.

## Goal

1. Verify the wheel can complete a rotation cleanly on the ESP32 bench.
2. Run the Pi-to-ESP32 bridge test with the same CSV fields as the PID runner.
3. Log velocity, not just encoder counts, so we can see ramp-up and ramp-down.
4. Extend the test dynamically from 1 to 3 revolutions when motion stays
   healthy, so smoothness can be judged over a longer span.
5. Stop the motors after every run.

## What The Latest Log Showed

The latest adaptive one-turn log confirmed that the encoder count path works,
but the motion is still bursty:

- the target extended from `1010` to `2020` and then `3030`
- the run timed out before finishing the 3-rev target
- `raw_vx` appeared in short bursts instead of a continuous ramp
- the wheel advanced, but velocity repeatedly fell back toward zero

That means the next task is motion smoothness, not more count chasing.
The ESP32 controller now keeps the sustain floor active through the first part
of a fresh move so the wheel does not fall back into deadband at bridge open.

## Current State

- Robot: differential drive, ESP32-S3 drive stack.
- Primary tuning path: ESP32 bench firmware in `test/test_pid_bench`.
- Bridge test path: same Python runner with `--profile bridge`.
- Logging path: direct telnet to `esp32-mybot.local:23` from the dev machine.
- Wheel diameter: 68 mm.
- Wheel radius: 0.034 m.
- Encoder CPR: 1010 counts/rev.
- The ESP32 bench has direct `t`, `p`, `r`, and `s` commands for PID and power
  runs.
- The bench auto-runs on boot, so manual input is optional. `t` and `p` are
  still available for replays, but the default flow is hands-off.

## What To Use

Use the ESP32 bench firmware directly. Open telnet and trigger the run:

```bash
nc esp32-mybot.local 23
```

The default flow is automatic:

- PID bench starts after boot
- power sweep follows after the PID segment
- motors stop at the end

You can still send:

- `t` for the PID bench run
- `p` for the power sweep
- `r` to reset encoders
- `s` to stop motors

Capture the output on the dev machine and graph the `[bench]` lines.

## Required Checks Before Running

1. Make sure the robot is on blocks or in a safe test area.
2. Confirm the bench firmware is flashed to the ESP32.
3. Confirm the encoder stream is reachable at `esp32-mybot.local:23`.
4. Use the dev machine, not the Pi, to capture the log.

## What To Log

Use the bench log output and graph these fields:

- `cnt`
- `tgt`
- `act`
- `filt`
- `pwm`
- `bat`

The key question is whether velocity ramps up and down smoothly while the wheel
is actually moving, not just whether counts eventually reach the target.

For the bridge profile, the first success criterion is simpler: while the system
is held at zero, the ESP32 must log at least one received command. That proves
the Pi-to-ESP32 path is alive before motion begins.
The reported `bridge_cmd_max_gap_s` is measured after the first nonzero command
so it reflects the active bridge stream, not the intentional startup zero hold.

When analyzing the log, watch for:

- how many separate nonzero velocity bursts appear
- whether `act` stays above a small floor after startup
- whether count growth is continuous, not just occasional jumps
- whether the wheel can hold one full rotation without dropping back to zero

## What Counts As Success

- The wheel reaches the count target without pulsing into stop-and-go motion.
- Velocity rises smoothly from zero, stays active through the move, and comes
  down cleanly when the command ends.
- The run can extend from 1 to 3 revolutions without stalling or snapping back
  into the deadband.
- The bridge profile logs a received command at zero before the first motion step.

## What To Fix If It Still Pulses

If the wheel still moves in bursts:

1. Inspect the velocity traces first.
2. Adjust motor sustain behavior before changing PID gains again.
3. Do not move on to longer rotation tests until the velocity graph looks
   continuous.

Treat bursty velocity as the blocker. Counts are already working well enough to
measure the problem; they are not the problem anymore.

## One-Line Summary For Claude Code

> Keep the robot motion test focused on wheel velocity smoothness, use the
> adaptive rotation runner to extend from 1 to 3 revolutions, and always stop
> the motors after each run. Treat bursty velocity as the blocker, not counts.
