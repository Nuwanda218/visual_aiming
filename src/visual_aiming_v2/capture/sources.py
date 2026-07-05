from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

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
    """真实视频文件输入源，把 cv2 的帧读取结果包装成统一 Frame。"""

    def __init__(self, video_path: str | Path) -> None:
        # 延迟导入 cv2，让不需要视频功能的测试不被 OpenCV 依赖阻塞。
        import cv2

        self.path = Path(video_path)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {self.path}")
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        # 某些视频读不到 FPS，退回 30 FPS，保证 timestamp 仍然单调递增。
        self._frame_dt = 1.0 / fps if fps and fps > 0 else 1.0 / 30.0
        self._sequence = 0

    def read(self) -> Optional[Frame]:
        ok, image = self.capture.read()
        if not ok:
            return None
        seq = self._sequence
        self._sequence += 1
        return Frame(image=image, sequence=seq, timestamp=seq * self._frame_dt)

    def close(self) -> None:
        self.capture.release()
