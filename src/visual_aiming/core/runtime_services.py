from dataclasses import dataclass
from typing import Optional, Tuple

import cv2

from ..actions.config_window import ConfigWindow
from ..actions.debug_visualizer import DebugVisualizer
from ..actions.input_listener import WakeUpModule
from ..actions.mouse_control import MouseController, get_cursor_pos
from ..common.utils import ThrottledPrinter
from ..vision.capture_worker import CaptureWorker
from ..vision.detection import TargetDetector
from ..vision.screen_capture import ScreenCapture
from .aim_calculator import AimPointCalculator
from .detect_scheduler import DetectionScheduler
from .pipeline import RuntimePipeline
from .runtime_state import RuntimeState
from .target_tracker import TargetTracker
from .throttle import Throttle


@dataclass
class RuntimeServices:
    config: object
    state: RuntimeState
    wakeup: WakeUpModule
    detector: TargetDetector
    aim_calculator: AimPointCalculator
    mouse_controller: MouseController
    throttle: Throttle
    detect_scheduler: DetectionScheduler
    debug_printer: ThrottledPrinter
    debug_visualizer: DebugVisualizer
    pipeline: RuntimePipeline
    capture_worker: Optional[CaptureWorker] = None
    screen_capture: Optional[ScreenCapture] = None
    target_tracker: Optional[TargetTracker] = None
    config_window: Optional[ConfigWindow] = None

    @classmethod
    def create(
        cls,
        config,
        roi_offset: Tuple[int, int],
        default_crosshair: Tuple[int, int],
        config_path: str = "config.json",
    ) -> "RuntimeServices":
        wakeup = WakeUpModule(config)
        wakeup.set_fixed_roi_offset(roi_offset)
        wakeup.set_default_crosshair(*default_crosshair)

        capture_worker = None
        screen_capture = None
        if bool(getattr(config, "capture_thread_enabled", True)):
            capture_worker = CaptureWorker(config, wakeup)
            capture_worker.start()
        else:
            screen_capture = ScreenCapture(config, wakeup)

        detector = TargetDetector()
        detector.set_debug(True)

        aim_calculator = AimPointCalculator(config)
        aim_calculator.set_wakeup(wakeup)

        target_tracker = cls._create_tracker(config)
        state = RuntimeState()
        pipeline = RuntimePipeline(
            config=config,
            aim_calculator=aim_calculator,
            tracker=target_tracker,
            state=state,
            fallback_point=get_cursor_pos,
        )

        mouse_controller = MouseController(config)
        throttle = Throttle(config)
        detect_scheduler = DetectionScheduler(config)
        debug_printer = ThrottledPrinter(0.5)
        debug_visualizer = DebugVisualizer(
            enabled=bool(getattr(config, "debug_enabled", False)),
            roi_size=(config.roi_width, config.roi_height),
            window_scale=getattr(config, "debug_window_scale", 1.6),
        )

        config_window = None
        if bool(getattr(config, "config_ui_enabled", True)):
            config_window = ConfigWindow(config, config_path)
            config_window.start()

        if getattr(config, "yolo_preload", False):
            detector.preload(config, (config.roi_height, config.roi_width, 3))

        return cls(
            config=config,
            state=state,
            wakeup=wakeup,
            detector=detector,
            aim_calculator=aim_calculator,
            mouse_controller=mouse_controller,
            throttle=throttle,
            detect_scheduler=detect_scheduler,
            debug_printer=debug_printer,
            debug_visualizer=debug_visualizer,
            pipeline=pipeline,
            capture_worker=capture_worker,
            screen_capture=screen_capture,
            target_tracker=target_tracker,
            config_window=config_window,
        )

    def stop(self) -> None:
        self.mouse_controller.stop()
        if self.config_window is not None:
            self.config_window.stop()
        if self.capture_worker is not None:
            self.capture_worker.stop()
        elif self.screen_capture is not None:
            self.screen_capture.close()
        self.wakeup.stop()
        self.debug_visualizer.close()
        cv2.destroyAllWindows()

    def set_capture_active(self, active: bool) -> None:
        if self.capture_worker is not None:
            self.capture_worker.set_active(active)

    def get_frame(self):
        if self.capture_worker is not None:
            return self.capture_worker.get_latest()
        if self.screen_capture is not None:
            return self.screen_capture.grab(), 0.0, None
        return None, 0.0, None

    @staticmethod
    def _create_tracker(config) -> Optional[TargetTracker]:
        if not bool(getattr(config, "tracker_enabled", True)):
            return None
        return TargetTracker(
            smoothing_factor=float(getattr(config, "tracker_smoothing_factor", 0.66)),
            prediction_time=float(getattr(config, "tracker_prediction_time", 0.025)),
            stop_threshold=float(getattr(config, "tracker_stop_threshold", 10.0)),
            reset_distance=float(getattr(config, "tracker_reset_distance", 200.0)),
        )

