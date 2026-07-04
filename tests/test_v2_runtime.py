import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Detection, Frame
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.capture.sources import MemoryCapture
from visual_aiming_v2.perception.detectors import StaticDetector
from visual_aiming_v2.actuation.targeting import Actuator
from visual_aiming_v2.actuation.outputs import LogOutput
from visual_aiming_v2.runtime.pipeline import Pipeline


class PipelineTests(unittest.TestCase):
    def _make_pipeline(self, detections, image_size=200):
        config = Config(image_width=image_size, image_height=image_size)
        return Pipeline(
            detector=StaticDetector(detections),
            actuator=Actuator(config),
            output=LogOutput(),
        )

    def test_noop_when_no_detections(self):
        pipeline = self._make_pipeline([])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        result = pipeline.tick(frame)

        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "no_target")

    def test_selects_nearest_and_produces_relative_command(self):
        far = Detection(x=200, y=200, w=20, h=20, confidence=0.9)
        near = Detection(x=92, y=82, w=20, h=20, confidence=0.8)
        pipeline = self._make_pipeline([far, near])
        frame = Frame(image="img", sequence=1, timestamp=0.1)

        result = pipeline.tick(frame)

        self.assertEqual(result.command.mode, "relative")
        self.assertEqual(result.command.dx, 2)
        self.assertEqual(result.command.dy, -8)

    def test_output_receives_command(self):
        det = Detection(x=110, y=95, w=10, h=10, confidence=0.9)
        pipeline = self._make_pipeline([det])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        pipeline.tick(frame)

        self.assertEqual(len(pipeline.output.commands), 1)

    def test_tick_result_contains_detections(self):
        d1 = Detection(x=10, y=10, w=10, h=10, confidence=0.5)
        d2 = Detection(x=50, y=50, w=10, h=10, confidence=0.6)
        pipeline = self._make_pipeline([d1, d2])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        result = pipeline.tick(frame)

        self.assertEqual(len(result.detections), 2)


from visual_aiming_v2.runtime.runner import run


class RunnerTests(unittest.TestCase):
    def test_processes_all_frames(self):
        frames = [
            Frame(image="a", sequence=0, timestamp=0.0),
            Frame(image="b", sequence=1, timestamp=0.1),
            Frame(image="c", sequence=2, timestamp=0.2),
        ]
        config = Config(image_width=200, image_height=200)
        output = LogOutput()

        results = run(
            capture=MemoryCapture(frames),
            detector=StaticDetector([Detection(x=10, y=10, w=10, h=10, confidence=0.9)]),
            actuator=Actuator(config),
            output=output,
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(len(output.commands), 3)

    def test_max_frames_limits_processing(self):
        frames = [Frame(image=f"f{i}", sequence=i, timestamp=i * 0.1) for i in range(10)]
        config = Config(image_width=200, image_height=200)

        results = run(
            capture=MemoryCapture(frames),
            detector=StaticDetector([]),
            actuator=Actuator(config),
            output=LogOutput(),
            max_frames=3,
        )

        self.assertEqual(len(results), 3)

    def test_closes_capture_and_output(self):
        close_log = []
        capture = MemoryCapture([])
        output = LogOutput()
        orig_cap_close = capture.close
        orig_out_close = output.close
        capture.close = lambda: (close_log.append("capture"), orig_cap_close())
        output.close = lambda: (close_log.append("output"), orig_out_close())
        config = Config(image_width=200, image_height=200)

        run(capture=capture, detector=StaticDetector([]), actuator=Actuator(config), output=output)

        self.assertIn("capture", close_log)
        self.assertIn("output", close_log)


if __name__ == "__main__":
    unittest.main()
