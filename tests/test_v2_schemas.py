import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class FrameTests(unittest.TestCase):
    def test_frame_holds_image_sequence_timestamp(self):
        frame = Frame(image="fake_image", sequence=0, timestamp=1.5)

        self.assertEqual(frame.image, "fake_image")
        self.assertEqual(frame.sequence, 0)
        self.assertEqual(frame.timestamp, 1.5)


class DetectionTests(unittest.TestCase):
    def test_center_computed_from_bbox(self):
        det = Detection(x=10, y=20, w=30, h=40, confidence=0.75, label="head")

        self.assertEqual(det.center, (25, 40))

    def test_defaults(self):
        det = Detection(x=0, y=0, w=10, h=10, confidence=0.5)

        self.assertEqual(det.label, "unknown")


class CommandTests(unittest.TestCase):
    def test_noop_factory(self):
        cmd = Command.noop("no_target")

        self.assertEqual(cmd.dx, 0)
        self.assertEqual(cmd.dy, 0)
        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "no_target")

    def test_relative_command(self):
        cmd = Command(dx=5, dy=-3, mode="relative", reason="tracking")

        self.assertEqual(cmd.dx, 5)
        self.assertEqual(cmd.dy, -3)


if __name__ == "__main__":
    unittest.main()
