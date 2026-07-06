import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.interaction.tuner import V2ConfigTunerState
from visual_aiming_v2.shared.config import Config


class V2ConfigTunerStateTests(unittest.TestCase):
    def test_updates_nested_config_values(self):
        state = V2ConfigTunerState(Config())

        state.set_value("control.speed", 240.0)
        state.set_value("tracker.lost_frame_grace", 4)
        state.set_value("smoothing.enabled", False)

        self.assertEqual(state.config.control.speed, 240.0)
        self.assertEqual(state.config.tracker.lost_frame_grace, 4)
        self.assertFalse(state.config.smoothing.enabled)

    def test_save_writes_nested_v2_json(self):
        state = V2ConfigTunerState(Config())
        state.set_value("capture.image_width", 360)
        state.set_value("control.near_speed_scale", 0.4)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.v2.json"
            state.save(path)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["capture"]["image_width"], 360)
        self.assertEqual(data["control"]["near_speed_scale"], 0.4)
        self.assertIn("tracker", data)
        self.assertNotIn("control_speed", data)

    def test_reset_restores_original_values(self):
        config = Config()
        config.control.speed = 180.0
        state = V2ConfigTunerState(config)

        state.set_value("control.speed", 300.0)
        state.reset()

        self.assertEqual(state.config.control.speed, 180.0)


if __name__ == "__main__":
    unittest.main()
