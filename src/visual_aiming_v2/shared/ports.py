from __future__ import annotations

from typing import Optional, Protocol, Sequence

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class CapturePort(Protocol):
    """帧输入端口：真实视频、屏幕采集、内存假数据都只需实现这个协议。"""

    def read(self) -> Optional[Frame]: ...
    def close(self) -> None: ...


class DetectorPort(Protocol):
    """检测端口：runtime 不关心背后是真 YOLO、假检测器还是其它模型。"""

    def detect(self, image) -> Sequence[Detection]: ...


class ActuationPort(Protocol):
    """控制决策端口：把检测结果转换为抽象 Command，暂不直接碰鼠标。"""

    def process(self, detections: Sequence[Detection]) -> Command: ...


class OutputPort(Protocol):
    """输出端口：Command 可以被丢弃、记录，未来也可以接真实鼠标。"""

    def apply(self, command: Command) -> None: ...
    def close(self) -> None: ...
