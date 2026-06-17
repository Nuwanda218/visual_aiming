import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ReplayRegressionTest(unittest.TestCase):
    def test_load_manifest_reads_video_cases(self):
        from scripts.replay_regression import load_manifest

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "cases": [
                    {
                        "name": "sample",
                        "video": "data/sample.mp4",
                        "min_visible_detection_rate": 80.0,
                        "max_empty_false_positive_rate": 5.0,
                        "max_target_switches": 12,
                    }
                ]
            }), encoding="utf-8")

            cases = load_manifest(path)

        self.assertEqual(cases[0].name, "sample")
        self.assertEqual(cases[0].video, Path("data/sample.mp4"))
        self.assertEqual(cases[0].max_target_switches, 12)

    def test_run_case_replays_and_evaluates_generated_log(self):
        from scripts.replay_regression import ReplayCase, run_case

        calls = []

        def fake_replay(video, diagnostics_path):
            calls.append(("replay", video, diagnostics_path))
            diagnostics_path.write_text(
                json.dumps({"target_visible": True, "detections": [{"class_id": 0}], "selected": {"switched": False}}) + "\n",
                encoding="utf-8",
            )

        def fake_evaluate(path, min_visible_detection_rate, max_empty_false_positive_rate, max_target_switches):
            calls.append(("evaluate", path, min_visible_detection_rate, max_empty_false_positive_rate, max_target_switches))
            return type("Result", (), {"passed": True, "failures": []})()

        with tempfile.TemporaryDirectory() as tmp:
            case = ReplayCase(
                name="sample",
                video=Path("data/sample.mp4"),
                min_visible_detection_rate=80.0,
                max_empty_false_positive_rate=5.0,
                max_target_switches=12,
            )
            result = run_case(case, Path(tmp), replay=fake_replay, evaluate=fake_evaluate)

        self.assertTrue(result.passed)
        self.assertEqual(calls[0][0], "replay")
        self.assertEqual(calls[0][1], Path("data/sample.mp4"))
        self.assertEqual(calls[1][0], "evaluate")
        self.assertEqual(calls[1][2:], (80.0, 5.0, 12))


if __name__ == "__main__":
    unittest.main()
