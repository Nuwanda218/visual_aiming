import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Command, Detection
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.actuation.targeting import Actuator, select_nearest, compute_error


class SelectNearestTests(unittest.TestCase):
    def test_returns_none_when_empty(self):
        self.assertIsNone(select_nearest([], crosshair=(100, 100)))

    def test_returns_single(self):
        det = Detection(x=90, y=90, w=20, h=20, confidence=0.9)
        self.assertEqual(select_nearest([det], crosshair=(100, 100)), det)

    def test_selects_closest(self):
        far = Detection(x=200, y=200, w=20, h=20, confidence=0.9)
        near = Detection(x=92, y=95, w=10, h=10, confidence=0.7)

        self.assertEqual(select_nearest([far, near], crosshair=(100, 100)), near)


class ComputeErrorTests(unittest.TestCase):
    def test_centered_returns_zero(self):
        det = Detection(x=95, y=95, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (0, 0))

    def test_right_of_crosshair(self):
        det = Detection(x=110, y=95, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (15, 0))

    def test_above_crosshair(self):
        det = Detection(x=95, y=75, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (0, -20))


class ActuatorTests(unittest.TestCase):
    def test_process_returns_noop_when_no_detections(self):
        actuator = Actuator(Config(image_width=200, image_height=200))

        cmd = actuator.process([])

        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "no_target")

    def test_process_returns_relative_command(self):
        actuator = Actuator(Config(image_width=200, image_height=200))
        det = Detection(x=110, y=85, w=10, h=10, confidence=0.9)

        cmd = actuator.process([det])

        self.assertEqual(cmd.dx, 15)
        self.assertEqual(cmd.dy, -10)
        self.assertEqual(cmd.mode, "relative")

    def test_process_returns_on_target_when_centered(self):
        actuator = Actuator(Config(image_width=200, image_height=200))
        det = Detection(x=95, y=95, w=10, h=10, confidence=0.9)

        cmd = actuator.process([det])

        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "on_target")


if __name__ == "__main__":
    unittest.main()
