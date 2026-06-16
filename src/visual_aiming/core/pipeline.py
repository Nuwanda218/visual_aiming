from __future__ import annotations

import time
from typing import Optional, Protocol

from visual_aiming.algorithms.aim_point import AimStrategy
from visual_aiming.algorithms.control import RelativeController
from visual_aiming.algorithms.prediction import AlphaBetaPredictor
from visual_aiming.algorithms.target_selection import TargetSelector
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.schemas import (
    AimMeasurement,
    ControlCommand,
    DetectionPacket,
    FramePacket,
    LatencyBreakdown,
    PipelineTickResult,
    Point,
    PredictedAim,
    RuntimeMode,
    SelectedTarget,
)


class _Detector(Protocol):
    name: str
    def detect(self, frame: FramePacket) -> DetectionPacket: ...


class _OutputBackend(Protocol):
    name: str
    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None: ...


class _DiagnosticsSink(Protocol):
    def write(self, result: PipelineTickResult) -> None: ...


class ModularPipeline:
    def __init__(
        self,
        config: ModularConfig,
        detector: _Detector,
        output_backend: _OutputBackend,
        diagnostics: Optional[_DiagnosticsSink] = None,
    ) -> None:
        self.config = config
        self.detector = detector
        self.output_backend = output_backend
        self.diagnostics = diagnostics
        self.selector = TargetSelector(config.target_selection)
        self.aim_strategy = AimStrategy(config.aim, config.target_selection.head_class_id)
        self.predictor = AlphaBetaPredictor(config.prediction)
        self.controller = RelativeController(config.control)
        # 预计算不变量
        self._detector_name = getattr(detector, "name", "detector")
        self._output_name = getattr(output_backend, "name", "unknown")
        self._dt = 1.0 / max(1.0, config.runtime.poll_fps)

    def reset(self) -> None:
        self.selector.reset()
        self.predictor.reset()
        self.controller.reset()

    def tick(self, frame, now: Optional[float] = None) -> PipelineTickResult:
        started = time.perf_counter()
        now = frame.timestamp if now is None else now
        mode = frame.mode

        if not mode.active:
            self.reset()
            detections = DetectionPacket(frame.sequence, [], 0.0, self._detector_name, fresh=False)
            result = self._build_result(
                frame=frame,
                mode=mode,
                detections=detections,
                selected=SelectedTarget(detection=None, score=float("inf"), reason="inactive"),
                aim=AimMeasurement(point=None, crosshair=frame.crosshair, error=(0.0, 0.0), valid=False),
                predicted=PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="inactive"),
                command=ControlCommand(mode="none", reason="inactive"),
                started=started,
            )
            self._publish(result)
            return result

        phase_started = time.perf_counter()
        detections = self.detector.detect(frame)
        detect_ms = (time.perf_counter() - phase_started) * 1000.0

        phase_started = time.perf_counter()
        roi_center = (frame.roi_size[0] // 2, frame.roi_size[1] // 2)
        selected = self.selector.select(detections.detections, roi_center=roi_center)
        select_ms = (time.perf_counter() - phase_started) * 1000.0

        phase_started = time.perf_counter()
        aim = self.aim_strategy.measure(selected.detection, frame.roi_offset, frame.crosshair)
        aim_ms = (time.perf_counter() - phase_started) * 1000.0

        phase_started = time.perf_counter()
        predicted = self.predictor.update(aim, mode, now)
        predict_ms = (time.perf_counter() - phase_started) * 1000.0

        phase_started = time.perf_counter()
        if predicted.point is None:
            command = ControlCommand(mode="none", reason="no_target")
        else:
            error = self._error_from_prediction(predicted, frame.crosshair)
            command = self.controller.update(error, active=mode.active, dt=self._dt)
            if predicted.state == "held" and command.mode == "relative":
                command.reason = "held"
        control_ms = (time.perf_counter() - phase_started) * 1000.0

        latency_breakdown = LatencyBreakdown(
            detect_ms=detect_ms,
            select_ms=select_ms,
            aim_ms=aim_ms,
            predict_ms=predict_ms,
            control_ms=control_ms,
        )
        result = self._build_result(
            frame,
            mode,
            detections,
            selected,
            aim,
            predicted,
            command,
            started,
            latency_breakdown,
        )
        self._publish(result)
        return result

    def _error_from_prediction(self, predicted: PredictedAim, crosshair: Point) -> tuple[float, float]:
        if predicted.point is None:
            return (0.0, 0.0)
        return (float(predicted.point[0] - crosshair[0]), float(predicted.point[1] - crosshair[1]))

    def _build_result(
        self,
        frame,
        mode,
        detections,
        selected,
        aim,
        predicted,
        command,
        started,
        latency_breakdown: Optional[LatencyBreakdown] = None,
    ) -> PipelineTickResult:
        latency_ms = (time.perf_counter() - started) * 1000.0
        latency_breakdown = latency_breakdown or LatencyBreakdown()
        latency_breakdown.total_ms = latency_ms
        return PipelineTickResult(
            sequence=frame.sequence,
            timestamp=frame.timestamp,
            mode=mode,
            detections=detections,
            selected=selected,
            aim=aim,
            predicted=predicted,
            command=command,
            output_backend=self._output_name,
            pipeline_latency_ms=latency_ms,
            latency_breakdown=latency_breakdown,
            telemetry=frame.telemetry,
        )

    def _publish(self, result: PipelineTickResult) -> None:
        self.output_backend.apply(result.command, result)
        if self.diagnostics is not None:
            self.diagnostics.write(result)
