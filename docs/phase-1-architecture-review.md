# Phase 1 Architecture Review

Date: 2026-06-10

## Scope

Phase 1 focused on making the Python modular runtime easier to debug, safer to evolve, and clearer at module boundaries. It did not change the core aiming algorithm priorities; target switching, target lost handling, and performance rewrites remain later work.

## Completed Work

- Added a JSONL diagnostics workflow for `main.py --video-test` and `main.py --analyze-log`.
- Split video-test helpers into focused app modules for timing, overlay text, diagnostics path formatting, and log analysis.
- Ignored local runtime logs through `.gitignore`.
- Removed the duplicate `src/visual_aiming/app.py` module after the package entrypoint became authoritative.
- Added detector and output factories under `visual_aiming.adapters`.
- Updated `visual_aiming.app.realtime` and `visual_aiming.app.video_test` to compose detectors and outputs through factories.
- Added architecture boundary tests for app, algorithm, core, port, config, and adapter layers.
- Removed the obsolete `tests/video_test.py` legacy manual script and its dedicated tests.
- Updated project structure documentation and marked the 2026-06-06 implementation plan as historical where it no longer matches the current layout.

## Current Boundary Rules

- `visual_aiming.app` may compose adapters, config, core, and app helpers, but it must not import `visual_aiming.actions` or `visual_aiming.vision`.
- `visual_aiming.app` must use output factories instead of importing concrete output implementations directly.
- `visual_aiming.algorithms` must stay independent from app, adapters, actions, and vision.
- `visual_aiming.core` must stay independent from app, adapters, ports, UI, actions, and vision.
- `visual_aiming.ports` must stay independent from runtime implementations.
- `visual_aiming.config` must stay independent from runtime layers.
- `visual_aiming.adapters` may wrap legacy `vision` during migration, but must not depend on app, algorithms, UI, or legacy actions.

These rules are enforced by `tests/test_architecture_boundaries.py`.

## Intentional Legacy Surface

- `visual_aiming.core.runtime` remains the default realtime loop when modular realtime screen activation is not explicitly selected.
- `visual_aiming.vision.detection.TargetDetector` remains wrapped by `visual_aiming.adapters.detectors.factory`.
- `visual_aiming.vision.screen_capture.ScreenCapture` remains wrapped by `visual_aiming.adapters.frame_sources.screen_capture`.
- Legacy UI and action modules still exist for compatibility and config-window coverage.

## Current Entry Points

- `main.py`: compatibility launcher.
- `main.py --video-test`: interactive modular video-test runner.
- `main.py --analyze-log <path>`: diagnostics report for modular JSONL logs.
- `main.py --modular --video <path>`: safe replay path.
- `main.py --modular --output win_mouse --real-mouse`: explicit opt-in for real mouse output.

## Phase 2 Entry Criteria

Before changing target-selection or target-lost algorithms, collect a fresh video-test JSONL run and analyze it with `main.py --analyze-log`. Use the report to decide whether the next bottleneck is detector quality, target stability, prediction hold behavior, or control tuning.

## Phase 2 Recommended Direction

1. Strengthen debug report interpretation with reason counts and target continuity metrics.
2. Add replay fixtures from real video-test JSONL output so algorithm changes can be evaluated repeatably.
3. Improve target selection hysteresis and short-term target retention only after those fixtures exist.
4. Keep performance rewrites and language rewrites out of scope until the Python behavior is stable.

## Final Verification

The following verification passed at phase close:

```text
.venv\Scripts\python.exe -m compileall -q src tests main.py
.venv\Scripts\python.exe -m unittest discover tests -v
Ran 65 tests ... OK

.venv\Scripts\python.exe -m unittest tests.test_architecture_boundaries -v
Ran 8 tests ... OK
```

The YOLO CPU fallback message during tests is expected on machines without CUDA and is covered by detector device tests.
