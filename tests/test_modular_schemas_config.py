import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class ModularSchemasTest(unittest.TestCase):
    def test_frame_packet_carries_roi_and_crosshair(self):
        from visual_aiming.core.schemas import FramePacket, RuntimeMode

        frame = np.zeros((4, 6, 3), dtype=np.uint8)
        packet = FramePacket(
            frame=frame,
            timestamp=1.25,
            sequence=7,
            roi_offset=(10, 20),
            roi_size=(6, 4),
            crosshair=(13, 22),
            source="unit",
            mode=RuntimeMode(active=True, firing=False),
        )

        self.assertEqual(packet.sequence, 7)
        self.assertEqual(packet.roi_offset, (10, 20))
        self.assertEqual(packet.crosshair, (13, 22))
        self.assertTrue(packet.mode.active)
        self.assertFalse(packet.mode.firing)

    def test_pipeline_tick_result_preserves_intermediate_states(self):
        from visual_aiming.core.schemas import (
            AimMeasurement,
            ControlCommand,
            Detection,
            DetectionPacket,
            PipelineTickResult,
            PredictedAim,
            RuntimeMode,
            SelectedTarget,
        )

        detection = Detection(bbox=(1, 2, 10, 20), confidence=0.9, class_id=0, class_name="head")
        detections = DetectionPacket(sequence=1, detections=[detection], latency_ms=3.5, detector_name="fake", fresh=True)
        selected = SelectedTarget(detection=detection, score=0.1, score_parts={"distance": 0.1}, switched=False)
        aim = AimMeasurement(point=(100, 120), crosshair=(90, 120), error=(10.0, 0.0), valid=True)
        predicted = PredictedAim(point=(101, 120), velocity=(5.0, 0.0), confidence=0.8, state="tracking")
        command = ControlCommand(dx=4, dy=0, mode="relative", limited=False, reason="tracking")

        result = PipelineTickResult(
            sequence=1,
            timestamp=2.0,
            mode=RuntimeMode(active=True, firing=True),
            detections=detections,
            selected=selected,
            aim=aim,
            predicted=predicted,
            command=command,
            output_backend="null",
            pipeline_latency_ms=1.2,
        )

        self.assertEqual(result.detections.detections[0].class_name, "head")
        self.assertEqual(result.selected.score_parts["distance"], 0.1)
        self.assertEqual(result.command.dx, 4)
        self.assertEqual(result.mode.firing, True)

    def test_ports_are_importable(self):
        from visual_aiming.ports.detector import Detector
        from visual_aiming.ports.diagnostics import DiagnosticsSink
        from visual_aiming.ports.frame_source import FrameSource
        from visual_aiming.ports.output import OutputBackend

        self.assertIsNotNone(Detector)
        self.assertIsNotNone(DiagnosticsSink)
        self.assertIsNotNone(FrameSource)
        self.assertIsNotNone(OutputBackend)


class ModularConfigTest(unittest.TestCase):
    def test_default_config_uses_safe_output(self):
        from visual_aiming.config.schema import ModularConfig

        config = ModularConfig()

        self.assertEqual(config.output.backend, "null")
        self.assertFalse(config.output.enable_real_mouse)
        self.assertEqual(config.detector.backend, "ultralytics")
        self.assertEqual(config.frame.roi_size, (410, 315))

    def test_legacy_flat_config_maps_to_grouped_config(self):
        from visual_aiming.config.loader import modular_config_from_mapping

        config = modular_config_from_mapping({
            "roi_width": 500,
            "roi_height": 300,
            "detect_fps": 20,
            "yolo_model_path": "models/custom.pt",
            "yolo_conf_threshold": 0.42,
            "yolo_head_class_id": 2,
            "yolo_person_class_id": 3,
            "aim_target_preference": 0.75,
            "head_bias": 0.2,
            "tracker_prediction_time": 0.05,
            "servo_deadzone": 3.0,
            "servo_step_limit": 12,
            "mouse_absolute_mode_enabled": True,
        })

        self.assertEqual(config.frame.roi_size, (500, 300))
        self.assertEqual(config.runtime.detect_fps, 20.0)
        self.assertEqual(config.detector.model_path, "models/custom.pt")
        self.assertEqual(config.detector.confidence, 0.42)
        self.assertEqual(config.target_selection.head_class_id, 2)
        self.assertEqual(config.target_selection.person_class_id, 3)
        self.assertEqual(config.aim.target_preference, 0.75)
        self.assertEqual(config.aim.head_bias, 0.2)
        self.assertEqual(config.prediction.lead_time, 0.05)
        self.assertEqual(config.control.deadzone, 3.0)
        self.assertEqual(config.control.max_step, 12)
        self.assertEqual(config.output.command_mode, "absolute")
        self.assertEqual(config.output.backend, "null")


if __name__ == "__main__":
    unittest.main()
