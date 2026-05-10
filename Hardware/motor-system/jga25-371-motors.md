# JGA25-371 DC Gear Motor with Encoder

![JGA25-371 Motor](../DC12V%20Encoder%20Gear%20Motor.png)

**Role in MyBot:** Left and right drive wheels. Quadrature encoder feedback enables closed-loop PID speed control via `ros_arduino_bridge` / `ros2_control`.

---

## Specs

| Parameter | Value |
|---|---|
| Voltage | 12V DC |
| No-load speed | 130 RPM (at 12V) |
| Gear ratio | **45:1** (Amazon listing says 34:1 — inaccurate) |
| Encoder type | Quadrature (A + B phases) |
| Encoder PPR | 11 pulses per revolution (motor shaft) |
| Encoder voltage | 3.3V – 5V |
| Shaft diameter | 6mm D-shaft |
| Gearbox | Metal |
| Mounting | M3 screws, standard JGA25 pattern |

---

## Encoder resolution calculation

```
Counts per wheel revolution (2× quadrature, both edges):
  = encoder_PPR × 2 × gear_ratio
  = 11 × 2 × 45
  = 990 theoretical

Empirically validated: 1010
(3 wall-guided runs: 1006 / 1016 / 1012, avg 1011, rounded to 1010)
```

**ROS config:** `enc_counts_per_rev: 1010` in `ros2_control.xacro`

---

## Wire colors

| Color | Signal |
|---|---|
| Red | Motor power + |
| White | Motor power − |
| Blue | Encoder VCC (3.3–5V) |
| Black | Encoder GND |
| Yellow | Encoder channel A |
| Green | Encoder channel B |

---

## Encoder wiring — Arduino Nano

| Motor wire | Arduino pin | Note |
|---|---|---|
| Left Yellow (A) | D2 | INT0 — hardware interrupt |
| Left Green (B) | D4 | |
| Right Yellow (A) | D3 | INT1 — hardware interrupt |
| Right Green (B) | D12 | |
| Blue (both) | 5V or 3.3V | encoder VCC |
| Black (both) | GND | |

## Encoder wiring — ESP32-S3

| Motor wire | ESP32 GPIO | Note |
|---|---|---|
| Left Yellow (A) | 36 | Input only, interrupt capable |
| Left Green (B) | 39 | Input only |
| Right Yellow (A) | 34 | Input only, interrupt capable |
| Right Green (B) | 35 | Input only |
| Blue (both) | 3V3 | encoder VCC |
| Black (both) | GND | |

---

## ISR direction logic

Both wheels count **positive** for forward rotation (validated — no inversion needed).

```cpp
// Left encoder ISR (validated fix #7)
if (A == B) enc_l++;  // forward
else        enc_l--;

// Right encoder ISR (validated fix #7 — was inverted before fix)
if (A != B) enc_r++;  // forward
else        enc_r--;
```

---

## Motor output wiring

| Motor terminal | Wire | TB6612 pin |
|---|---|---|
| Left + | Red | Motor B output + |
| Left − | White | Motor B output − |
| Right + | Red | Motor A output + |
| Right − | White | Motor A output − |

If a motor runs reversed after installation: **swap its Red/White output wires at the TB6612 terminals** — do not change firmware.

---

## Wheel geometry

| Parameter | Value |
|---|---|
| Wheel diameter | 68mm (measured; datasheet 65mm) |
| Wheel radius | **0.034m** |
| Wheel separation (center-to-center) | **0.179m** |

---

## Tuning formula

If odometry is inaccurate after swapping motors or wheels:

```
new_enc_counts = old_enc_counts × (actual_distance / reported_distance)
```

---

## Purchase reference

- Amazon listing: B07X7M1LLQ (DC12V 130RPM JGA25-371)
- Note: Amazon listing states 34:1 gear ratio — **actual ratio is 45:1**
