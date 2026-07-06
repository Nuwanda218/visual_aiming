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
from visual_aiming_v2.actuation.aim_filter import AimSmoother


class AimSmootherTests(unittest.TestCase):
    def test_first_point_passes_through(self):
        """首次观测应直接返回原始值。"""
        smoother = AimSmoother()
        result = smoother.smooth((100, 100))
        self.assertEqual(result, (100, 100))

    def test_reduces_jitter(self):
        """微小抖动应被吸收，输出比输入更集中。"""
        smoother = AimSmoother()
        # 在 (100,100) 附近抖动
        points = [(100, 100), (102, 98), (99, 101), (101, 100), (100, 99)]
        results = [smoother.smooth(p) for p in points]
        # 最后几个输出应接近 (100,100)
        last = results[-1]
        self.assertLessEqual(abs(last[0] - 100), 2)
        self.assertLessEqual(abs(last[1] - 100), 2)

    def test_follows_real_movement(self):
        """目标真的在移动时，平滑点应该跟上。"""
        smoother = AimSmoother()
        # 目标匀速向右移动
        for i in range(20):
            smoother.smooth((100 + i * 10, 100))
        result = smoother.smooth((300, 100))
        # 应该已经接近 300
        self.assertGreater(result[0], 250)

    def test_hold_predicts_on_target_lost(self):
        """目标丢失后应继续预测几帧。"""
        smoother = AimSmoother(hold_frames=3)
        smoother.smooth((100, 100))
        smoother.smooth((110, 100))
        # 目标丢失
        result = smoother.smooth(None)
        self.assertIsNotNone(result)

    def test_hold_expires(self):
        """超过 hold_frames 后应返回 None。"""
        smoother = AimSmoother(hold_frames=2)
        smoother.smooth((100, 100))
        smoother.smooth(None)  # hold 1
        smoother.smooth(None)  # hold 2
        result = smoother.smooth(None)  # 超过
        self.assertIsNone(result)

    def test_reset_clears_state(self):
        """reset 后应重新初始化。"""
        smoother = AimSmoother()
        smoother.smooth((100, 100))
        smoother.reset()
        # reset 后第一次应该直接返回原始值
        result = smoother.smooth((200, 200))
        self.assertEqual(result, (200, 200))


from visual_aiming_v2.actuation.tracker import TargetTracker, compute_iou


class ComputeIouTests(unittest.TestCase):
    def test_identical_boxes(self):
        a = Detection(x=100, y=100, w=50, h=50, confidence=0.9)
        self.assertAlmostEqual(compute_iou(a, a), 1.0)

    def test_no_overlap(self):
        a = Detection(x=0, y=0, w=50, h=50, confidence=0.9)
        b = Detection(x=200, y=200, w=50, h=50, confidence=0.9)
        self.assertAlmostEqual(compute_iou(a, b), 0.0)

    def test_partial_overlap(self):
        a = Detection(x=0, y=0, w=100, h=100, confidence=0.9)
        b = Detection(x=50, y=50, w=100, h=100, confidence=0.9)
        iou = compute_iou(a, b)
        self.assertGreater(iou, 0.0)
        self.assertLess(iou, 1.0)


class TargetTrackerTests(unittest.TestCase):
    def _select(self, dets, crosshair):
        import math
        if not dets:
            return None
        cx, cy = crosshair
        return min(dets, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))

    def test_locks_nearest_initially(self):
        tracker = TargetTracker()
        far = Detection(x=200, y=200, w=20, h=20, confidence=0.9)
        near = Detection(x=95, y=95, w=20, h=20, confidence=0.8)
        result = tracker.update([far, near], (100, 100), self._select)
        self.assertEqual(result, near)

    def test_keeps_locked_target_with_iou(self):
        tracker = TargetTracker()
        det1 = Detection(x=100, y=100, w=50, h=50, confidence=0.9)
        tracker.update([det1], (100, 100), self._select)
        det2 = Detection(x=105, y=102, w=48, h=50, confidence=0.9)
        result = tracker.update([det2], (100, 100), self._select)
        self.assertEqual(result, det2)
        self.assertEqual(tracker.locked_frames, 2)

    def test_ignores_closer_new_target(self):
        tracker = TargetTracker()
        original = Detection(x=150, y=150, w=50, h=50, confidence=0.9)
        tracker.update([original], (100, 100), self._select)
        original_moved = Detection(x=152, y=148, w=50, h=50, confidence=0.9)
        closer = Detection(x=95, y=95, w=20, h=20, confidence=0.9)
        result = tracker.update([original_moved, closer], (100, 100), self._select)
        self.assertEqual(result, original_moved)

    def test_switches_when_target_disappears(self):
        tracker = TargetTracker()
        target_a = Detection(x=100, y=100, w=50, h=50, confidence=0.9)
        target_b = Detection(x=200, y=200, w=30, h=30, confidence=0.8)
        tracker.update([target_a, target_b], (100, 100), self._select)
        result = tracker.update([target_b], (100, 100), self._select)
        self.assertEqual(result, target_b)

    def test_returns_none_when_all_gone(self):
        tracker = TargetTracker()
        det = Detection(x=100, y=100, w=50, h=50, confidence=0.9)
        tracker.update([det], (100, 100), self._select)
        result = tracker.update([], (100, 100), self._select)
        self.assertIsNone(result)


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
