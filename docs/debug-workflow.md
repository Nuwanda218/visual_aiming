# Debug Workflow

This project uses `--video-test` to produce repeatable JSONL diagnostics and `--analyze-log` to summarize the run.

## 1. Run Video Test

Use the project virtual environment:

```powershell
.venv\Scripts\python.exe main.py --video-test
```

The test opens a file picker, runs the modular pipeline on the selected video, and writes diagnostics under `logs/`.

The generated files are local artifacts and are ignored by Git:

```text
logs/video_test_<video>_<timestamp>.jsonl
logs/video_test_<video>_<timestamp>.summary.json
```

## 2. Analyze Latest Log

Analyze the newest JSONL file:

```powershell
$latest = Get-ChildItem logs -Filter "video_test_*.jsonl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
.venv\Scripts\python.exe main.py --analyze-log $latest.FullName
```

Analyze a specific run:

```powershell
.venv\Scripts\python.exe main.py --analyze-log logs\video_test_example.jsonl
```

## 3. Evaluate a Diagnostics Run

```powershell
.venv\Scripts\python.exe scripts\evaluate_diagnostics.py logs\run.jsonl --min-visible-detection-rate 85 --max-empty-false-positive-rate 5 --max-target-switches 10
```

Use this only for annotated logs. Unannotated logs still show output rate and continuity, but cannot prove detection accuracy.

## 4. Read The Report

Key fields:

- `检测输出率`: percentage of frames with at least one detection. This is not detection accuracy because unannotated videos may contain empty frames.
- `可见目标检出率`: when annotations exist, percentage of target-visible frames with at least one detection.
- `空场景误检率`: when annotations exist, percentage of target-empty frames that still produced detections.
- `目标丢失率`: percentage of frames where prediction state is `lost`.
- `目标切换`: number of selected target switches.
- `非零指令率`: percentage of frames where output command has non-zero movement.
- `指令幅度`: movement command magnitude distribution across all frames.
- `非零指令幅度`: movement command magnitude distribution after zero commands are removed.
- `最长追踪段`: longest consecutive run of `tracking` prediction state.
- `最长丢失段`: longest consecutive run of `lost` prediction state.
- `最长无检测段`: longest consecutive run of frames without detections.
- `异常段`: longest frame ranges for no detection, lost prediction, and zero movement command. Use the `seq` range to inspect the matching video section.
- `预测状态`: counts for prediction states such as `tracking`, `held`, `lost`, and `reset`.
- `选择原因`: counts for target-selection reasons such as `selected` and `no_detections`.
- `命令原因`: counts for command reasons such as `tracking`, `deadzone`, and `subpixel`.
- `目标中心跳变`: selected target center movement between adjacent selected frames.
- `最大目标跳变`: largest adjacent selected-target center jump and its source sequence range.
- `检测延迟`: detector latency percentiles.
- `显示 FPS`: measured debug window FPS.
- `帧处理耗时`: per-frame UI loop work time.
- `等待时间`: OpenCV wait time. If p95 is `1ms`, playback is not waitKey-limited.
- `主要瓶颈`: dominant pipeline stage from latency breakdown.
- `结论`: machine-readable hints such as `wait_not_bottleneck` and `detector_bottleneck`.

## 5. Current Baseline Interpretation

Recent manual tests showed:

- `wait_ms` p95 is near `1ms`, so video-test playback is no longer artificially throttled by `waitKey`.
- The dominant bottleneck is `detect`.
- Selection, aim, prediction, and control stages are near-zero compared with detector latency.
- Algorithm changes should wait until diagnostics show stable capture, detection, and playback behavior.

## 6. Before Algorithm Work

Before changing target selection or target-lost handling, collect at least one fresh video-test run and keep these fields in the report:

- detection output rate
- annotation-based detection quality, if the log contains `target_visible`, `enemy_visible`, `annotations.target_visible`, or `annotations.enemy_visible`
- target lost rate
- target switches
- command magnitude p50/p95/max
- problem segment sequence ranges
- largest target jump sequence range
- detector p50/p95/p99
- display FPS p50/avg
- frame work p50/p95
- insight codes

## 7. Mouse Output Probe

Before judging algorithm control quality in-game, compare the two Windows sender methods on the desktop:

```powershell
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend set_cursor --dx 80 --dy 0 --count 2
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --dx 80 --dy 0 --count 2
```

Use `set_cursor` for the conservative `GetCursorPos + SetCursorPos` path. Use `sendinput` for Win32 relative mouse movement. If both move the desktop cursor but only one works in-game, the difference is likely in how the game reads mouse input.

The probe requests administrator privileges by default. Add `--no-elevate` only when you explicitly want to stay in the current non-admin shell. The probe prints each send step before calling the sender and prints `done` at the end. If `sendinput` returns but the observed desktop delta differs from the requested delta, Windows pointer speed/acceleration may be scaling relative input. Use larger deltas such as `--dx 80` before judging that movement failed.

For live runtime checks, enable `输出诊断日志` in the config window. The runtime prints `mouse_diagnostics` lines with:

- `sender`: active mouse sender, such as `send_relative_move_sendinput`.
- `sent`: number of non-zero moves sent by the controller.
- `zero`: number of controller ticks that produced zero movement.
- `last`: last sent `(dx, dy)`.
- `blocked`: reasons such as `inactive`, `missing_crosshair`, or `reset`.

If `sent` keeps increasing but in-game aim does not move, focus on game input mode and sender method. If `sent` stays flat while detections exist, focus on activation state, crosshair availability, deadzone, or controller output.

### Recommended tuning order

1. Adjust `置信度阈值` until obvious false positives are controlled.
2. Adjust `切换迟滞` when targets switch too often.
3. Adjust `短时保持` when short detection gaps produce unstable commands.
4. Adjust `死区` only after target selection and prediction are stable.
