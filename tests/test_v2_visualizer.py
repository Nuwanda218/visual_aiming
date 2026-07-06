import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.interaction.visualizer import Visualizer
from visual_aiming_v2.shared.schemas import Command, Detection, Frame, TickResult


class VisualizerTests(unittest.TestCase):
    def test_draws_smoothed_aim_from_result_not_command_delta(self):
        frame = Frame(image=np.zeros((120, 120, 3), dtype=np.uint8), sequence=1, timestamp=0.0)
        selected = Detection(x=40, y=40, w=20, h=20, confidence=0.9, label="head")
        result = TickResult(
            frame=frame,
            detections=[selected],
            selected=selected,
            command=Command(dx=3, dy=4, mode="relative", reason="tracking"),
            raw_aim=(50, 48),
            smoothed_aim=(52, 49),
        )
        circles = []

        with patch("cv2.namedWindow"), patch("cv2.setWindowProperty"), patch("cv2.imshow"), patch("cv2.waitKeyEx", return_value=-1), patch("cv2.getWindowProperty", return_value=1), patch("cv2.circle", side_effect=lambda _img, center, *_args, **_kwargs: circles.append(center)):
            visualizer = Visualizer(crosshair=(60, 60), total_frames=0)
            keep_running = visualizer.update(frame.image, result)

        self.assertTrue(keep_running)
        self.assertIn((52, 49), circles)
        self.assertNotIn((63, 64), circles)


if __name__ == "__main__":
    unittest.main()
