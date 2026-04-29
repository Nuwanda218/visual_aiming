# -*- coding: utf-8 -*-
import threading
import time
from typing import Optional, Tuple

import numpy as np

from .screen_capture import ScreenCapture
from ..common.timing import sleep_precise


class CaptureWorker:
    def __init__(self, config, wakeup):
        self.config = config
        self.wakeup = wakeup
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._active = False
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_time = 0.0
        self._latest_seq = 0
        self._thread = threading.Thread(target=self._run, name="CaptureWorker", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=1.0)

    def set_active(self, active: bool):
        with self._lock:
            self._active = bool(active)
            if not active:
                self._latest_frame = None
                self._latest_time = 0.0
                self._latest_seq = 0

    def get_latest(self) -> Tuple[Optional[np.ndarray], float, int]:
        with self._lock:
            return self._latest_frame, self._latest_time, self._latest_seq

    def _run(self):
        screen = ScreenCapture(self.config, self.wakeup)
        last_capture = 0.0
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    active = self._active

                if not active:
                    sleep_precise(0.01)
                    last_capture = 0.0
                    continue

                capture_fps = max(1.0, float(getattr(self.config, "capture_fps", 30)))
                interval = 1.0 / capture_fps
                now = time.perf_counter()
                wait_for = interval - (now - last_capture)
                if wait_for > 0:
                    sleep_precise(wait_for)
                    continue

                last_capture = time.perf_counter()
                frame = screen.grab()
                if frame is None:
                    continue

                with self._lock:
                    self._latest_frame = frame
                    self._latest_time = time.time()
                    self._latest_seq += 1
        finally:
            screen.close()
