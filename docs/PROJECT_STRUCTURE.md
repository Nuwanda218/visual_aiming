# Project Structure

```text
.
├── main.py
├── config.json
├── requirements.txt
├── src/
│   └── visual_aiming/
│       ├── app.py
│       ├── config.py
│       ├── core/
│       │   ├── runtime.py
│       │   ├── aim_calculator.py
│       │   ├── target_tracker.py
│       │   ├── detect_scheduler.py
│       │   └── throttle.py
│       ├── vision/
│       │   ├── screen_capture.py
│       │   ├── capture_worker.py
│       │   └── detection.py
│       ├── actions/
│       │   ├── input_listener.py
│       │   ├── mouse_control.py
│       │   ├── debug_visualizer.py
│       │   ├── config_window.py
│       │   └── visual_servo.py
│       └── common/
│           ├── timing.py
│           ├── resource_path.py
│           └── utils.py
├── models/
│   └── best.pt
├── scripts/
│   └── build_exe.py
├── packaging/
│   └── aim_assist.spec
└── docs/
    └── PROJECT_STRUCTURE.md
```

## Entry Points

- `main.py`: stable compatibility launcher. Use this for VSCode and normal local runs.
- `src/visual_aiming/app.py`: compatibility wrapper that imports `visual_aiming.core.runtime.main`.
- `src/visual_aiming/core/runtime.py`: actual application loop.
- `scripts/build_exe.py`: PyInstaller build helper.

## Runtime Layers

- Vision module: `vision/screen_capture.py`, `vision/capture_worker.py`, `vision/detection.py`
- Core interface module: `core/runtime.py`, `core/detect_scheduler.py`, `core/throttle.py`, `core/aim_calculator.py`, `core/target_tracker.py`
- Action module: `actions/input_listener.py`, `actions/mouse_control.py`, `actions/debug_visualizer.py`, `actions/config_window.py`
- Common helpers: `common/timing.py`, `common/resource_path.py`, `common/utils.py`
