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

        self.assertLessEqual(len(common_items), 8)
        self.assertEqual(
            common_keys,
            {
                "yolo_conf_threshold",
                "yolo_imgsz",
                "servo_deadzone",
                "target_stickiness",
                "head_bias",
                "mouse_diagnostics_enabled",
            },
        )

    def test_common_tuning_keeps_only_high_value_controls(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        common_items = dict(sections)["常用调参"]
        keys = [item.key for item in common_items]

        self.assertLessEqual(len(keys), 8)
        self.assertIn("yolo_conf_threshold", keys)
        self.assertIn("head_bias", keys)
        self.assertIn("servo_deadzone", keys)
        self.assertIn("mouse_diagnostics_enabled", keys)
        self.assertIn("target_stickiness", keys)
        self.assertNotIn("tracker_prediction_time", keys)
        self.assertNotIn("target_switch_margin", keys)

    def test_output_test_section_exposes_mouse_method(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        output_keys = {item.key for item in dict(sections)["输出测试"]}

        self.assertIn("mouse_method", output_keys)
        self.assertIn("mouse_diagnostics_enabled", output_keys)
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
