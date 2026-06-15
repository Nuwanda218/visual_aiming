# Minimum Runtime Refactor Design

## Goal

Build a minimum runnable refactor of the current visual-assisted aiming project.
After the refactor, `python main.py` must still load the YOLO model, capture the ROI, detect targets, react to the current hotkeys, and drive relative mouse movement.

This stage keeps the current three-layer shape:

- `vision`: frame capture, YOLO inference, target selection.
- `core`: runtime orchestration, state, scheduling, target calculation, control target generation.
- `actions`: user input, mouse output, debug window, configuration UI.

The refactor is also a preparation step for the future plugin stage. It should make model input and output control boundaries explicit without introducing a full plugin loader yet.

## Success Criteria

- `python main.py` remains the stable startup command.
- The YOLO model loads through the existing config path.
- CUDA is preferred for inference when available; CPU fallback is explicit and visible in logs.
- ROI capture continues to work in threaded and synchronous modes.
- Target detection and target selection continue to return ROI-relative target data.
- Existing hotkey behavior remains intact.
- Mouse movement remains real relative mouse output, not a stub.
- Visual parameter tuning remains available through the Tkinter configuration window.
- Vision update frequency and mouse control frequency are independently tunable.

## Architecture

The runtime should be split around data flow, not around algorithms.

```text
vision loop
  -> latest VisionFrame / DetectionState
  -> core pipeline state
  -> low-frequency ControlTarget sampling
  -> actions output
```

`vision` can run as fast as the configured capture and YOLO inference settings allow. `actions` should not move the mouse once per detection frame. Instead, the mouse controller should sample the latest target state at its own control frequency and apply smoothing, speed limits, acceleration limits, and arrival behavior.

This preserves high-frequency perception while making control output visually smooth.

## Module Design

### `vision`

`vision` keeps the current concrete implementation:

- `screen_capture.py`: synchronous fixed ROI capture.
- `capture_worker.py`: background capture thread and latest-frame cache.
- `detection.py`: YOLO model loading, CUDA/CPU device resolution, inference, target scoring, target continuity.

The main design change is that detection output should be treated as a standard runtime value. The existing `DetectedTarget` can remain, but `core` should consume it through explicit schemas rather than depending on detector internals.

### `core`

`core` becomes the framework layer.

Planned responsibilities:

- `schemas.py`: shared runtime data structures such as `VisionFrame`, `DetectionState`, `AimPoint`, and `ControlTarget`.
- `runtime_state.py`: mutable runtime state such as active/firing state, latest capture sequence, latest aim point, lost-target counters, and timestamps.
- `runtime_services.py`: construction and cleanup of detector, capture, wakeup listener, mouse controller, debug visualizer, and config window.
- `pipeline.py`: transform latest detection data into a control target using target tracking, prediction, aim point calculation, and current config.
- `runtime.py`: startup, loop timing, service lifecycle, error handling, and shutdown only.

`runtime.py` should become small enough that a reader can understand the program lifecycle without reading YOLO selection or mouse control internals.

### `actions`

`actions` remains concrete device and UI integration:

- `input_listener.py`: current hotkeys and mouse-button state.
- `mouse_control.py`: real relative mouse movement and low-frequency servo loop.
- `debug_visualizer.py`: OpenCV debug display.
- `config_window.py`: runtime parameter tuning UI.

The mouse controller should continue to own output smoothing. The pipeline gives it a target; the controller decides how to move toward that target at the configured control rate.

## Frequency Model

Vision and control frequency must be separated.

Recommended minimum behavior:

- Capture thread uses `capture_fps`.
- Detection scheduling uses `detect_fps`, `firing_detect_fps`, and idle detection settings.
- Mouse output uses `servo_loop_hz` or a clearly named control-loop setting.
- The control loop samples the latest available target state and should tolerate stale or missing detections.

This lets the program capture continuous visual changes while producing smoother lower-frequency mouse movement.

## CUDA/GPU Behavior

YOLO inference should keep the existing `yolo_device`, `yolo_half`, and `yolo_imgsz` settings.

Runtime behavior:

- `yolo_device="auto"` prefers CUDA when `torch.cuda.is_available()` is true.
- `yolo_device="cuda"` requests CUDA and falls back to CPU with a clear warning if CUDA is unavailable.
- Half precision is enabled only when the runtime device supports it.
- Logs should show the requested device, actual device, half precision state, and model path.

The refactor should not hide GPU selection inside the main loop. Device resolution belongs in `TargetDetector`.

## Configuration UI

The configuration window remains part of the MVP.

Use focused default visibility with advanced grouping:

- Core performance: capture FPS, detect FPS, firing detect FPS, idle detect FPS, control loop Hz.
- Model/GPU: device, half precision, image size, confidence threshold, IoU threshold.
- Control smoothing: output gain, step limit, max speed, max acceleration, arrival radius, near brake.
- Target behavior: target preference, stickiness, history radius, switch margin.
- Advanced groups keep existing low-level parameters available without dominating normal tuning.

Settings should continue to write back to `config.json` as they do today.

## Testing Strategy

Most hardware behavior is difficult to test directly, so the first test layer should focus on pure orchestration pieces:

- Pipeline returns no control target when inactive or when no fresh detection exists.
- Pipeline returns a control target when active and detection exists.
- Frequency gating keeps detection scheduling independent from mouse control scheduling.
- Runtime state updates latest detection and aim timestamps without requiring YOLO or real mouse output.

Manual verification remains required for the full chain:

```text
python main.py
```

Expected manual result:

- Model loads.
- ROI capture starts.
- Detector logs selected CUDA/CPU runtime.
- Hotkeys activate the loop.
- Mouse movement follows detected targets.
- Configuration UI can adjust key performance and smoothing parameters while running.

## Future Plugin Path

After this design is working, the future plugin stage can be introduced with small surface changes:

```text
VisionPlugin.process(frame) -> DetectionState
CorePipeline.update(DetectionState) -> ControlTarget
OutputPlugin.apply(ControlTarget)
```

The MVP should not implement plugin discovery, dynamic loading, plugin metadata, or third-party packaging. It only creates the stable boundaries needed for those features in the future plugin stage.

## Non-Goals

- No full plugin loader in this stage.
- No rewrite of YOLO target selection unless required by tests or runtime breakage.
- No replacement of real mouse output with a mock in production.
- No UI redesign beyond grouping and exposing the required tuning parameters.
- No change to the root startup command.
