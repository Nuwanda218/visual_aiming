import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import DetectorConfig, FrameSourceConfig
from visual_aiming.core.schemas import FramePacket, RuntimeMode


class LegacyDetectedTarget:
    def __init__(self):
        self.bbox = (1, 2, 3, 4)
        self.confidence = 0.9
        self.class_id = 0
        self.class_name = "head"


class FakeLegacyDetector:
    last_result_fresh = True

    def detect(self, frame, config, roi_center=None, firing=False):
        self.called_with = (frame, config, roi_center, firing)
        return LegacyDetectedTarget()

    def preload(self, config, frame_shape):
        self.preloaded_with = (config, frame_shape)


class AdapterTest(unittest.TestCase):
    def test_ultralytics_adapter_normalizes_legacy_detector_result(self):
        from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector

        legacy = FakeLegacyDetector()
        adapter = UltralyticsYoloDetector(DetectorConfig(), legacy_detector=legacy)
        frame = FramePacket(
            frame=np.zeros((10, 20, 3), dtype=np.uint8),
            timestamp=1.0,
            sequence=5,
            roi_offset=(0, 0),
            roi_size=(20, 10),
            crosshair=(10, 5),
            source="unit",
            mode=RuntimeMode(active=True, firing=True),
        )

        packet = adapter.detect(frame)

        self.assertEqual(packet.sequence, 5)
        self.assertEqual(packet.detections[0].bbox, (1, 2, 3, 4))
        self.assertTrue(packet.fresh)
        self.assertEqual(legacy.called_with[2], (10, 5))
        self.assertTrue(legacy.called_with[3])

    def test_ultralytics_adapter_delegates_warmup_to_legacy_detector(self):
        from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector

        legacy = FakeLegacyDetector()
        adapter = UltralyticsYoloDetector(DetectorConfig(), legacy_detector=legacy)

        adapter.warmup((315, 410, 3))

        config, frame_shape = legacy.preloaded_with
        self.assertEqual(frame_shape, (315, 410, 3))
        self.assertEqual(config.yolo_imgsz, DetectorConfig().imgsz)

    def test_array_frame_source_emits_frame_packets_for_replay_tests(self):
        from visual_aiming.adapters.frame_sources.video_file import ArrayFrameSource

        frames = [np.zeros((4, 6, 3), dtype=np.uint8), np.ones((4, 6, 3), dtype=np.uint8)]
        source = ArrayFrameSource(frames, fps=20.0, roi_offset=(10, 20), crosshair=(13, 22), source="array")

        first = source.read()
        second = source.read()
        third = source.read()

        self.assertEqual(first.sequence, 0)
        self.assertEqual(first.timestamp, 0.0)
        self.assertEqual(second.sequence, 1)
        self.assertEqual(second.timestamp, 0.05)
        self.assertIsNone(third)

    def test_screen_frame_source_wraps_grabber(self):
        from visual_aiming.adapters.frame_sources.screen_capture import ScreenFrameSource

        calls = []
        def grabber():
            calls.append(True)
            return np.zeros((4, 6, 3), dtype=np.uint8)

        source = ScreenFrameSource(
            FrameSourceConfig(roi_size=(6, 4)),
            roi_offset=(10, 20),
            crosshair=(13, 22),
            grabber=grabber,
            clock=lambda: 12.5,
        )

        packet = source.read()

        self.assertEqual(packet.sequence, 0)
        self.assertEqual(packet.timestamp, 12.5)
        self.assertEqual(packet.roi_offset, (10, 20))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
