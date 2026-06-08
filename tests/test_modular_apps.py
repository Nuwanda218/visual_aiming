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


if __name__ == "__main__":
    unittest.main()
