import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import ModularConfig


class ModularAppsTest(unittest.TestCase):
    def test_create_pipeline_uses_detector_factory_by_default(self):
        from visual_aiming.app.realtime import create_pipeline

        pipeline = create_pipeline(ModularConfig())

        self.assertEqual(pipeline.detector.name, "ultralytics")
        self.assertTrue(hasattr(pipeline.detector, "legacy_detector"))

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

    def test_replay_runner_uses_runtime_runner(self):
        from visual_aiming.app.replay import run_replay

        class Source:
            def __init__(self):
                self.frames = ["one", "two"]
                self.closed = False

            def read(self):
                return self.frames.pop(0) if self.frames else None

            def close(self):
                self.closed = True

        class Pipeline:
            def __init__(self):
                self.frames = []

            def tick(self, frame, now=None):
                self.frames.append(frame)
                return {"frame": frame}

        source = Source()
        pipeline = Pipeline()
        results = run_replay(ModularConfig(), source, pipeline=pipeline)

        self.assertEqual(results, [{"frame": "one"}, {"frame": "two"}])
        self.assertEqual(pipeline.frames, ["one", "two"])
        self.assertTrue(source.closed)

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

    def test_video_run_diagnostics_builds_log_path_and_summary_lines(self):
        from visual_aiming.app.video_run_diagnostics import build_video_log_path, format_summary_lines

        path = build_video_log_path("C:/videos/sample.mp4", timestamp="20260609_120000", log_dir=Path("logs"))
        self.assertEqual(path, Path("logs") / "video_test_sample_20260609_120000.jsonl")

        lines = format_summary_lines(
            {
                "samples": 2,
                "noop_commands": 1,
                "target_lost": 1,
                "target_switches": 0,
                "avg_command_magnitude": 3.5,
                "max_command_magnitude": 7.0,
                "max_detector_latency_ms": 12.0,
                "max_pipeline_latency_ms": 13.0,
            },
            jsonl_path=path,
        )

        joined = "\n".join(lines)
        self.assertIn("处理帧数: 2", joined)
        self.assertIn("平均控制幅度: 3.50", joined)
        self.assertIn("日志路径: logs", joined)

    def test_log_analyzer_summarizes_modular_jsonl(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl

        rows = [
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "switched": False},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking"},
                "detector_latency_ms": 10.0,
                "pipeline_latency_ms": 11.0,
                "latency_breakdown": {"detect_ms": 10.0, "select_ms": 0.1, "aim_ms": 0.1, "predict_ms": 0.1, "control_ms": 0.1, "total_ms": 11.0},
                "telemetry": {"wait_ms": 1.0, "frame_work_ms": 20.0, "display_fps": 45.0, "source_fps": 60.0, "active": True},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections", "switched": True},
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
        self.assertEqual(report["detection_output_rate_pct"], 50.0)
        self.assertEqual(report["detection_rate_pct"], 50.0)
        self.assertEqual(report["target_lost_rate_pct"], 50.0)
        self.assertEqual(report["detector_latency_ms"]["p50"], 10.0)
        self.assertEqual(report["detector_latency_ms"]["p95"], 30.0)
        self.assertEqual(report["detector_latency_ms"]["p99"], 30.0)
        self.assertEqual(report["display_fps"]["avg"], 37.5)
        self.assertEqual(report["bottleneck"], "detect")
        self.assertEqual(report["target_switches"], 1)
        self.assertEqual(report["predicted_state_counts"], {"tracking": 1, "lost": 1})
        self.assertIn("wait_not_bottleneck", report["insight_codes"])

    def test_log_analyzer_labels_detection_output_rate_not_accuracy(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {"detections": [{"class_id": 0}], "predicted": {"state": "tracking"}, "command": {"mode": "relative"}},
            {"detections": [], "predicted": {"state": "lost"}, "command": {"mode": "none"}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = format_report(analyze_jsonl(path))

        self.assertIn("检测输出率: 50.0%", report)
        self.assertNotIn("检测命中率", report)

    def test_log_analyzer_reports_annotation_based_detection_quality(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {"target_visible": True, "detections": [{"class_id": 0}]},
            {"target_visible": True, "detections": []},
            {"enemy_visible": False, "detections": [{"class_id": 0}]},
            {"annotations": {"enemy_visible": False}, "detections": []},
            {"detections": [{"class_id": 0}]},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            analyzed = analyze_jsonl(path)
            report = format_report(analyzed)

        self.assertEqual(analyzed["annotation_quality"], {
            "target_visible_frames": 2,
            "empty_scene_frames": 2,
            "visible_target_detection_rate_pct": 50.0,
            "empty_scene_false_positive_rate_pct": 50.0,
        })
        self.assertIn("可见目标检出率: 50.0% (2 frames)", report)
        self.assertIn("空场景误检率: 50.0% (2 frames)", report)

    def test_log_analyzer_reports_continuity_and_nonzero_command_metrics(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "switched": False},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 3, "dy": 0},
            },
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "switched": False},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "subpixel", "dx": 0, "dy": 0},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections", "switched": False},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections", "switched": False},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "switched": True},
                "predicted": {"state": "held"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 1, "dy": -1},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = analyze_jsonl(path)

        self.assertEqual(report["nonzero_command_rate_pct"], 40.0)
        self.assertEqual(
            report["continuity"],
            {
                "max_tracking_streak": 2,
                "max_lost_streak": 2,
                "max_detection_streak": 2,
                "max_no_detection_streak": 2,
                "max_relative_command_streak": 2,
                "max_nonzero_command_streak": 1,
            },
        )
        self.assertIn("最长追踪段: 2", format_report(report))

    def test_log_analyzer_reports_problem_segments_with_sequences(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {
                "sequence": 10,
                "detections": [],
                "selected": {"reason": "no_detections"},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
            {
                "sequence": 11,
                "detections": [],
                "selected": {"reason": "no_detections"},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
            {
                "sequence": 12,
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "detection": {"bbox": [0, 0, 10, 10]}},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "subpixel", "dx": 0, "dy": 0},
            },
            {
                "sequence": 13,
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "detection": {"bbox": [30, 40, 10, 10]}},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 2, "dy": 0},
            },
            {
                "sequence": 14,
                "detections": [],
                "selected": {"reason": "no_detections"},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            analyzed = analyze_jsonl(path)
            report = format_report(analyzed)

        self.assertEqual(analyzed["problem_segments"], {
            "longest_no_detection": {"length": 2, "start_sequence": 10, "end_sequence": 11},
            "longest_lost": {"length": 2, "start_sequence": 10, "end_sequence": 11},
            "longest_zero_command": {"length": 3, "start_sequence": 10, "end_sequence": 12},
        })
        self.assertEqual(analyzed["largest_selected_center_jump"], {
            "distance_px": 50.0,
            "from_sequence": 12,
            "to_sequence": 13,
        })
        self.assertIn("异常段: 无检测=2(seq 10-11), 丢失=2(seq 10-11), 零指令=3(seq 10-12)", report)
        self.assertIn("最大目标跳变: 50.00px (seq 12->13)", report)

    def test_log_analyzer_reports_command_magnitude_distribution(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {"command": {"dx": 0, "dy": 0}},
            {"command": {"dx": 3, "dy": 4}},
            {"command": {"dx": 6, "dy": 8}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            analyzed = analyze_jsonl(path)
            report = format_report(analyzed)

        self.assertEqual(analyzed["command_magnitude_px"]["p50"], 5.0)
        self.assertEqual(analyzed["command_magnitude_px"]["max"], 10.0)
        self.assertEqual(analyzed["nonzero_command_magnitude_px"]["p50"], 5.0)
        self.assertIn("指令幅度: p50=5.00px p95=10.00px max=10.00px", report)
        self.assertIn("非零指令幅度: p50=5.00px p95=10.00px max=10.00px", report)

    def test_log_analyzer_report_includes_reason_count_summaries(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "switched": False},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 2, "dy": 1},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections", "switched": False},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
            {
                "detections": [],
                "selected": {"reason": "no_detections", "switched": False},
                "predicted": {"state": "lost"},
                "command": {"mode": "none", "reason": "deadzone", "dx": 0, "dy": 0},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = format_report(analyze_jsonl(path))

        self.assertIn("预测状态: lost=2, tracking=1", report)
        self.assertIn("选择原因: no_detections=2, selected=1", report)
        self.assertIn("命令原因: deadzone=2, tracking=1", report)

    def test_log_analyzer_reports_selected_center_jump_stats(self):
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        rows = [
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "detection": {"bbox": [0, 0, 10, 10]}},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 1, "dy": 1},
            },
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "detection": {"bbox": [3, 4, 10, 10]}},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 1, "dy": 1},
            },
            {
                "detections": [{"class_id": 0}],
                "selected": {"reason": "selected", "detection": {"bbox": [13, 4, 10, 10]}},
                "predicted": {"state": "tracking"},
                "command": {"mode": "relative", "reason": "tracking", "dx": 1, "dy": 1},
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = analyze_jsonl(path)

        self.assertEqual(report["selected_center_jump_px"]["p50"], 5.0)
        self.assertEqual(report["selected_center_jump_px"]["max"], 10.0)
        self.assertIn("目标中心跳变: p50=5.00px", format_report(report))


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
        self.assertEqual(args.mouse_method, "set_cursor")
        self.assertFalse(args.real_mouse)

    def test_main_parser_accepts_explicit_real_mouse_flag(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--modular", "--real-mouse", "--output", "win_mouse"])

        self.assertTrue(args.modular)
        self.assertTrue(args.real_mouse)
        self.assertEqual(args.output, "win_mouse")

    def test_main_parser_accepts_mouse_method_flag(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--modular", "--output", "win_mouse", "--real-mouse", "--mouse-method", "sendinput"])

        self.assertEqual(args.mouse_method, "sendinput")

    def test_main_parser_accepts_analyze_log(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import parse_args

        args = parse_args(["--analyze-log", "logs/run.jsonl"])

        self.assertEqual(args.analyze_log, "logs/run.jsonl")

    def test_main_video_test_delegates_to_modular_runner(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from main import main

        with patch("visual_aiming.app.video_test.run_video_test", return_value=7) as run_video_test:
            result = main(["--video-test"])

        self.assertEqual(result, 7)
        run_video_test.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
