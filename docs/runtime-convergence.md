# Runtime Convergence

## Route Table

| Command | Runtime path | Pipeline | Mouse/control path | Status |
| --- | --- | --- | --- | --- |
| `python main.py` | `visual_aiming.core.runtime.main()` | `RuntimePipeline` | `MouseController` | Legacy realtime default |
| `python main.py --video-test` | `visual_aiming.app.video_test.run_video_test()` | Modular video path | Modular control/output diagnostics | Active debug path |
| `python main.py --modular --video <file>` | `visual_aiming.app.replay.run_video_file()` | `ModularPipeline` | Configured output backend | Active replay path |
| `python main.py --modular` | Falls back to `visual_aiming.core.runtime.main()` | `RuntimePipeline` | `MouseController` | Temporary fallback |

## Problem

There is no normal single-process fight between old and new runtimes. The risk is behavior drift: fixes verified in video replay may not affect live realtime, and live-only behavior may not be covered by modular tests.

## Convergence Rule

Move shared behavior into small modules first. Keep realtime behavior stable until each shared contract has tests.

## Migration Order

1. Route decisions become explicit and testable.
2. Diagnostics and control events use compatible field names.
3. Config conversion lives in one place.
4. Modular realtime composition exists behind an explicit flag.
5. Manual parity testing decides when default realtime can switch.

## Deferred

Mouse angular control is intentionally deferred to `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.
