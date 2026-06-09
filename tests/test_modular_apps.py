import sys
import json
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import ModularConfig


class ModularAppsTest(unittest.TestCase):
    def test_output_factory_defaults_to_null(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        output = create_output_backend(config.output)

        self.assertEqual(output.name, "null")

    def test_output_factory_requires_real_mouse_flag(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        config.output.backend = "win_mouse"
        config.output.enable_real_mouse = False

        output = create_output_backend(config.output)

        self.assertEqual(output.name, "null")

    def test_output_factory_returns_win_mouse_when_explicitly_enabled(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        config.output.backend = "win_mouse"
        config.output.enable_real_mouse = True

        output = create_output_backend(config.output, mouse_sender=lambda dx, dy: None)

        self.assertEqual(output.name, "win_mouse")

    def test_replay_runner_processes_all_frames(self):
        import numpy as np
        from visual_aiming.adapters.frame_sources.video_file import ArrayFrameSource
        from visual_aiming.app.replay import run_replay
        from visual_aiming.core.schemas import DetectionPacket

        class EmptyDetector:
            name = "empty"
            def detect(self, frame):
                return DetectionPacket(frame.sequence, [], 0.0, self.name, fresh=True)

        frames = [np.zeros((4, 6, 3), dtype=np.uint8), np.zeros((4, 6, 3), dtype=np.uint8)]
        source = ArrayFrameSource(frames, fps=10.0, roi_offset=(0, 0), crosshair=(3, 2))

        results = run_replay(ModularConfig(), source, EmptyDetector())

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].sequence, 0)
        self.assertEqual(results[1].sequence, 1)

    def test_video_test_wait_subtracts_previous_frame_work(self):
        from visual_aiming.app.timing import compute_active_wait_ms

        self.assertEqual(compute_active_wait_ms(fps=60.0, previous_frame_ms=0.0), 16)
        self.assertEqual(compute_active_wait_ms(fps=60.0, previous_frame_ms=10.0), 6)
        self.assertEqual(compute_active_wait_ms(fps=60.0, previous_frame_ms=40.0), 1)

    def test_video_overlay_builds_active_osd_lines(self):
        from tests.test_modular_outputs import make_result
        from visual_aiming.app.video_overlay import build_osd_lines

        lines = build_osd_lines(
            sequence=7,
            total_frames=100,
            active=True,
            result=make_result(),
            frame_work_ms=20.5,
            wait_ms=1,
            display_fps=44.8,
        )

        joined = "\n".join(lines)
        self.assertIn("Frame: 7/100", joined)
        self.assertIn("Det latency:", joined)
        self.assertIn("Pipeline:", joined)
        self.assertIn("Frame work: 20.5ms | Wait: 1ms", joined)
        self.assertIn("FPS: 44.8", joined)
        self.assertIn("(tracking)", joined)

    def test_log_analyzer_summarizes_modular_jsonl(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl

        rows = [
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected"},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking"},
                "detector_latency_ms": 10.0,
                "pipeline_latency_ms": 11.0,
                "latency_breakdown": {"detect_ms": 10.0, "select_ms": 0.1, "aim_ms": 0.1, "predict_ms": 0.1, "control_ms": 0.1, "total_ms": 11.0},
                "telemetry": {"wait_ms": 1.0, "frame_work_ms": 20.0, "display_fps": 45.0, "source_fps": 60.0, "active": True},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections"},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone"},
                "detector_latency_ms": 30.0,
                "pipeline_latency_ms": 31.0,
                "latency_breakdown": {"detect_ms": 30.0, "select_ms": 0.1, "aim_ms": 0.1, "predict_ms": 0.1, "control_ms": 0.1, "total_ms": 31.0},
                "telemetry": {"wait_ms": 1.0, "frame_work_ms": 40.0, "display_fps": 30.0, "source_fps": 60.0, "active": True},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = analyze_jsonl(path)

        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["detection_rate_pct"], 50.0)
        self.assertEqual(report["target_lost_rate_pct"], 50.0)
        self.assertEqual(report["detector_latency_ms"]["p50"], 10.0)
        self.assertEqual(report["detector_latency_ms"]["p95"], 30.0)
        self.assertEqual(report["display_fps"]["avg"], 37.5)
        self.assertEqual(report["bottleneck"], "detect")


class ModularCliTest(unittest.TestCase):
    def test_main_parser_accepts_modular_safe_flags(self):
        # 把项目根目录加入路径以便 import main
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--modular", "--video", "sample.mp4", "--output", "log", "--diagnostics", "run.jsonl"])

        self.assertTrue(args.modular)
        self.assertEqual(args.video, "sample.mp4")
        self.assertEqual(args.output, "log")
        self.assertEqual(args.diagnostics, "run.jsonl")
        self.assertFalse(args.real_mouse)

    def test_main_parser_accepts_explicit_real_mouse_flag(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--modular", "--real-mouse", "--output", "win_mouse"])

        self.assertTrue(args.modular)
        self.assertTrue(args.real_mouse)
        self.assertEqual(args.output, "win_mouse")

    def test_main_parser_accepts_analyze_log(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--analyze-log", "logs/run.jsonl"])

        self.assertEqual(args.analyze_log, "logs/run.jsonl")


if __name__ == "__main__":
    unittest.main()
