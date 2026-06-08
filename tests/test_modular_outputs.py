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


if __name__ == "__main__":
    unittest.main()
