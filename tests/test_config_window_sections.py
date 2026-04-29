import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.actions.config_window import ConfigWindow


class ConfigWindowSectionsTest(unittest.TestCase):
    def test_focused_sections_are_exposed_first(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        names = [name for name, _items in sections]

        self.assertEqual(names[:4], ["核心性能", "模型/GPU", "控制平滑", "目标行为"])

    def test_core_tuning_keys_are_available(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        keys = {
            item.key
            for _name, items in sections
            for item in items
        }

        for key in [
            "capture_fps",
            "detect_fps",
            "firing_detect_fps",
            "idle_detect_fps",
            "servo_loop_hz",
            "yolo_device",
            "yolo_half",
            "yolo_imgsz",
            "servo_output_gain",
            "target_stickiness",
        ]:
            self.assertIn(key, keys)


if __name__ == "__main__":
    unittest.main()
