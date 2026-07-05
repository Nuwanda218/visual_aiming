"""图像获取层 — 帧获取与预处理。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Frame


class MemoryCapture:
    """测试用输入源：从内存列表顺序吐出 Frame，不依赖 cv2。"""

    def __init__(self, frames: Iterable[Frame]) -> None:
        self._frames = list(frames)
        self._index = 0

    def read(self) -> Optional[Frame]:
        # 返回 None 表示数据源结束，runner 会据此停止循环。
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def close(self) -> None:
        pass


class VideoFileCapture:
    """真实视频文件输入源，读取视频帧并裁切 ROI 区域。

    ROI 以视频画面中心为基准，裁切 config.image_width × config.image_height 的区域。
    裁切后的画面中心即准星默认位置。
    """

    def __init__(self, video_path: str | Path, config: Optional[Config] = None) -> None:
        import cv2

        self._cv2 = cv2
        self.path = Path(video_path)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {self.path}")

        # 读取视频基本信息
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self._frame_dt = 1.0 / fps if fps and fps > 0 else 1.0 / 30.0
        self._sequence = 0
        self.video_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))

        # 计算 ROI 裁切参数（以画面中心为基准）
        if config is not None:
            self._roi_w = min(config.image_width, self.video_width)
            self._roi_h = min(config.image_height, self.video_height)
        else:
            # 没有 config 时不裁切，输出原始尺寸
            self._roi_w = self.video_width
            self._roi_h = self.video_height
        self._roi_left = (self.video_width - self._roi_w) // 2
        self._roi_top = (self.video_height - self._roi_h) // 2

    def read(self) -> Optional[Frame]:
        ok, image = self.capture.read()
        if not ok:
            return None

        # ROI 裁切：从画面中心取固定尺寸区域
        cropped = image[
            self._roi_top : self._roi_top + self._roi_h,
            self._roi_left : self._roi_left + self._roi_w,
        ]

        seq = self._sequence
        self._sequence += 1
        return Frame(image=cropped, sequence=seq, timestamp=seq * self._frame_dt)

    def close(self) -> None:
        self.capture.release()
