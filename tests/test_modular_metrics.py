import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
TESTS_ROOT = PROJECT_ROOT / "tests"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_modular_outputs import make_result
from visual_aiming.core.schemas import ControlCommand


class DiagnosticsMetricsTest(unittest.TestCase):
    def test_jsonl_diagnostics_writes_records_and_summary(self):
        from visual_aiming.core.metrics import JsonlDiagnostics

        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "run.jsonl"
            summary_path = Path(tmp) / "summary.json"
            diagnostics = JsonlDiagnostics(jsonl, summary_path)
            diagnostics.write(make_result(ControlCommand(dx=3, dy=4, mode="relative", reason="tracking")))
            diagnostics.write(make_result(ControlCommand(dx=0, dy=0, mode="none", reason="deadzone")))
            diagnostics.close()

            records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["command"]["dx"], 3)
            self.assertEqual(summary["samples"], 2)
            self.assertEqual(summary["max_command_magnitude"], 5.0)
            self.assertEqual(summary["noop_commands"], 1)

    def test_jsonl_diagnostics_writes_strict_json_without_non_finite_numbers(self):
        from visual_aiming.core.metrics import JsonlDiagnostics
        from visual_aiming.core.schemas import RuntimeTelemetry

        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "run.jsonl"
            diagnostics = JsonlDiagnostics(jsonl)
            result = make_result()
            result.telemetry = RuntimeTelemetry(wait_ms=11.0, frame_work_ms=23.0, display_fps=41.5, source_fps=60.0, active=True)
            diagnostics.write(result)
            diagnostics.close()

            payload = jsonl.read_text(encoding="utf-8")
            self.assertNotIn("Infinity", payload)
            self.assertNotIn("NaN", payload)

            def reject_constant(value):
                raise ValueError(f"non-standard JSON constant: {value}")

            record = json.loads(payload, parse_constant=reject_constant)
            self.assertIsNone(record["selected"]["score"])
            self.assertIn("latency_breakdown", record)
            self.assertEqual(record["latency_breakdown"]["total_ms"], 0.0)
            self.assertEqual(record["telemetry"]["wait_ms"], 11.0)
            self.assertEqual(record["telemetry"]["frame_work_ms"], 23.0)
            self.assertEqual(record["telemetry"]["display_fps"], 41.5)


if __name__ == "__main__":
    unittest.main()
