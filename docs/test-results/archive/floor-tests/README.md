# Floor Test Results

Raw ESP32 Telnet captures and derived artifacts for floor motion tests.

Primary tuning summary:

- `../../floor-test-tuning-log.md`

Naming:

- `floor_baseline_N_<move>.csv`: valid count-based baseline CSV for baseline pass `N`
- `archive-short-protocol/`: old 1.5 second timed floor tests, kept for tuning history only
- `invalid-cmd-vel-route/`: invalid count-based attempts where `/cmd_vel` did not drive ESP32 targets
- `debug-command-path-2026-05-17/`: partial troubleshooting runs collected while isolating command delivery and stop behavior
- Additional parsed summaries can be added as `floor_test_N_summary.md` if needed

Current protocol:

- Compare the latest three completed tests when deciding tuning changes.
- Record the exact firmware constants or launch changes that caused each result.
- Run `--profile floor_baseline` to execute all four counted moves in one process (fwd 1m, bwd 1m, left 360°, right 360°). Do NOT use four separate `--profile one_turn` invocations — DDS participant churn after each exit causes command delivery to fail.
- CSV logs contain active-motion samples only unless a specific idle/rearm issue is being investigated.
- Every runner exit publishes zero Twist to `/cmd_vel_joy` and `/cmd_vel`.
- Stop `oled-display.service` on the Pi before each test batch; restart it afterward.
- All four steps must reach their count target (not time out) before treating data as valid baseline.
