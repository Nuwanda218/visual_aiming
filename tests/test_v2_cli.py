import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.interaction.cli import parse_args


class ParseArgsTests(unittest.TestCase):
    def test_parses_video(self):
        args = parse_args(["--video", "sample.mp4"])
        self.assertEqual(args.video, "sample.mp4")

    def test_defaults(self):
        args = parse_args(["--video", "v.mp4"])
        self.assertEqual(args.output, "null")
        self.assertEqual(args.model, "models/best.pt")
        self.assertEqual(args.max_frames, 0)
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


if __name__ == "__main__":
    unittest.main()
