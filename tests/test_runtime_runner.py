import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.runtime_runner import RuntimeObserver, RuntimeRunner


class FakeFrameSource:
    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False

    def read(self):
        return self.frames.pop(0) if self.frames else None

    def close(self):
        self.closed = True


class FakePipeline:
    def __init__(self):
        self.frames = []

    def tick(self, frame, now=None):
        self.frames.append((frame, now))
        return {"frame": frame, "now": now}


class FakeObserver(RuntimeObserver):
    def __init__(self):
        self.events = []
        self.closed = False

    def on_tick(self, frame, result):
        self.events.append((frame, result))

    def close(self):
        self.closed = True


class RuntimeRunnerTests(unittest.TestCase):
    def test_run_until_source_returns_none(self):
        source = FakeFrameSource(["a", "b"])
        pipeline = FakePipeline()
        observer = FakeObserver()
        runner = RuntimeRunner(source, pipeline, observers=[observer], clock=lambda: 10.0)

        results = runner.run()

        self.assertEqual(results, [{"frame": "a", "now": 10.0}, {"frame": "b", "now": 10.0}])
        self.assertEqual(pipeline.frames, [("a", 10.0), ("b", 10.0)])
        self.assertEqual(observer.events, [("a", results[0]), ("b", results[1])])

    def test_run_once_returns_false_without_frame(self):
        source = FakeFrameSource([])
        pipeline = FakePipeline()
        runner = RuntimeRunner(source, pipeline, clock=lambda: 1.0)

        has_frame, result = runner.run_once()

        self.assertFalse(has_frame)
        self.assertIsNone(result)
        self.assertEqual(pipeline.frames, [])

    def test_run_once_passes_none_time_when_clock_is_not_configured(self):
        source = FakeFrameSource(["frame"])
        pipeline = FakePipeline()
        runner = RuntimeRunner(source, pipeline)

        has_frame, result = runner.run_once()

        self.assertTrue(has_frame)
        self.assertEqual(result, {"frame": "frame", "now": None})
        self.assertEqual(pipeline.frames, [("frame", None)])

    def test_close_closes_source_and_observer(self):
        source = FakeFrameSource([])
        pipeline = FakePipeline()
        observer = FakeObserver()
        runner = RuntimeRunner(source, pipeline, observers=[observer])

        runner.close()

        self.assertTrue(source.closed)
        self.assertTrue(observer.closed)


if __name__ == "__main__":
    unittest.main()
