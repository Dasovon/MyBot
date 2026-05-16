# Claude Code CLI PID Test Instructions

This file is now a short pointer to the live tuning guide.

Use [docs/pid_tuning_guide.md](./pid_tuning_guide.md), especially:
- `Step 0 — Use The ESP32 Bench First`
- `Step 2 — Baseline Test`
- `Flash + Test Cycle`
- `What To Log`
- `Current one-turn result`

The active workflow is:
- ESP32 bench first
- bridge profile second
- stop the motors after every run
- treat bursty velocity as the blocker, not counts
