import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.runtime_state import RuntimeState
from visual_aiming.core.pipeline import RuntimePipeline


class RuntimeStateTest(unittest.TestCase):
    def test_reset_tracking_state_clears_runtime_targets(self):
        state = RuntimeState(firing=True, last_aim_base=(10, 20), last_capture_seq=7)

        state.reset_tracking_state()

        self.assertFalse(state.firing)
        self.assertIsNone(state.last_aim_base)
        self.assertEqual(state.last_capture_seq, -1)

    def test_update_firing_reports_transitions(self):
        state = RuntimeState()

        self.assertEqual(state.update_firing(True), "started")
        self.assertTrue(state.firing)
        self.assertEqual(state.update_firing(True), "unchanged")
        self.assertEqual(state.update_firing(False), "stopped")
        self.assertFalse(state.firing)


class FakeAimCalculator:
    def __init__(self, result):
        self.result = result

    def calculate(self, target, roi_left, roi_top):
        return self.result


class RuntimePipelineTest(unittest.TestCase):
    def test_inactive_pipeline_returns_empty_control(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )

        result = pipeline.process_detection(
            active=False,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertIsNone(result.control.target)
        self.assertFalse(result.control.has_measurement)

    def test_active_fresh_detection_returns_control_target(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )

        result = pipeline.process_detection(
            active=True,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertEqual(result.control.target, (100, 100))
        self.assertTrue(result.control.has_measurement)

    def test_current_control_reuses_last_target_without_measurement(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )
        pipeline.state.last_aim_base = (120, 130)

        control = pipeline.current_control(active=True, crosshair=(50, 50))

        self.assertEqual(control.target, (120, 130))
        self.assertFalse(control.has_measurement)
        self.assertTrue(control.active)


class VideoTestRuntimeReuseTest(unittest.TestCase):
    def test_video_test_delegates_to_runtime_pipeline(self):
        source = (PROJECT_ROOT / "tests" / "video_test.py").read_text(encoding="utf-8")

        self.assertIn("RuntimePipeline", source)
        self.assertIn("AimPointCalculator", source)
        self.assertIn("runtime_core._update_detection_and_control", source)
        self.assertNotIn("self.tracker.update", source)
        self.assertNotIn("self.tracker.predict", source)

    def test_video_frame_adapter_preserves_fullscreen_canvas_and_crops_center_roi(self):
        from video_test import VideoFrameAdapter

        source = np.full((2, 4, 3), 7, dtype=np.uint8)
        source[:, 1:3] = 255
        adapter = VideoFrameAdapter(screen_size=(8, 6), roi_size=(4, 2))

        canvas = adapter.make_canvas(source)
        roi = adapter.crop_center_roi(canvas)

        self.assertEqual(canvas.shape, (6, 8, 3))
        self.assertEqual(roi.shape, (2, 4, 3))
        self.assertTrue((roi[:, 1:3] == 255).any())
        self.assertEqual(adapter.roi_offset, (2, 2))
        self.assertEqual(adapter.crosshair, (4, 3))

    def test_video_playback_clock_maps_elapsed_time_to_frame_index(self):
        from video_test import PlaybackClock

        clock = PlaybackClock(fps=25.0, total_frames=100)

        self.assertEqual(clock.frame_index(0.0), 0)
        self.assertEqual(clock.frame_index(0.039), 0)
        self.assertEqual(clock.frame_index(0.040), 1)
        self.assertEqual(clock.frame_index(4.120), 3)

    def test_video_runtime_mode_toggles_active_firing_and_absolute_validation(self):
        from video_test import VideoRuntimeMode

        mode = VideoRuntimeMode()
        self.assertFalse(mode.active)
        self.assertFalse(mode.firing)
        self.assertFalse(mode.absolute_validation)
        self.assertEqual(mode.mouse_mode_label, "servo")

        mode.toggle_active()
        self.assertTrue(mode.active)
        self.assertFalse(mode.firing)

        mode.toggle_firing()
        self.assertTrue(mode.active)
        self.assertTrue(mode.firing)

        mode.toggle_absolute_validation()
        self.assertTrue(mode.absolute_validation)
        self.assertEqual(mode.mouse_mode_label, "absolute")

        mode.toggle_active()
        self.assertFalse(mode.active)
        self.assertFalse(mode.firing)

    def test_video_diagnostics_include_pipeline_and_mouse_state(self):
        from video_test import VideoDiagnostics, VideoRuntimeMode

        diagnostics = VideoDiagnostics()
        mode = VideoRuntimeMode(active=True, firing=True, absolute_validation=True)
        lines = diagnostics.lines(
            mode=mode,
            display_fps=120.0,
            detect_fps=30.0,
            detection_latency_ms=12.5,
            target_bbox=(1, 2, 3, 4),
            aim_point=(100, 200),
            control_target=(110, 210),
            has_measurement=True,
            target_is_fresh=False,
        )

        joined = "\n".join(lines)
        self.assertIn("Status: ACTIVE+FIRING", joined)
        self.assertIn("Mouse mode: absolute", joined)
        self.assertIn("Control target: (110, 210)", joined)
        self.assertIn("Measurement: True", joined)
        self.assertIn("Fresh: False", joined)

    def test_video_run_logger_writes_jsonl_and_summary(self):
        from video_test import VideoRunLogger

        with tempfile.TemporaryDirectory() as tmp_dir:
            logger = VideoRunLogger(Path(tmp_dir), run_name="sample")
            logger.write_event({
                "t": 0.1,
                "display_fps": 120.0,
                "detect_fps": 30.0,
                "detect_latency_ms": 12.5,
                "fresh": True,
                "has_measurement": True,
                "target_error_after": 3.0,
            })
            logger.write_event({
                "t": 0.2,
                "display_fps": 100.0,
                "detect_fps": 20.0,
                "detect_latency_ms": 30.0,
                "fresh": False,
                "has_measurement": False,
                "target_error_after": 10.0,
            })
            logger.close()

            self.assertTrue(logger.jsonl_path.exists())
            records = [json.loads(line) for line in logger.jsonl_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 2)
            self.assertTrue(records[0]["fresh"])

            summary = json.loads(logger.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["samples"], 2)
            self.assertEqual(summary["fresh_ratio"], 0.5)
            self.assertEqual(summary["measurement_ratio"], 0.5)
            self.assertEqual(summary["max_detect_latency_ms"], 30.0)
            self.assertEqual(summary["avg_target_error_after"], 6.5)

    def test_video_cli_parser_accepts_safe_automated_run_options(self):
        from video_test import parse_args

        args = parse_args([
            "--video",
            "clip.mp4",
            "--duration",
            "2.5",
            "--no-mouse",
            "--log-dir",
            "tests/logs",
        ])

        self.assertEqual(args.video, "clip.mp4")
        self.assertEqual(args.duration, 2.5)
        self.assertTrue(args.no_mouse)
        self.assertEqual(args.log_dir, "tests/logs")


if __name__ == "__main__":
    unittest.main()
