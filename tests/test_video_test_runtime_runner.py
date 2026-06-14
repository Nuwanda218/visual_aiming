import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.app.video_test import VideoDebugObserver


class VideoDebugObserverTests(unittest.TestCase):
    def test_observer_records_latest_frame_and_result(self):
        observer = VideoDebugObserver()

        observer.on_tick("frame", {"seq": 1})

        self.assertEqual(observer.latest_frame, "frame")
        self.assertEqual(observer.latest_result, {"seq": 1})


if __name__ == "__main__":
    unittest.main()
