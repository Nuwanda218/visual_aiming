import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.schemas import Detection, DetectionPacket, FramePacket, RuntimeMode


class FakeDetector:
    name = "fake"

    def __init__(self, detections):
        self.detections = detections

    def detect(self, frame):
        return DetectionPacket(
            sequence=frame.sequence,
            detections=list(self.detections),
            latency_ms=0.5,
            detector_name=self.name,
            fresh=True,
        )


class FakeOutput:
    name = "fake_output"

    def __init__(self):
        self.applied = []

    def apply(self, command, result):
        self.applied.append((command, result))

    def close(self):
        return None


class ModularPipelineTest(unittest.TestCase):
    def make_frame(self, active=True, firing=False):
        return FramePacket(
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
            timestamp=1.0,
            sequence=1,
            roi_offset=(100, 200),
            roi_size=(100, 100),
            crosshair=(150, 250),
            source="unit",
            mode=RuntimeMode(active=active, firing=firing),
        )

    def test_inactive_tick_outputs_noop_without_detection(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        pipeline = ModularPipeline(ModularConfig(), FakeDetector([Detection((40, 40, 20, 20), 1.0, 0, "head")]), output)

        result = pipeline.tick(self.make_frame(active=False), now=1.0)

        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "inactive")
        self.assertEqual(len(output.applied), 1)
        self.assertEqual(result.detections.detections, [])

    def test_active_tick_detects_selects_aims_predicts_controls_and_outputs(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        config.aim.head_bias = 0.5
        config.control.deadzone = 0.0
        config.control.max_step = 6
        detection = Detection(bbox=(40, 40, 20, 20), confidence=1.0, class_id=0, class_name="head")
        pipeline = ModularPipeline(config, FakeDetector([detection]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.selected.detection.bbox, detection.bbox)
        self.assertEqual(result.aim.point, (150, 250))
        self.assertEqual(result.predicted.point, (150, 250))
        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "deadzone")
        self.assertEqual(len(output.applied), 1)

    def test_active_tick_with_offset_target_emits_relative_command(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        config.aim.head_bias = 0.5
        config.control.deadzone = 0.0
        config.control.max_step = 6
        config.control.speed_gain = 500.0
        config.control.near_speed_scale = 1.0
        config.runtime.poll_fps = 30.0
        detection = Detection(bbox=(50, 40, 20, 20), confidence=1.0, class_id=0, class_name="head")
        pipeline = ModularPipeline(config, FakeDetector([detection]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.command.mode, "relative")
        self.assertGreater(result.command.dx, 0)
        self.assertEqual(len(output.applied), 1)

    def test_lost_target_result_records_no_detection_reason(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        pipeline = ModularPipeline(config, FakeDetector([]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.selected.reason, "no_detections")
        self.assertIn(result.predicted.state, {"lost", "held"})
        self.assertEqual(result.command.reason, "no_target")


if __name__ == "__main__":
    unittest.main()
