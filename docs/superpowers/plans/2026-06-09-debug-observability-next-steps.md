# Debug Observability Next Steps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the next debug-observability batch: add a reusable log analyzer, remove first-frame warmup noise from video-test, and split video-test rendering/diagnostic helpers without changing aiming algorithms.

**Architecture:** Keep the app layer as composition and user interaction. Put reusable log analysis in a small app service that reads JSONL diagnostics and returns plain dictionaries for CLI/tests. Keep video-test timing and rendering helpers separate from target selection, prediction, and control code.

**Tech Stack:** Python standard library, `unittest`, existing modular diagnostics JSONL, existing OpenCV video-test app.

---

### Task 1: Add JSONL Log Analyzer CLI

**Files:**
- Create: `src/visual_aiming/app/log_analyzer.py`
- Modify: `main.py`
- Test: `tests/test_modular_apps.py`

- [ ] Write a failing test for `--analyze-log logs/run.jsonl`.
- [ ] Implement `analyze_jsonl(path)` with strict JSON parsing, counters, rates, and p50/p90/p95 latency summaries.
- [ ] Add `--analyze-log` to `main.py`.
- [ ] Print a compact text report with samples, detection rate, lost rate, display FPS, frame work, detector latency, and dominant bottleneck.
- [ ] Run `python -m unittest tests.test_modular_apps -v`.

### Task 2: Add Video-Test Model Warmup

**Files:**
- Modify: `src/visual_aiming/app/video_test.py`
- Modify: `src/visual_aiming/adapters/detectors/ultralytics_yolo.py` if a small adapter method is needed.
- Test: `tests/test_modular_adapters.py` or `tests/test_modular_apps.py`

- [ ] Write a failing test proving the detector adapter exposes or delegates warmup without requiring GUI.
- [ ] Warm up the detector once after the first frame is loaded and before active playback starts.
- [ ] Keep warmup outside JSONL frame samples so the first recorded detection latency is less polluted by model startup.
- [ ] Print one concise warmup status line in video-test startup.
- [ ] Run focused adapter/app tests.

### Task 3: Split Video-Test Rendering Helpers

**Files:**
- Create: `src/visual_aiming/app/video_overlay.py`
- Modify: `src/visual_aiming/app/video_test.py`
- Test: `tests/test_modular_apps.py`

- [ ] Move OSD text construction into a pure helper so it can be tested without OpenCV windows.
- [ ] Keep drawing calls in video-test or a small renderer helper; do not move pipeline logic.
- [ ] Add tests for OSD lines containing frame count, detection latency, pipeline latency, frame work, wait, FPS, and command reason.
- [ ] Run focused app tests.

### Task 4: Batch Verification And Commit

**Files:**
- All files touched by Tasks 1-3.

- [ ] Run `python -m compileall -q src tests`.
- [ ] Run `python -m unittest discover tests -v`.
- [ ] Remove generated `logs/video_test_*` test artifacts if any.
- [ ] Commit with a Chinese commit message.
- [ ] Push `origin main` if network is available.
