from __future__ import annotations

import time
from typing import Callable, Optional, Protocol

from visual_aiming.algorithms.aim_point import AimStrategy
from visual_aiming.algorithms.control import RelativeController
from visual_aiming.algorithms.prediction import AlphaBetaPredictor
from visual_aiming.algorithms.target_selection import TargetSelector
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.runtime_state import RuntimeState
from visual_aiming.core.schemas import (
    AimMeasurement,
    ControlCommand,
    ControlTarget,
    DetectionPacket,
    FramePacket,
    PipelineResult,
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

        detections = self.detector.detect(frame)
        roi_center = (frame.roi_size[0] // 2, frame.roi_size[1] // 2)
        selected = self.selector.select(detections.detections, roi_center=roi_center)
        aim = self.aim_strategy.measure(selected.detection, frame.roi_offset, frame.crosshair)
        predicted = self.predictor.update(aim, mode, now)
        error = self._error_from_prediction(predicted, frame.crosshair)
        command = self.controller.update(error, active=mode.active, dt=self._dt)
        result = self._build_result(frame, mode, detections, selected, aim, predicted, command, started)
        self._publish(result)
        return result

    def _error_from_prediction(self, predicted: PredictedAim, crosshair: Point) -> tuple[float, float]:
        if predicted.point is None:
            return (0.0, 0.0)
        return (float(predicted.point[0] - crosshair[0]), float(predicted.point[1] - crosshair[1]))

    def _build_result(self, frame, mode, detections, selected, aim, predicted, command, started) -> PipelineTickResult:
        latency_ms = (time.perf_counter() - started) * 1000.0
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
        )

    def _publish(self, result: PipelineTickResult) -> None:
        self.output_backend.apply(result.command, result)
        if self.diagnostics is not None:
            self.diagnostics.write(result)


# --- Legacy RuntimePipeline (used by existing runtime) ---


class RuntimePipeline:
    def __init__(
        self,
        config,
        aim_calculator,
        tracker=None,
        state: Optional[RuntimeState] = None,
        fallback_point: Optional[Callable[[], Point]] = None,
    ):
        self.config = config
        self.aim_calculator = aim_calculator
        self.tracker = tracker
        self.state = state or RuntimeState()
        self.fallback_point = fallback_point

    def reset(self) -> None:
        self.state.reset_tracking_state()
        if self.tracker is not None:
            self.tracker.reset()

    def current_control(self, active: bool, crosshair: Optional[Point]) -> ControlTarget:
        if not active:
            return ControlTarget(target=None, crosshair=crosshair, has_measurement=False, active=False)
        if self.state.last_aim_base is None:
            self.state.last_aim_base = self._fallback(crosshair)
        return ControlTarget(target=self.state.last_aim_base, crosshair=crosshair, has_measurement=False, active=True)

    def process_detection(self, active, firing, target, target_is_fresh, roi_offset, crosshair, now) -> PipelineResult:
        if not active:
            return PipelineResult(ControlTarget(None, crosshair, False, active), None, None)
        aim_base = None
        if roi_offset is not None:
            roi_left, roi_top = roi_offset
            raw_aim = self.aim_calculator.calculate(target, roi_left, roi_top)
            aim_base = raw_aim if target_is_fresh else None
            fresh_measurement = target_is_fresh and target is not None and aim_base is not None
            tracker_allowed = not (firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True)))
            if fresh_measurement and self.tracker is not None and tracker_allowed:
                aim_base = self.tracker.update(aim_base, now)
            elif fresh_measurement and self.tracker is not None and not tracker_allowed:
                self.tracker.reset()
            self._update_last_aim(target, target_is_fresh, aim_base, firing, crosshair)

        base_target = aim_base
        used_tracker_prediction = False
        tracker_allowed = not (firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True)))
        if base_target is None and self.tracker is not None and tracker_allowed and self.tracker.has_recent_track(now, float(getattr(self.config, "tracker_max_prediction_ms", 160.0))):
            base_target = self.tracker.predict(now)
            used_tracker_prediction = True
        if base_target is None and self.state.last_aim_base is not None:
            base_target = self.state.last_aim_base
        has_measurement = aim_base is not None
        if not has_measurement and used_tracker_prediction and bool(getattr(self.config, "tracker_prediction_as_measurement", True)):
            has_measurement = True
        control = ControlTarget(target=base_target, crosshair=crosshair, has_measurement=has_measurement, active=active)
        return PipelineResult(control=control, aim_point=aim_base, debug_bbox=getattr(target, "bbox", None) if target is not None else None, used_tracker_prediction=used_tracker_prediction)

    def _update_last_aim(self, target, target_is_fresh, aim_base, firing, crosshair) -> None:
        if target is not None and target_is_fresh:
            if aim_base is not None:
                self.state.last_aim_base = aim_base
            elif not self._hold_last_aim(firing):
                self.state.last_aim_base = self._fallback(crosshair)
            return
        if target is None:
            if aim_base is not None:
                self.state.last_aim_base = aim_base
            elif not self._hold_last_aim(firing):
                self.state.last_aim_base = self._fallback(crosshair)

    def _hold_last_aim(self, firing: bool) -> bool:
        return firing and bool(getattr(self.config, "firing_hold_last_aim", True)) and self.state.last_aim_base is not None

    def _fallback(self, crosshair: Optional[Point]) -> Optional[Point]:
        if crosshair is not None:
            return crosshair
        if self.fallback_point is not None:
            return self.fallback_point()
        return None
