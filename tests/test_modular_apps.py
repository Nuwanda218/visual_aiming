import sys
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


if __name__ == "__main__":
    unittest.main()
