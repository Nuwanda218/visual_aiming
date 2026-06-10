# Project Structure

```text
.
├── main.py
├── config.json
├── requirements.txt
├── src/
│   └── visual_aiming/
│       ├── app/
│       │   ├── log_analyzer.py
│       │   ├── replay.py
│       │   ├── realtime.py
│       │   ├── timing.py
│       │   ├── video_overlay.py
│       │   ├── video_run_diagnostics.py
│       │   └── video_test.py
│       ├── adapters/
│       │   ├── detectors/
│       │   ├── frame_sources/
│       │   └── outputs/
│       ├── algorithms/
│       │   ├── aim_point.py
│       │   ├── control.py
│       │   ├── prediction.py
│       │   └── target_selection.py
│       ├── config/
│       ├── core/
│       │   ├── metrics.py
│       │   ├── pipeline.py
│       │   ├── runtime.py
│       │   ├── aim_calculator.py
│       │   ├── target_tracker.py
│       │   ├── detect_scheduler.py
│       │   ├── schemas.py
│       │   └── throttle.py
│       ├── ports/
│       │   ├── detector.py
│       │   ├── diagnostics.py
│       │   ├── frame_source.py
│       │   └── output.py
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
- `src/visual_aiming/app/`: modular app package for replay, realtime composition, video-test, and diagnostics analysis.
- `src/visual_aiming/adapters/`: concrete integrations for detector, frame sources, and output backends.
- `src/visual_aiming/algorithms/`: modular target selection, aim, prediction, and control algorithms.
- `src/visual_aiming/ports/`: Protocol boundaries between pipeline and adapters.
- `src/visual_aiming/core/runtime.py`: actual application loop.
- `scripts/build_exe.py`: PyInstaller build helper.

## Runtime Layers

- Vision module: `vision/screen_capture.py`, `vision/capture_worker.py`, `vision/detection.py`
- Core interface module: `core/runtime.py`, `core/detect_scheduler.py`, `core/throttle.py`, `core/aim_calculator.py`, `core/target_tracker.py`
- Action module: `actions/input_listener.py`, `actions/mouse_control.py`, `actions/debug_visualizer.py`, `actions/config_window.py`
- Common helpers: `common/timing.py`, `common/resource_path.py`, `common/utils.py`

## Modular Algorithm Runtime

The first-version modular runtime lives beside the legacy realtime runtime. It is organized around replaceable ports:

```text
FrameSource -> Detector -> TargetSelector -> AimStrategy -> Predictor -> Controller -> OutputBackend
```

Realtime and replay modes are expected to share `visual_aiming.core.pipeline.ModularPipeline`. The default modular output backend is `NullOutput`, so modular runs do not move the mouse unless `--output win_mouse --real-mouse` is passed.

Key modules:

- `visual_aiming.core.schemas`: normalized frame, detection, aim, prediction, command, and tick-result dataclasses.
- `visual_aiming.ports`: Protocol boundaries for frame sources, detectors, outputs, and diagnostics.
- `visual_aiming.algorithms`: pure target selection, aim point, prediction, and control logic.
- `visual_aiming.adapters`: wrappers for screen/video input, ultralytics YOLO, and output backends.
- `visual_aiming.app.replay`: safe replay runner.
- `visual_aiming.app.realtime`: composition helpers for realtime mode.
- `visual_aiming.app.video_test`: interactive video-test runner used by `main.py --video-test`.
