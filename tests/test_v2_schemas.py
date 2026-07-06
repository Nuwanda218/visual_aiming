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


from visual_aiming_v2.shared.ports import ActuationPort, CapturePort, DetectorPort, OutputPort


class PortsTests(unittest.TestCase):
    def test_all_ports_importable(self):
        self.assertIsNotNone(CapturePort)
        self.assertIsNotNone(DetectorPort)
        self.assertIsNotNone(ActuationPort)
        self.assertIsNotNone(OutputPort)


from visual_aiming_v2.shared.config import Config


class ConfigTests(unittest.TestCase):
    def test_defaults_are_grouped_by_v2_layer(self):
        config = Config()

        self.assertEqual(config.perception.model_path, "models/best.pt")
        self.assertEqual(config.perception.confidence, 0.5)
        self.assertEqual(config.perception.device, "auto")
        self.assertGreater(config.capture.image_width, 0)
        self.assertGreater(config.capture.image_height, 0)
        self.assertGreater(config.control.speed, 0.0)
        self.assertGreater(config.tracker.match_distance_ratio, 0.0)
        self.assertTrue(config.smoothing.enabled)

    def test_nested_overrides(self):
        config = Config()
        config.perception.model_path = "custom.pt"
        config.perception.confidence = 0.8
        config.capture.image_width = 320
        config.control.speed = 220.0

        self.assertEqual(config.perception.model_path, "custom.pt")
        self.assertEqual(config.perception.confidence, 0.8)
        self.assertEqual(config.capture.image_width, 320)
        self.assertEqual(config.control.speed, 220.0)


if __name__ == "__main__":
    unittest.main()
