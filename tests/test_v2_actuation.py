import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Command, Detection
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.actuation.targeting import Actuator, select_target, compute_aim_point, compute_error


class SelectTargetTests(unittest.TestCase):
    def test_returns_none_when_empty(self):
        self.assertIsNone(select_target([], crosshair=(100, 100)))

    def test_prefers_head_over_person(self):
        """有头选头，即使 person 更近。"""
        head = Detection(x=200, y=200, w=20, h=20, confidence=0.8, label="head")
        person = Detection(x=95, y=95, w=10, h=10, confidence=0.9, label="person")

        result = select_target([person, head], crosshair=(100, 100))
        self.assertEqual(result, head)

    def test_selects_nearest_head_when_multiple(self):
        far_head = Detection(x=300, y=300, w=20, h=20, confidence=0.8, label="head")
        near_head = Detection(x=92, y=95, w=10, h=10, confidence=0.7, label="head")

        result = select_target([far_head, near_head], crosshair=(100, 100))
        self.assertEqual(result, near_head)

    def test_falls_back_to_person_when_no_head(self):
        person = Detection(x=90, y=90, w=20, h=20, confidence=0.9, label="person")

        result = select_target([person], crosshair=(100, 100))
        self.assertEqual(result, person)


class ComputeAimPointTests(unittest.TestCase):
    def test_head_aim_point_biased_up(self):
        """head 框瞄准点应该在框内偏上位置。"""
        det = Detection(x=100, y=100, w=40, h=60, confidence=0.9, label="head")

        ax, ay = compute_aim_point(det, head_label="head", head_bias=0.35)

        self.assertEqual(ax, 120)  # x 居中: 100 + 40//2
        self.assertEqual(ay, 121)  # y 偏上: 100 + int(60 * 0.35)

    def test_person_aim_point_near_top(self):
        """person 框瞄准点应该在框内顶部偏下（估算头部）。"""
        det = Detection(x=100, y=100, w=40, h=200, confidence=0.9, label="person")

        ax, ay = compute_aim_point(det, head_label="head", body_bias=0.25)

        self.assertEqual(ax, 120)  # x 居中
        self.assertEqual(ay, 150)  # y 偏上: 100 + int(200 * 0.25)


class ComputeErrorTests(unittest.TestCase):
    def test_aim_at_crosshair_returns_zero(self):
        self.assertEqual(compute_error((100, 100), crosshair=(100, 100)), (0, 0))

    def test_aim_right_of_crosshair(self):
        self.assertEqual(compute_error((115, 100), crosshair=(100, 100)), (15, 0))


class ActuatorTests(unittest.TestCase):
    def test_noop_when_no_detections(self):
        actuator = Actuator(Config(image_width=200, image_height=200))
        cmd = actuator.process([])
        self.assertEqual(cmd.reason, "no_target")

    def test_prefers_head_in_process(self):
        """Actuator.process 应该有头选头。"""
        actuator = Actuator(Config(image_width=400, image_height=400))
        head = Detection(x=250, y=250, w=20, h=20, confidence=0.8, label="head")
        person = Detection(x=195, y=195, w=10, h=10, confidence=0.9, label="person")

        cmd = actuator.process([person, head])
        self.assertEqual(cmd.mode, "relative")
        # 应该是瞄向 head 而不是 person
        self.assertNotEqual(cmd.dx, 0)


from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput


class NullOutputTests(unittest.TestCase):
    def test_apply_does_nothing(self):
        output = NullOutput()
        output.apply(Command.noop("test"))
        output.close()


class LogOutputTests(unittest.TestCase):
    def test_records_commands(self):
        output = LogOutput()
        cmd = Command(dx=3, dy=-2, mode="relative", reason="tracking")
        output.apply(cmd)
        self.assertEqual(len(output.commands), 1)
        self.assertEqual(output.commands[0].dx, 3)

    def test_close_is_safe(self):
        output = LogOutput()
        output.close()
        output.close()


if __name__ == "__main__":
    unittest.main()
