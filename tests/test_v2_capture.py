import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Frame
from visual_aiming_v2.capture.sources import MemoryCapture


class MemoryCaptureTests(unittest.TestCase):
    def test_reads_all_frames_then_returns_none(self):
        frames = [
            Frame(image="a", sequence=0, timestamp=0.0),
            Frame(image="b", sequence=1, timestamp=0.1),
        ]
        source = MemoryCapture(frames)

        self.assertEqual(source.read(), frames[0])
        self.assertEqual(source.read(), frames[1])
        self.assertIsNone(source.read())

    def test_close_is_safe(self):
        source = MemoryCapture([])
        source.close()
        source.close()


if __name__ == "__main__":
    unittest.main()
