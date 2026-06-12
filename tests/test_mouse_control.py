import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class Config:
    servo_thread_enabled = False
    servo_deadzone = 0.0
    fps_speed_gain = 100.0
    fps_min_speed = 0.0
    fps_max_speed = 10000.0
    fps_decel_radius = 1.0
    fps_near_speed_scale = 1.0
    fps_acceleration = 1000.0
    fps_brake_radius = 1.0
    fps_brake = 0.0
    servo_output_gain = 1.0
    servo_step_limit = 100
    fps_jitter_angle = 0.0
    fps_velocity_feedback = 0.0
    servo_overshoot_guard_enabled = False
    servo_output_to_error_gain = 0.0
    servo_output_to_velocity_gain = 0.0
    mouse_absolute_mode_enabled = False


class MouseControllerTest(unittest.TestCase):
    def test_relative_controller_uses_injected_sender(self):
        from visual_aiming.actions.mouse_control import MouseController

        sent = []
        controller = MouseController(Config(), move_sender=lambda dx, dy: sent.append((dx, dy)))
        controller.printer = None

        controller.move_towards(target_pos=(150, 100), crosshair_pos=(100, 100), has_measurement=True, active=True)

        self.assertEqual(sent, [(21, 0)])


if __name__ == "__main__":
    unittest.main()
