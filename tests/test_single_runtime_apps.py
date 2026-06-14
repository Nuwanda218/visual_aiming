import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.app.realtime import run_realtime
from visual_aiming.config.schema import ModularConfig


class Source:
    def __init__(self):
        self.frames = ["frame"]

    def read(self):
        return self.frames.pop(0) if self.frames else None


class Pipeline:
    def __init__(self):
        self.frames = []

    def tick(self, frame, now=None):
        self.frames.append(frame)
        return {"frame": frame}


class SingleRuntimeAppsTests(unittest.TestCase):
    def test_realtime_uses_same_runner_contract(self):
        pipeline = Pipeline()
        results = run_realtime(ModularConfig(), frame_source=Source(), pipeline=pipeline, max_frames=1)

        self.assertEqual(results, [{"frame": "frame"}])
        self.assertEqual(pipeline.frames, ["frame"])


if __name__ == "__main__":
    unittest.main()
