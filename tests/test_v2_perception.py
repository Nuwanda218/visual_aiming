import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Detection
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.perception.detectors import StaticDetector, YoloDetector


class StaticDetectorTests(unittest.TestCase):
    def test_returns_configured_detections(self):
        det = Detection(x=10, y=20, w=30, h=40, confidence=0.9, label="head")
        detector = StaticDetector([det])

        result = detector.detect("fake_image")

        self.assertEqual(result, [det])

    def test_returns_empty_when_none_configured(self):
        detector = StaticDetector([])

        self.assertEqual(detector.detect("fake_image"), [])


class YoloDetectorTests(unittest.TestCase):
    def test_accepts_config_and_lazy_loads(self):
        config = Config(model_path="nonexistent.pt")
        detector = YoloDetector(config)

        self.assertIsNone(detector._model)

    def test_detect_raises_when_model_not_found(self):
        config = Config(model_path="nonexistent.pt")
        detector = YoloDetector(config)

        with self.assertRaises(Exception):
            detector.detect("fake_image")


if __name__ == "__main__":
    unittest.main()
