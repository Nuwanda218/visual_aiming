# Runtime Convergence

## Route Table

| Command | Runtime path | Pipeline | Mouse/control path | Status |
| --- | --- | --- | --- | --- |
| `python main.py` | `visual_aiming.app.realtime.run_realtime()` | `ModularPipeline` | Configured output backend | Default realtime path |
| `python main.py --video-test` | `visual_aiming.app.video_test.run_video_test()` | Modular video path | Modular control/output diagnostics | Active debug path |
| `python main.py --modular --video <file>` | `visual_aiming.app.replay.run_video_file()` | `ModularPipeline` | Configured output backend | Active replay path |
| `python main.py --modular` | `visual_aiming.app.realtime.run_realtime()` | `ModularPipeline` | Configured output backend | Explicit realtime path |

## Problem

The default realtime entry now uses the same modular runtime shape as video replay and video test. The old realtime path has been removed, so runtime changes now have one behavioral surface.

## Convergence Rule

Realtime, replay, and video-test code should share `RuntimeRunner` and `ModularPipeline`. Differences belong at the input source, output backend, and debug observer boundary.

## Migration Order

1. Route decisions are explicit and testable.
2. Realtime, replay, and video-test paths use the unified runner contract.
3. Default realtime uses `run_realtime(config)`.
4. Keep the old realtime path deleted after verification.
5. Clean generated artifacts, obsolete scripts, stale docs, and old tests after the single runtime is enforced.

## Deferred

Mouse angular control is intentionally deferred to `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.
