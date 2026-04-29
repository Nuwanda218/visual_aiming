import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.runtime_state import RuntimeState
from visual_aiming.core.pipeline import RuntimePipeline


class RuntimeStateTest(unittest.TestCase):
    def test_reset_tracking_state_clears_runtime_targets(self):
        state = RuntimeState(firing=True, last_aim_base=(10, 20), last_capture_seq=7)

        state.reset_tracking_state()

        self.assertFalse(state.firing)
        self.assertIsNone(state.last_aim_base)
        self.assertEqual(state.last_capture_seq, -1)

    def test_update_firing_reports_transitions(self):
        state = RuntimeState()

        self.assertEqual(state.update_firing(True), "started")
        self.assertTrue(state.firing)
        self.assertEqual(state.update_firing(True), "unchanged")
        self.assertEqual(state.update_firing(False), "stopped")
        self.assertFalse(state.firing)


class FakeAimCalculator:
    def __init__(self, result):
        self.result = result

    def calculate(self, target, roi_left, roi_top):
        return self.result


class RuntimePipelineTest(unittest.TestCase):
    def test_inactive_pipeline_returns_empty_control(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )

        result = pipeline.process_detection(
            active=False,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertIsNone(result.control.target)
        self.assertFalse(result.control.has_measurement)

    def test_active_fresh_detection_returns_control_target(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )

        result = pipeline.process_detection(
            active=True,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertEqual(result.control.target, (100, 100))
        self.assertTrue(result.control.has_measurement)

    def test_current_control_reuses_last_target_without_measurement(self):
        pipeline = RuntimePipeline(
            config=object(),
            aim_calculator=FakeAimCalculator((100, 100)),
            tracker=None,
        )
        pipeline.state.last_aim_base = (120, 130)

        control = pipeline.current_control(active=True, crosshair=(50, 50))

        self.assertEqual(control.target, (120, 130))
        self.assertFalse(control.has_measurement)
        self.assertTrue(control.active)


if __name__ == "__main__":
    unittest.main()
