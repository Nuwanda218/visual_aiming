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
        diagnostics=None,
    ) -> None:
        self.detector = detector
        self.actuator = actuator
        self.output = output
        self.diagnostics = diagnostics

    def tick(self, frame: Frame) -> TickResult:
        """处理一帧：detect → track → aim → smooth → control → output。"""
        started = time.perf_counter()

        detections = list(self.detector.detect(frame.image))
        command = self.actuator.process(detections)
        self.output.apply(command)

        pipeline_ms = (time.perf_counter() - started) * 1000.0

        selected = self._find_selected(detections, command)
        result = TickResult(
            frame=frame,
            detections=detections,
            selected=selected,
            command=command,
        )

        if self.diagnostics is not None:
            self._emit_diagnostics(frame, detections, selected, command, pipeline_ms)

        return result

    def _find_selected(self, detections: list[Detection], command) -> Optional[Detection]:
        """根据 actuation 的 tracker 获取当前锁定目标。"""
        tracker = getattr(self.actuator, "tracker", None)
        if tracker is not None and tracker.locked_target is not None:
            return tracker.locked_target
        if not detections or command.reason == "no_target":
            return None
        crosshair = getattr(self.actuator, "crosshair", None)
        if crosshair is None:
            return detections[0] if detections else None
        cx, cy = crosshair
        return min(detections, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))

    def _emit_diagnostics(self, frame, detections, selected, command, pipeline_ms):
        """收集各层数据（含 P5/P6 中间状态），交给诊断日志器。"""
        crosshair = getattr(self.actuator, "crosshair", (0, 0))

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

        image = frame.image
        image_shape = image.shape if hasattr(image, "shape") else (0, 0, 0)
        output_name = type(self.output).__name__

        # P6 追踪状态
        tracker = getattr(self.actuator, "tracker", None)
        tracker_info = None
        if tracker is not None:
            tracker_info = {
                "locked_frames": tracker.locked_frames,
                "has_lock": tracker.locked_target is not None,
                "lost_frames": getattr(tracker, "lost_frames", 0),
                "switched": getattr(tracker, "switched", False),
                "has_measurement": getattr(tracker, "has_measurement_this_frame", False),
            }

        # P5 平滑状态
        raw_aim = getattr(self.actuator, "last_raw_aim", None)
        smoothed_aim = getattr(self.actuator, "last_smoothed_aim", None)

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
            tracker_info=tracker_info,
            raw_aim=raw_aim,
            smoothed_aim=smoothed_aim,
        )
