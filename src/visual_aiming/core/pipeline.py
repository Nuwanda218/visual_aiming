from typing import Callable, Optional

from .runtime_state import RuntimeState
from .schemas import ControlTarget, PipelineResult, Point


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
            return ControlTarget(
                target=None,
                crosshair=crosshair,
                has_measurement=False,
                active=False,
            )
        if self.state.last_aim_base is None:
            self.state.last_aim_base = self._fallback(crosshair)
        return ControlTarget(
            target=self.state.last_aim_base,
            crosshair=crosshair,
            has_measurement=False,
            active=True,
        )

    def process_detection(
        self,
        active: bool,
        firing: bool,
        target,
        target_is_fresh: bool,
        roi_offset: Optional[Point],
        crosshair: Optional[Point],
        now: float,
    ) -> PipelineResult:
        if not active:
            return self._empty_result(crosshair, active)

        aim_base = None
        if roi_offset is not None:
            roi_left, roi_top = roi_offset
            raw_aim = self.aim_calculator.calculate(target, roi_left, roi_top)
            aim_base = raw_aim if target_is_fresh else None

            fresh_measurement = target_is_fresh and target is not None and aim_base is not None
            tracker_allowed = not (
                firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True))
            )
            if fresh_measurement and self.tracker is not None and tracker_allowed:
                aim_base = self.tracker.update(aim_base, now)
            elif fresh_measurement and self.tracker is not None and not tracker_allowed:
                self.tracker.reset()

            self._update_last_aim(target, target_is_fresh, aim_base, firing, crosshair)

        base_target = aim_base
        used_tracker_prediction = False
        tracker_allowed = not (
            firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True))
        )
        if (
            base_target is None
            and self.tracker is not None
            and tracker_allowed
            and self.tracker.has_recent_track(
                now,
                float(getattr(self.config, "tracker_max_prediction_ms", 160.0)),
            )
        ):
            base_target = self.tracker.predict(now)
            used_tracker_prediction = True

        if base_target is None and self.state.last_aim_base is not None:
            base_target = self.state.last_aim_base

        has_measurement = aim_base is not None
        if (
            not has_measurement
            and used_tracker_prediction
            and bool(getattr(self.config, "tracker_prediction_as_measurement", True))
        ):
            has_measurement = True

        control = ControlTarget(
            target=base_target,
            crosshair=crosshair,
            has_measurement=has_measurement,
            active=active,
        )
        return PipelineResult(
            control=control,
            aim_point=aim_base,
            debug_bbox=getattr(target, "bbox", None) if target is not None else None,
            used_tracker_prediction=used_tracker_prediction,
        )

    def _empty_result(self, crosshair: Optional[Point], active: bool) -> PipelineResult:
        return PipelineResult(
            control=ControlTarget(
                target=None,
                crosshair=crosshair,
                has_measurement=False,
                active=active,
            ),
            aim_point=None,
            debug_bbox=None,
        )

    def _update_last_aim(
        self,
        target,
        target_is_fresh: bool,
        aim_base: Optional[Point],
        firing: bool,
        crosshair: Optional[Point],
    ) -> None:
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
        return (
            firing
            and bool(getattr(self.config, "firing_hold_last_aim", True))
            and self.state.last_aim_base is not None
        )

    def _fallback(self, crosshair: Optional[Point]) -> Optional[Point]:
        if crosshair is not None:
            return crosshair
        if self.fallback_point is not None:
            return self.fallback_point()
        return None
