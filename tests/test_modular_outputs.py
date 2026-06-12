import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.schemas import (
    AimMeasurement,
    ControlCommand,
    DetectionPacket,
    PipelineTickResult,
    PredictedAim,
    RuntimeMode,
    SelectedTarget,
)


def make_result(command=None):
    command = command or ControlCommand(dx=3, dy=4, mode="relative", reason="tracking")
    return PipelineTickResult(
        sequence=1,
        timestamp=1.0,
        mode=RuntimeMode(active=True, firing=False),
        detections=DetectionPacket(sequence=1, detections=[], latency_ms=0.0, detector_name="fake"),
        selected=SelectedTarget(detection=None, score=float("inf"), reason="no_detections"),
        aim=AimMeasurement(point=None, crosshair=(100, 100), error=(0.0, 0.0), valid=False),
        predicted=PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost"),
        command=command,
        output_backend="test",
        pipeline_latency_ms=0.0,
    )


class OutputBackendTest(unittest.TestCase):
    def test_null_output_records_nothing_and_does_not_raise(self):
        from visual_aiming.adapters.outputs.null_output import NullOutput

        output = NullOutput()
        output.apply(ControlCommand(dx=10, dy=10, mode="relative"), make_result())
        output.close()

        self.assertEqual(output.name, "null")

    def test_log_output_keeps_commands_in_memory(self):
        from visual_aiming.adapters.outputs.log_output import LogOutput

        output = LogOutput()
        result = make_result(ControlCommand(dx=5, dy=-2, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(len(output.commands), 1)
        self.assertEqual(output.commands[0].dx, 5)
        self.assertEqual(output.commands[0].dy, -2)

    def test_win_mouse_requires_explicit_enable(self):
        from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput

        calls = []
        output = WinMouseOutput(enable_real_mouse=False, sender=lambda dx, dy: calls.append((dx, dy)))
        result = make_result(ControlCommand(dx=7, dy=8, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(calls, [])

    def test_win_mouse_sends_when_enabled(self):
        from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput

        calls = []
        output = WinMouseOutput(enable_real_mouse=True, sender=lambda dx, dy: calls.append((dx, dy)))
        result = make_result(ControlCommand(dx=7, dy=8, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(calls, [(7, 8)])

    def test_send_relative_move_offsets_current_cursor_position(self):
        from visual_aiming.adapters.outputs.win_mouse import send_relative_move

        class FakePoint:
            x = 100
            y = 200

        class FakeUser32:
            def __init__(self):
                self.positions = []

            def GetCursorPos(self, point_ref):
                point_ref._obj.x = FakePoint.x
                point_ref._obj.y = FakePoint.y
                return 1

            def SetCursorPos(self, x, y):
                self.positions.append((x, y))
                return 1

        fake_user32 = FakeUser32()

        send_relative_move(7, -3, user32=fake_user32)

        self.assertEqual(fake_user32.positions, [(107, 197)])

    def test_sendinput_relative_move_sends_mouse_input_delta(self):
        import ctypes

        from visual_aiming.adapters.outputs.win_mouse import INPUT, MOUSEEVENTF_MOVE, send_relative_move_sendinput

        class FakeUser32:
            def __init__(self):
                self.calls = []

            def SendInput(self, count, inputs, size):
                record = inputs[0]
                mouse = record.value.mi
                self.calls.append((count, record.type, mouse.dx, mouse.dy, mouse.dwFlags, size))
                return count

        fake_user32 = FakeUser32()

        send_relative_move_sendinput(7, -3, user32=fake_user32)

        self.assertEqual(fake_user32.calls[0][:5], (1, 0, 7, -3, MOUSEEVENTF_MOVE))
        self.assertEqual(fake_user32.calls[0][5], ctypes.sizeof(INPUT))

    def test_sendinput_input_struct_matches_windows_layout_size(self):
        import ctypes

        from visual_aiming.adapters.outputs.win_mouse import INPUT

        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28

        self.assertEqual(ctypes.sizeof(INPUT), expected)

    def test_create_mouse_sender_selects_setcursor_or_sendinput(self):
        from visual_aiming.adapters.outputs.win_mouse import (
            create_mouse_sender,
            send_relative_move_setcursor,
            send_relative_move_sendinput,
        )

        self.assertIs(create_mouse_sender("set_cursor"), send_relative_move_setcursor)
        self.assertIs(create_mouse_sender("sendinput"), send_relative_move_sendinput)

        with self.assertRaises(ValueError):
            create_mouse_sender("unknown")

    def test_output_factory_selects_configured_mouse_sender(self):
        from visual_aiming.adapters.outputs import factory
        from visual_aiming.config.schema import OutputConfig

        calls = []

        def fake_create_sender(method):
            calls.append(method)
            return lambda _dx, _dy: None

        original = factory.create_mouse_sender
        factory.create_mouse_sender = fake_create_sender
        try:
            output = factory.create_output_backend(
                OutputConfig(backend="win_mouse", enable_real_mouse=True, mouse_method="sendinput")
            )
        finally:
            factory.create_mouse_sender = original

        self.assertEqual(output.name, "win_mouse")
        self.assertEqual(calls, ["sendinput"])


if __name__ == "__main__":
    unittest.main()
