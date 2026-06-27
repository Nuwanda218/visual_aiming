import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.schemas import Command, Detection, Frame, TickResult


class V2SchemaTests(unittest.TestCase):
    def test_detection_center_is_computed_from_bbox(self):
        detection = Detection(x=10, y=20, w=30, h=40, confidence=0.75, label="target")

        self.assertEqual(detection.center, (25, 40))

    def test_command_defaults_to_noop(self):
        command = Command.noop("no_target")

        self.assertEqual(command.dx, 0)
        self.assertEqual(command.dy, 0)
        self.assertEqual(command.mode, "none")
        self.assertEqual(command.reason, "no_target")

    def test_tick_result_preserves_intermediate_state(self):
        frame = Frame(sequence=1, image="frame", timestamp=12.5, crosshair=(100, 100))
        detection = Detection(x=90, y=80, w=20, h=30, confidence=0.8, label="target")
        command = Command(dx=0, dy=-5, mode="relative", reason="tracking")
        result = TickResult(frame=frame, detections=[detection], selected=detection, command=command)

        self.assertEqual(result.frame.sequence, 1)
        self.assertEqual(result.selected.center, (100, 95))
        self.assertEqual(result.command.dy, -5)


if __name__ == "__main__":
    unittest.main()
