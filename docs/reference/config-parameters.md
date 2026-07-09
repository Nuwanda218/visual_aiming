# V2 Configuration Parameters Reference

All parameters live in `config.v2.json`, organized by architectural layer.

## Quick tuning guide

| Problem | Fix |
|---------|-----|
| Overshooting target (crosshair goes past) | Increase `control.near_radius`, decrease `control.near_speed_scale` |
| Can't keep up with moving target | Increase `control.speed` |
| Aim shakes when crosshair on target | Increase `control.deadzone`, increase `smoothing.jitter_radius` |
| Losing target lock too easily | Increase `tracker.match_distance_ratio`, increase `tracker.lost_frame_grace` |
| Target lock jumps between enemies | Decrease `tracker.match_distance_ratio` |
| Too many false detections | Increase `perception.confidence` |
| Mouse feels laggy / unresponsive | Increase `control.acceleration`, increase `runtime.detect_fps` |
| Aim point too high on head box | Increase `targeting.head_bias` |
| Aim point too high on person box | Increase `targeting.body_bias` |

---

## capture — Image capture

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `image_width` | int | 410 | 100-1000 | ROI crop width in pixels. Larger = wider coverage but more GPU work. |
| `image_height` | int | 315 | 100-1000 | ROI crop height. Keep 4:3 or 16:9 aspect ratio. |
| `crosshair_offset_x` | int | 0 | -200..200 | Horizontal crosshair offset from ROI center. Positive = right. |
| `crosshair_offset_y` | int | 0 | -200..200 | Vertical crosshair offset from ROI center. Negative = up. |

Use `--tune capture` to visually adjust these with a real-time preview.

---

## perception — YOLO detector

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `model_path` | str | `models/best.pt` | - | Path to YOLO model. bigger models (yolov8s.pt) = better accuracy, slower. |
| `confidence` | float | 0.5 | 0.05-0.95 | Minimum confidence for a detection. Raise to filter out false positives. |
| `iou` | float | 0.45 | 0.1-0.9 | NMS IOU threshold for merging overlapping boxes. Lower = merge more aggressively. |
| `device` | str | `auto` | - | `auto` = prefer CUDA, `cpu`, `cuda:0`. |

---

## actuation — targeting (aim point bias)

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `head_label` | str | `head` | - | YOLO class label for head detection. Must match model's class names. |
| `person_label` | str | `person` | - | YOLO class label for person detection. |
| `head_bias` | float | 0.35 | 0-1.0 | Vertical aim point on head box: 0=top edge, 0.5=center. Raise if shooting too high. |
| `body_bias` | float | 0.25 | 0-1.0 | Vertical aim point on person box: 0=top edge. Raise if shooting too high. |

---

## actuation — tracker (target lock)

Logic: compares consecutive detection boxes by center distance and size ratio.
Once locked on a target, it stays locked until the target disappears. It does NOT actively switch to a closer target.

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `match_distance_ratio` | float | 0.75 | 0.3-2.0 | Max allowed center move distance / box diagonal between frames to still be same target. Higher = looser matching. Increase if losing lock when target moves fast. |
| `min_match_distance` | float | 18.0 | 1-100 | If center moves less than this in pixels, always consider same target regardless of ratio. |
| `size_ratio_min` | float | 0.55 | 0.2-1.0 | Min new/old box area ratio. Below this = not the same target. |
| `size_ratio_max` | float | 1.8 | 1.0-3.0 | Max new/old box area ratio. Above this = not the same target. |
| `lost_frame_grace` | int | 2 | 0-10 | Keep the lock for N frames after target disappears from detection. Increase if target frequently lost and reacquired. |

---

## actuation — smoothing (aim point filter)

Uses Exponential Moving Average (EMA) to smooth aim point across frames, reducing jitter from detection box size variations.

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `enabled` | bool | true | - | Enable/disable aim point smoothing. |
| `alpha` | float | 0.55 | 0.05-0.95 | EMA coefficient: 0 = fully smooth/unresponsive, 1 = raw/no smoothing. Decrease if aim shakes when idle. Increase if aim lags behind moving target. |
| `jitter_radius` | float | 2.0 | 0-20 | Aim point changes smaller than this are treated as jitter and suppressed. Increase if stationary target causes aim shake. |
| `stable_frames` | int | 2 | 1-10 | Consecutive frames below jitter_radius before heavy smoothing activates. |
| `hold_frames` | int | 3 | 0-20 | Continue predicting aim position for N frames after target lost. |

---

## actuation — control (mouse movement)

FPS-style velocity controller: farther error = faster movement, decelerates when close.
Output goes through FpsController -> output_scale -> SendInput.

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `speed` | float | 180.0 | 20-500 | Base movement speed. Higher = faster mouse. Increase if can't keep up with moving target. |
| `acceleration` | float | 0.45 | 0.05-0.95 | Velocity smoothing factor. 0 = slow smooth response, 1 = instant response. Lower = smoother but feels laggy. |
| `deadzone` | float | 3.0 | 0-15 | Stop all output when aim error < deadzone pixels. Increase if aim oscillates near target. |
| `near_radius` | float | 80.0 | 10-300 | Start decelerating within this distance from target. **Increase if overshooting.** |
| `near_speed_scale` | float | 0.35 | 0.01-1.0 | Speed multiplier when inside near_radius. **Decrease if overshooting (try 0.05-0.10).** |
| `output_scale` | float | 1.0 | 0.1-3.0 | Final output multiplier. Use calibration tool to match your game sensitivity. |

### How the velocity controller works

```
Error (pixels from crosshair to aim point)
    |
    --> If error < deadzone: STOP
    |
    --> Target speed = error * speed_gain (clamped to speed)
    --> If error < near_radius: target speed *= near_speed_scale
    |
    --> Smooth velocity toward target speed (acceleration factor)
    |
    --> If error < speed*3: apply deceleration brake
    |
    --> Output dx,dy (raw mouse units via SendInput)
```

### Calibrating output_scale

Run `python scripts/test_mouse_calibrate.py` to send a known dx (default 100).
Measure how many pixels your crosshair moved in-game.
`output_scale = in_game_pixels / 100`

---

## runtime — Loop control

| Param | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `detect_fps` | float | 30.0 | 5-120 | YOLO detection rate. Higher = lower reaction latency, more GPU load. 30 is a good balance. |

---

## output — Output backend

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | str | `null` | `null` = no output, `log` = record commands in memory, `mouse` = real mouse via SendInput. |

The `backend` field is set by CLI `--output` argument, not directly in config.
