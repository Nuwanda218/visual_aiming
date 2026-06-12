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

        self.assertEqual(names[:2], ["常用调参", "输出测试"])
        self.assertEqual(names, ["常用调参", "输出测试", "高级-性能模型", "高级-控制行为", "高级-预测开火"])

    def test_common_tuning_panel_stays_small_and_actionable(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        common_items = dict(sections)["常用调参"]
        common_keys = {item.key for item in common_items}

        self.assertLessEqual(len(common_items), 12)
        self.assertEqual(
            common_keys,
            {
                "capture_fps",
                "detect_fps",
                "firing_detect_fps",
                "yolo_conf_threshold",
                "yolo_imgsz",
                "servo_output_gain",
                "servo_step_limit",
                "servo_deadzone",
                "target_stickiness",
                "head_bias",
            },
        )

    def test_output_test_section_exposes_mouse_method(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        output_keys = {item.key for item in dict(sections)["输出测试"]}

        self.assertIn("mouse_method", output_keys)
        self.assertIn("mouse_absolute_mode_enabled", output_keys)

    def test_advanced_tuning_keys_are_still_available(self):
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
            "tracker_prediction_time",
            "fps_acceleration",
            "firing_anchor_hold_ms",
        ]:
            self.assertIn(key, keys)


if __name__ == "__main__":
    unittest.main()
