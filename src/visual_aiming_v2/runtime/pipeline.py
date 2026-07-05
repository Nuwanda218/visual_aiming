"""运行编排层 — 单帧处理管道。"""
from __future__ import annotations

import math
import time
from typing import Optional

from visual_aiming_v2.shared.ports import ActuationPort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import Detection, Frame, TickResult


class Pipeline:
    """单帧流水线：负责调用各层组件，但不持有具体实现细节。"""

    def __init__(
        self,
        detector: DetectorPort,
        actuator: ActuationPort,
        output: OutputPort,
        diagnostics=None,  # 可选的 DiagnosticLogger 实例
    ) -> None:
        # 这里依赖的是 shared.ports 里的协议，因此测试替身和真实组件可互换。
        self.detector = detector
        self.actuator = actuator
        self.output = output
        self.diagnostics = diagnostics  # 为 None 时不输出诊断日志

    def tick(self, frame: Frame) -> TickResult:
        """处理一帧：detect → select → aim → command → output。"""
        started = time.perf_counter()

        # perception 层：检测
        detections = list(self.detector.detect(frame.image))

        # actuation 层：选目标 + 算指令
        command = self.actuator.process(detections)

        # output 层：执行指令
        self.output.apply(command)

        pipeline_ms = (time.perf_counter() - started) * 1000.0

        # 构建 TickResult
        selected = self._find_selected(detections, command)
        result = TickResult(
            frame=frame,
            detections=detections,
            selected=selected,
            command=command,
        )

        # 诊断日志输出（可选）
        if self.diagnostics is not None:
            self._emit_diagnostics(frame, detections, selected, command, pipeline_ms)

        return result

    def _find_selected(self, detections: list[Detection], command) -> Optional[Detection]:
        """根据 actuation 的 crosshair 反推被选中的目标（用于诊断和可视化）。"""
        if not detections:
            return None
        # no_target 时确实没选中
        if command.reason == "no_target":
            return None
        crosshair = getattr(self.actuator, "crosshair", None)
        if crosshair is None:
            return detections[0] if detections else None
        # 选距离 crosshair 最近的（与 actuation 逻辑一致）
        cx, cy = crosshair
        return min(detections, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))

    def _emit_diagnostics(
        self,
        frame: Frame,
        detections: list[Detection],
        selected: Optional[Detection],
        command,
        pipeline_ms: float,
    ) -> None:
        """收集各层数据，交给诊断日志器格式化输出。"""
        crosshair = getattr(self.actuator, "crosshair", (0, 0))

        # 计算选中目标的索引和距离
        selected_index = None
        selected_distance = None
        if selected is not None:
            for i, det in enumerate(detections):
                if det is selected:
                    selected_index = i
                    break
            sx, sy = selected.center
            cx, cy = crosshair
            selected_distance = math.hypot(sx - cx, sy - cy)

        # 获取图像形状
        image = frame.image
        if hasattr(image, "shape"):
            # OpenCV/numpy 图像通常带 shape: (height, width, channels)。
            image_shape = image.shape
        else:
            image_shape = (0, 0, 0)

        # 获取输出后端名称
        output_name = getattr(self.output, "__class__", type(self.output)).__name__

        self.diagnostics.log_frame(
            frame=frame,
            image_shape=image_shape,
            detections=detections,
            crosshair=crosshair,
            selected=selected,
            selected_index=selected_index,
            selected_distance=selected_distance,
            command=command,
            output_name=output_name,
            pipeline_ms=pipeline_ms,
        )
