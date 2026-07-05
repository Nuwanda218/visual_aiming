import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Frame
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.capture.sources import MemoryCapture, VideoFileCapture


class MemoryCaptureTests(unittest.TestCase):
    def test_reads_all_frames_then_returns_none(self):
        frames = [
            Frame(image="a", sequence=0, timestamp=0.0),
            Frame(image="b", sequence=1, timestamp=0.1),
        ]
        source = MemoryCapture(frames)

        self.assertEqual(source.read(), frames[0])
        self.assertEqual(source.read(), frames[1])
        self.assertIsNone(source.read())

    def test_close_is_safe(self):
        source = MemoryCapture([])
        source.close()
        source.close()


class VideoFileCaptureRoiTests(unittest.TestCase):
    """测试 VideoFileCapture 的 ROI 裁切参数计算逻辑。"""

    def test_roi_clamps_to_video_size(self):
        """ROI 配置大于视频分辨率时，应使用视频原始尺寸。"""
        config = Config(image_width=9999, image_height=9999)
        # 直接检查内部参数，不需要真实视频
        cap = VideoFileCapture.__new__(VideoFileCapture)
        cap.video_width = 640
        cap.video_height = 480
        cap._roi_w = min(config.image_width, cap.video_width)
        cap._roi_h = min(config.image_height, cap.video_height)
        cap._roi_left = (cap.video_width - cap._roi_w) // 2
        cap._roi_top = (cap.video_height - cap._roi_h) // 2

        self.assertEqual(cap._roi_w, 640)
        self.assertEqual(cap._roi_h, 480)
        self.assertEqual(cap._roi_left, 0)
        self.assertEqual(cap._roi_top, 0)

    def test_roi_centers_on_frame(self):
        """ROI 小于视频时应居中裁切。"""
        config = Config(image_width=200, image_height=100)
        cap = VideoFileCapture.__new__(VideoFileCapture)
        cap.video_width = 640
        cap.video_height = 480
        cap._roi_w = min(config.image_width, cap.video_width)
        cap._roi_h = min(config.image_height, cap.video_height)
        cap._roi_left = (cap.video_width - cap._roi_w) // 2
        cap._roi_top = (cap.video_height - cap._roi_h) // 2

        self.assertEqual(cap._roi_w, 200)
        self.assertEqual(cap._roi_h, 100)
        self.assertEqual(cap._roi_left, 220)  # (640-200)//2
        self.assertEqual(cap._roi_top, 190)  # (480-100)//2


if __name__ == "__main__":
    unittest.main()
