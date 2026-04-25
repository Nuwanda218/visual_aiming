# Project Structure

```text
.
├── main.py
├── src/
│   └── visual_aiming/
│       ├── app.py
│       ├── config.py
│       ├── detection.py
│       ├── capture_worker.py
│       ├── detect_scheduler.py
│       ├── target_tracker.py
│       ├── timing.py
│       ├── aim_calculator.py
│       ├── visual_servo.py
│       ├── mouse_control.py
│       ├── recoil.py
│       ├── config_window.py
│       ├── screen_capture.py
│       ├── input_listener.py
│       ├── throttle.py
│       ├── debug_visualizer.py
│       ├── resource_path.py
│       └── utils.py
├── models/
│   └── best.pt
├── tools/
│   └── color_threshold_tuner.py
├── scripts/
│   └── build_exe.py
├── packaging/
│   └── aim_assist.spec
├── config.json
├── requirements.txt
└── docs/
    └── PROJECT_STRUCTURE.md
```

## Entry Points

- `main.py`: stable compatibility launcher. Use this for VSCode and normal local runs.
- `src/visual_aiming/app.py`: actual application loop.
- `scripts/build_exe.py`: PyInstaller build helper.
- `tools/color_threshold_tuner.py`: legacy color-threshold tuning utility retained for reference.

## Runtime Layers

- Input state: `input_listener.py`
- Capture: `screen_capture.py`
- Capture worker: `capture_worker.py`
- Detection scheduler: `detect_scheduler.py`
- Target prediction: `target_tracker.py`
- Timing helpers: `timing.py`
- Detection: `detection.py`
- Aim point calculation: `aim_calculator.py`
- Control: `visual_servo.py`, `mouse_control.py`
- Compensation: `recoil.py`
- Runtime config UI: `config_window.py`
- Debug display: `debug_visualizer.py`
