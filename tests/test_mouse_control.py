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
    mouse_diagnostics_enabled = True


class MouseControllerTest(unittest.TestCase):
    def test_relative_controller_uses_injected_sender(self):
        from visual_aiming.actions.mouse_control import MouseController

        sent = []
        controller = MouseController(Config(), move_sender=lambda dx, dy: sent.append((dx, dy)))
        controller.printer = None

        controller.move_towards(target_pos=(150, 100), crosshair_pos=(100, 100), has_measurement=True, active=True)

        self.assertEqual(sent, [(21, 0)])

    def test_diagnostics_counts_sends_and_blocked_reasons(self):
        from visual_aiming.actions.mouse_control import MouseController

        sent = []
        controller = MouseController(Config(), move_sender=lambda dx, dy: sent.append((dx, dy)))
        controller.printer = None

        controller.move_towards(target_pos=(150, 100), crosshair_pos=(100, 100), has_measurement=True, active=True)
        controller.move_towards(target_pos=(100, 100), crosshair_pos=(100, 100), has_measurement=True, active=True)
        controller.move_towards(target_pos=(150, 100), crosshair_pos=None, has_measurement=True, active=True)
        controller.move_towards(target_pos=(150, 100), crosshair_pos=(100, 100), has_measurement=True, active=False)

        diagnostics = controller.diagnostics_snapshot()

        self.assertEqual(diagnostics["sent_moves"], 1)
        self.assertEqual(diagnostics["zero_outputs"], 1)
        self.assertEqual(diagnostics["blocked"]["missing_crosshair"], 1)
        self.assertEqual(diagnostics["blocked"]["inactive"], 1)
        self.assertGreater(diagnostics["last_command_magnitude"], 0.0)

    def test_diagnostics_prints_summary_after_send(self):
        from visual_aiming.actions.mouse_control import MouseController

        class FakePrinter:
            def __init__(self):
                self.calls = []

            def print(self, key, message):
                self.calls.append((key, message))

        fake_printer = FakePrinter()
        controller = MouseController(Config(), move_sender=lambda _dx, _dy: None)
        controller.printer = fake_printer

        controller.move_towards(target_pos=(150, 100), crosshair_pos=(100, 100), has_measurement=True, active=True)

        self.assertTrue(any(key == "mouse_diagnostics" for key, _message in fake_printer.calls))
        self.assertTrue(any("sent=1" in message and "last=(21,0)" in message for _key, message in fake_printer.calls))


if __name__ == "__main__":
    unittest.main()
