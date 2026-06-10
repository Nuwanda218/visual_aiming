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

## 3. Read The Report

Key fields:

- `检测命中率`: percentage of frames with at least one detection.
- `目标丢失率`: percentage of frames where prediction state is `lost`.
- `目标切换`: number of selected target switches.
- `检测延迟`: detector latency percentiles.
- `显示 FPS`: measured debug window FPS.
- `帧处理耗时`: per-frame UI loop work time.
- `等待时间`: OpenCV wait time. If p95 is `1ms`, playback is not waitKey-limited.
- `主要瓶颈`: dominant pipeline stage from latency breakdown.
- `结论`: machine-readable hints such as `wait_not_bottleneck` and `detector_bottleneck`.

## 4. Current Baseline Interpretation

Recent manual tests showed:

- `wait_ms` p95 is near `1ms`, so video-test playback is no longer artificially throttled by `waitKey`.
- The dominant bottleneck is `detect`.
- Selection, aim, prediction, and control stages are near-zero compared with detector latency.
- Algorithm changes should wait until diagnostics show stable capture, detection, and playback behavior.

## 5. Before Algorithm Work

Before changing target selection or target-lost handling, collect at least one fresh video-test run and keep these fields in the report:

- detection rate
- target lost rate
- target switches
- detector p50/p95/p99
- display FPS p50/avg
- frame work p50/p95
- insight codes
