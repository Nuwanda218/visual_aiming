import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.interaction.cli import _build_config, load_config_file, parse_args


class ParseArgsTests(unittest.TestCase):
    def test_parses_video(self):
        args = parse_args(["--video", "sample.mp4"])
        self.assertEqual(args.video, "sample.mp4")

    def test_defaults(self):
        args = parse_args(["--video", "v.mp4"])
        self.assertEqual(args.output, "null")
        self.assertEqual(args.model, "models/best.pt")
        self.assertEqual(args.max_frames, 0)
        self.assertEqual(args.config, "config.v2.json")
        self.assertFalse(args.realtime)

    def test_all_video_options(self):
        args = parse_args(["--video", "v.mp4", "--model", "m.pt", "--output", "log", "--max-frames", "50"])
        self.assertEqual(args.model, "m.pt")
        self.assertEqual(args.output, "log")
        self.assertEqual(args.max_frames, 50)

    def test_realtime_mode(self):
        args = parse_args(["--realtime", "--output", "mouse"])
        self.assertTrue(args.realtime)
        self.assertEqual(args.output, "mouse")

    def test_config_tune_mode(self):
        args = parse_args(["--tune", "config", "--video", "v.mp4"])
        self.assertEqual(args.tune, "config")


class ConfigLoadTests(unittest.TestCase):
    def test_load_config_file_returns_nested_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.v2.json"
            path.write_text(json.dumps({"control": {"speed": 240.0}}), encoding="utf-8")

            data = load_config_file(str(path))

        self.assertEqual(data["control"]["speed"], 240.0)

    def test_build_config_reads_nested_v2_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.v2.json"
            path.write_text(json.dumps({
                "perception": {"model_path": "from-file.pt", "confidence": 0.7},
                "capture": {"image_width": 320, "image_height": 240},
                "control": {"speed": 240.0, "acceleration": 0.6},
                "tracker": {"match_distance_ratio": 0.5},
            }), encoding="utf-8")
            args = parse_args(["--video", "v.mp4", "--config", str(path)])

            config = _build_config(args)

        self.assertEqual(config.perception.model_path, "from-file.pt")
        self.assertEqual(config.perception.confidence, 0.7)
        self.assertEqual(config.capture.image_width, 320)
        self.assertEqual(config.capture.image_height, 240)
        self.assertEqual(config.control.speed, 240.0)
        self.assertEqual(config.control.acceleration, 0.6)
        self.assertEqual(config.tracker.match_distance_ratio, 0.5)

    def test_model_argument_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.v2.json"
            path.write_text(json.dumps({"perception": {"model_path": "from-file.pt"}}), encoding="utf-8")
            args = parse_args(["--video", "v.mp4", "--config", str(path), "--model", "cli.pt"])

            config = _build_config(args)

        self.assertEqual(config.perception.model_path, "cli.pt")


if __name__ == "__main__":
    unittest.main()
