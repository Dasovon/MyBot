# Test Results

All PID tuning test logs live here.

## Folder structure

```
test-results/
├── floor_baseline/   ← valid floor_baseline runs (fwd + bwd + left/right 360°)
└── archive/          ← old, debug, invalid, or pre-IMU runs
```

## Naming convention

`floor_baseline/YYYY-MM-DD_run_NNN.csv`

Example: `floor_baseline/2026-05-17_run_001.csv`

## Validity rule

A floor_baseline run is valid only when all four steps reach their count target
without timing out. Timed-out runs go to `archive/`.

## Run command

```bash
ros2 run articubot_one pid_sequence_test.py \
  --profile floor_baseline \
  --turn-linear 0.35 \
  --floor-spin-rate 1.5 \
  --floor-distance 0.25 \
  --stop-hold 2.0 \
  --warmup 0.5 \
  --output ~/dev_ws/src/articubot_one/docs/test-results/floor_baseline/YYYY-MM-DD_run_NNN.csv
```

## CSV columns

| Column | Description |
|---|---|
| `enc_derived_lin_mps` | Encoder-derived linear velocity (m/s) — ground truth speed |
| `enc_derived_ang_rps` | Encoder-derived angular velocity (rad/s) |
| `imu_gyro_z` | IMU angular rate (rad/s) — compare to enc_derived_ang_rps |
| `imu_accel_x` | Raw IMU forward acceleration |
| `imu_accel_x_filt` | EMA-filtered (α=0.1) forward acceleration — vibration suppressed |
| `imu_enc_ang_err_avg` | Summary: mean \|imu_gyro_z − enc_derived_ang_rps\| during active phases |
