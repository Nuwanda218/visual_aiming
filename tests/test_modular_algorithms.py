import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import AimConfig, PredictionConfig, ControlConfig, TargetSelectionConfig
from visual_aiming.core.schemas import AimMeasurement, Detection, RuntimeMode


class TargetSelectorTest(unittest.TestCase):
    def test_prefers_head_near_crosshair(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        selector = TargetSelector(TargetSelectionConfig(head_class_id=0, person_class_id=1, target_preference=0.85))
        detections = [
            Detection(bbox=(0, 0, 40, 80), confidence=0.95, class_id=1, class_name="person"),
            Detection(bbox=(95, 95, 20, 20), confidence=0.75, class_id=0, class_name="head"),
        ]

        selected = selector.select(detections, roi_center=(100, 100))

        self.assertIsNotNone(selected.detection)
        self.assertEqual(selected.detection.class_name, "head")
        self.assertEqual(selected.reason, "selected")
        self.assertIn("class", selected.score_parts)

    def test_sticky_target_delays_small_switches(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        selector = TargetSelector(TargetSelectionConfig(stickiness=0.5, history_radius=80, switch_margin=0.2))
        previous = Detection(bbox=(90, 90, 20, 20), confidence=0.8, class_id=0, class_name="head")
        selector.select([previous], roi_center=(100, 100))
        near_previous = Detection(bbox=(92, 92, 20, 20), confidence=0.7, class_id=0, class_name="head")
        slightly_better = Detection(bbox=(100, 100, 20, 20), confidence=0.71, class_id=0, class_name="head")

        selected = selector.select([slightly_better, near_previous], roi_center=(100, 100))

        self.assertEqual(selected.detection.bbox, near_previous.bbox)
        self.assertFalse(selected.switched)

    def test_switch_requires_meaningful_score_improvement(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        config = TargetSelectionConfig()
        config.sticky_enabled = True
        config.sticky_switch_margin = 0.35
        selector = TargetSelector(config)

        first = Detection((40, 40, 20, 20), confidence=0.90, class_id=0, class_name="head")
        close_competitor = Detection((45, 40, 20, 20), confidence=0.91, class_id=0, class_name="head")

        selected = selector.select([first], roi_center=(50, 50))
        next_selected = selector.select([close_competitor, first], roi_center=(50, 50))

        self.assertEqual(selected.detection.bbox, first.bbox)
        self.assertEqual(next_selected.detection.bbox, first.bbox)
        self.assertFalse(next_selected.switched)

    def test_switches_when_new_target_is_clearly_better(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        config = TargetSelectionConfig()
        config.sticky_enabled = True
        config.sticky_switch_margin = 0.10
        selector = TargetSelector(config)

        old = Detection((10, 10, 20, 20), confidence=0.55, class_id=1, class_name="person")
        better = Detection((45, 40, 20, 20), confidence=0.99, class_id=0, class_name="head")

        selector.select([old], roi_center=(50, 50))
        selected = selector.select([better, old], roi_center=(50, 50))

        self.assertEqual(selected.detection.bbox, better.bbox)
        self.assertTrue(selected.switched)


class AimStrategyTest(unittest.TestCase):
    def test_head_aim_uses_head_bias_and_roi_offset(self):
        from visual_aiming.algorithms.aim_point import AimStrategy

        strategy = AimStrategy(AimConfig(head_bias=0.25), head_class_id=0)
        detection = Detection(bbox=(10, 20, 40, 80), confidence=1.0, class_id=0, class_name="head")

        measurement = strategy.measure(detection, roi_offset=(100, 200), crosshair=(150, 250))

        self.assertEqual(measurement.point, (130, 240))
        self.assertEqual(measurement.error, (-20.0, -10.0))
        self.assertTrue(measurement.valid)

    def test_missing_target_returns_invalid_measurement(self):
        from visual_aiming.algorithms.aim_point import AimStrategy

        strategy = AimStrategy(AimConfig(), head_class_id=0)

        measurement = strategy.measure(None, roi_offset=(100, 200), crosshair=(150, 250))

        self.assertIsNone(measurement.point)
        self.assertEqual(measurement.error, (0.0, 0.0))
        self.assertFalse(measurement.valid)


class PredictorTest(unittest.TestCase):
    def test_predictor_tracks_velocity_and_predicts_forward(self):
        from visual_aiming.algorithms.prediction import AlphaBetaPredictor

        predictor = AlphaBetaPredictor(PredictionConfig(alpha=0.5, beta=0.25, lead_time=0.10))
        first = AimMeasurement(point=(100, 100), crosshair=(90, 100), error=(10.0, 0.0), valid=True)
        second = AimMeasurement(point=(110, 100), crosshair=(90, 100), error=(20.0, 0.0), valid=True)

        predictor.update(first, RuntimeMode(active=True, firing=False), now=1.0)
        predicted = predictor.update(second, RuntimeMode(active=True, firing=False), now=1.1)

        self.assertEqual(predicted.state, "tracking")
        self.assertGreater(predicted.point[0], 105)
        self.assertGreater(predicted.velocity[0], 0.0)

    def test_predictor_holds_recent_track_when_measurement_missing(self):
        from visual_aiming.algorithms.prediction import AlphaBetaPredictor

        predictor = AlphaBetaPredictor(PredictionConfig(max_hold_ms=200.0))
        measurement = AimMeasurement(point=(100, 100), crosshair=(90, 100), error=(10.0, 0.0), valid=True)
        missing = AimMeasurement(point=None, crosshair=(90, 100), error=(0.0, 0.0), valid=False)

        predictor.update(measurement, RuntimeMode(active=True, firing=False), now=1.0)
        predicted = predictor.update(missing, RuntimeMode(active=True, firing=False), now=1.1)

        self.assertEqual(predicted.state, "held")
        self.assertIsNotNone(predicted.point)


class ControllerTest(unittest.TestCase):
    def test_controller_returns_noop_inside_deadzone(self):
        from visual_aiming.algorithms.control import RelativeController

        controller = RelativeController(ControlConfig(deadzone=3.0))
        predicted = AimMeasurement(point=(101, 100), crosshair=(100, 100), error=(1.0, 0.0), valid=True)

        command = controller.update(predicted.error, active=True, dt=1 / 240)

        self.assertEqual(command.mode, "none")
        self.assertEqual((command.dx, command.dy), (0, 0))
        self.assertEqual(command.reason, "deadzone")

    def test_controller_limits_large_step(self):
        from visual_aiming.algorithms.control import RelativeController

        controller = RelativeController(ControlConfig(deadzone=0.0, speed_gain=1000.0, max_speed=100000.0, max_step=5))

        command = controller.update((100.0, 0.0), active=True, dt=1.0)

        self.assertEqual(command.mode, "relative")
        self.assertEqual(command.dx, 5)
        self.assertTrue(command.limited)


if __name__ == "__main__":
    unittest.main()
