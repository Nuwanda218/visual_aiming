import argparse
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.runtime_modes import RuntimeMode, choose_runtime_mode


class RuntimeModeTests(unittest.TestCase):
    def _args(self, **overrides):
        values = {
            "analyze_log": "",
            "video_test": False,
            "modular": False,
            "video": "",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_analyze_log_wins(self):
        mode = choose_runtime_mode(self._args(analyze_log="logs/run.jsonl"))
        self.assertEqual(mode, RuntimeMode.ANALYZE_LOG)

    def test_video_test_wins_before_modular(self):
        mode = choose_runtime_mode(self._args(video_test=True, modular=True, video="a.mp4"))
        self.assertEqual(mode, RuntimeMode.VIDEO_TEST)

    def test_modular_video_replay(self):
        mode = choose_runtime_mode(self._args(modular=True, video="a.mp4"))
        self.assertEqual(mode, RuntimeMode.MODULAR_REPLAY)

    def test_modular_realtime_opt_in(self):
        mode = choose_runtime_mode(self._args(modular=True))
        self.assertEqual(mode, RuntimeMode.MODULAR_REALTIME)

    def test_default_legacy_realtime(self):
        mode = choose_runtime_mode(self._args())
        self.assertEqual(mode, RuntimeMode.LEGACY_REALTIME)


if __name__ == "__main__":
    unittest.main()
