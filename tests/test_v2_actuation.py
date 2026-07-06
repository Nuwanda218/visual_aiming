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

        self.assertEqual(ax, 120)
        self.assertEqual(ay, 121)

    def test_person_aim_point_near_top(self):
        """person 框瞄准点应该在框内顶部偏下（估算头部）。"""
        det = Detection(x=100, y=100, w=40, h=200, confidence=0.9, label="person")

        ax, ay = compute_aim_point(det, head_label="head", body_bias=0.25)

        self.assertEqual(ax, 120)
        self.assertEqual(ay, 150)


class ComputeErrorTests(unittest.TestCase):
    def test_aim_at_crosshair_returns_zero(self):
        self.assertEqual(compute_error((100, 100), crosshair=(100, 100)), (0, 0))

    def test_aim_right_of_crosshair(self):
        self.assertEqual(compute_error((115, 100), crosshair=(100, 100)), (15, 0))


class ActuatorTests(unittest.TestCase):
    def _config(self, image_width: int, image_height: int) -> Config:
        config = Config()
        config.capture.image_width = image_width
        config.capture.image_height = image_height
        return config

    def test_noop_when_no_detections(self):
        actuator = Actuator(self._config(image_width=200, image_height=200))
        cmd = actuator.process([])
        self.assertEqual(cmd.reason, "no_target")

    def test_prefers_head_in_process(self):
        """Actuator.process 应该有头选头。"""
        actuator = Actuator(self._config(image_width=400, image_height=400))
        head = Detection(x=250, y=250, w=20, h=20, confidence=0.8, label="head")
        person = Detection(x=195, y=195, w=10, h=10, confidence=0.9, label="person")

        cmd = actuator.process([person, head])
        self.assertEqual(cmd.mode, "relative")
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
        points = [(100, 100), (102, 98), (99, 101), (101, 100), (100, 99)]
        results = [smoother.smooth(p) for p in points]
        last = results[-1]
        self.assertLessEqual(abs(last[0] - 100), 2)
        self.assertLessEqual(abs(last[1] - 100), 2)

    def test_follows_real_movement(self):
        """目标真的在移动时，平滑点应该跟上。"""
        smoother = AimSmoother()
        for i in range(20):
            smoother.smooth((100 + i * 10, 100))
        result = smoother.smooth((300, 100))
        self.assertGreater(result[0], 250)

    def test_hold_predicts_on_target_lost(self):
        """目标丢失后应继续预测几帧。"""
        smoother = AimSmoother(hold_frames=3)
        smoother.smooth((100, 100))
        smoother.smooth((110, 100))
        result = smoother.smooth(None)
        self.assertIsNotNone(result)

    def test_hold_expires(self):
        """超过 hold_frames 后应返回 None。"""
        smoother = AimSmoother(hold_frames=2)
        smoother.smooth((100, 100))
        smoother.smooth(None)
        smoother.smooth(None)
        result = smoother.smooth(None)
        self.assertIsNone(result)

    def test_reset_clears_state(self):
        """reset 后应重新初始化。"""
        smoother = AimSmoother()
        smoother.smooth((100, 100))
        smoother.reset()
        result = smoother.smooth((200, 200))
        self.assertEqual(result, (200, 200))


from visual_aiming_v2.actuation.tracker import TargetTracker, detection_boxes_match


class DetectionBoxMatchTests(unittest.TestCase):
    def test_matches_near_detection_with_similar_size(self):
        locked = Detection(x=100, y=100, w=40, h=40, confidence=0.9)
        candidate = Detection(x=108, y=104, w=42, h=39, confidence=0.9)

        self.assertTrue(detection_boxes_match(locked, candidate))

    def test_rejects_far_detection(self):
        locked = Detection(x=100, y=100, w=40, h=40, confidence=0.9)
        candidate = Detection(x=180, y=100, w=40, h=40, confidence=0.9)

        self.assertFalse(detection_boxes_match(locked, candidate, match_distance_ratio=0.75, min_match_distance=18.0))

    def test_rejects_size_change_too_large(self):
        locked = Detection(x=100, y=100, w=40, h=40, confidence=0.9)
        candidate = Detection(x=104, y=104, w=100, h=100, confidence=0.9)

        self.assertFalse(detection_boxes_match(locked, candidate, size_ratio_max=1.8))


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
        self.assertFalse(tracker.switched)
        self.assertTrue(tracker.has_measurement_this_frame)

    def test_keeps_lock_when_detection_box_moves_within_match_distance(self):
        tracker = TargetTracker(match_distance_ratio=0.75, min_match_distance=18.0)
        original = Detection(x=150, y=150, w=50, h=50, confidence=0.9)
        tracker.update([original], (100, 100), self._select)
        original_moved = Detection(x=162, y=154, w=52, h=48, confidence=0.9)
        closer = Detection(x=95, y=95, w=20, h=20, confidence=0.9)

        result = tracker.update([original_moved, closer], (100, 100), self._select)

        self.assertEqual(result, original_moved)
        self.assertFalse(tracker.switched)
        self.assertEqual(tracker.locked_frames, 2)

    def test_switches_when_detection_box_moves_beyond_match_distance(self):
        tracker = TargetTracker(match_distance_ratio=0.5, min_match_distance=10.0)
        original = Detection(x=200, y=200, w=30, h=30, confidence=0.9)
        tracker.update([original], (100, 100), self._select)
        far = Detection(x=280, y=280, w=30, h=30, confidence=0.9)
        nearer = Detection(x=95, y=95, w=20, h=20, confidence=0.9)

        result = tracker.update([far, nearer], (100, 100), self._select)

        self.assertEqual(result, nearer)
        self.assertTrue(tracker.switched)

    def test_rejects_match_when_box_size_changes_too_much(self):
        tracker = TargetTracker(size_ratio_min=0.8, size_ratio_max=1.2)
        original = Detection(x=100, y=100, w=40, h=40, confidence=0.9)
        tracker.update([original], (100, 100), self._select)
        huge = Detection(x=102, y=102, w=90, h=90, confidence=0.9)
        fallback = Detection(x=95, y=95, w=20, h=20, confidence=0.9)

        result = tracker.update([huge, fallback], (100, 100), self._select)

        self.assertEqual(result, fallback)
        self.assertTrue(tracker.switched)

    def test_short_empty_detection_gap_does_not_steal_lock_on_reacquire(self):
        tracker = TargetTracker(lost_frame_grace=2)
        original = Detection(x=150, y=150, w=50, h=50, confidence=0.9)
        tracker.update([original], (100, 100), self._select)

        missing = tracker.update([], (100, 100), self._select)
        reacquired = Detection(x=154, y=148, w=50, h=50, confidence=0.9)
        closer = Detection(x=95, y=95, w=20, h=20, confidence=0.9)
        result = tracker.update([reacquired, closer], (100, 100), self._select)

        self.assertIsNone(missing)
        self.assertEqual(result, reacquired)
        self.assertEqual(tracker.lost_frames, 0)
        self.assertFalse(tracker.switched)

    def test_lost_gap_expires_then_reselects_best_target(self):
        tracker = TargetTracker(lost_frame_grace=1)
        original = Detection(x=150, y=150, w=50, h=50, confidence=0.9)
        tracker.update([original], (100, 100), self._select)
        tracker.update([], (100, 100), self._select)
        tracker.update([], (100, 100), self._select)
        new_target = Detection(x=95, y=95, w=20, h=20, confidence=0.9)

        result = tracker.update([new_target], (100, 100), self._select)

        self.assertEqual(result, new_target)
        self.assertFalse(tracker.switched)

    def test_returns_none_when_all_gone(self):
        tracker = TargetTracker(lost_frame_grace=0)
        det = Detection(x=100, y=100, w=50, h=50, confidence=0.9)
        tracker.update([det], (100, 100), self._select)
        result = tracker.update([], (100, 100), self._select)
        self.assertIsNone(result)
        self.assertIsNone(tracker.locked_target)


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
