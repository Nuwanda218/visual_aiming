# -*- coding: utf-8 -*-
import numpy as np
import mss
from .utils import ThrottledPrinter

class ScreenCapture:
    def __init__(self, config, wakeup):
        self.config = config
        self.wakeup = wakeup
        self.sct = mss.MSS()
        self.fail_count = 0
        self.printer = ThrottledPrinter(2.0)

    def grab(self):
        roi_offset = self.wakeup.get_roi_offset()
        if roi_offset is None:
            return None
        roi_left, roi_top = roi_offset
        monitor = {
            "left": roi_left,
            "top": roi_top,
            "width": self.config.roi_width,
            "height": self.config.roi_height
        }
        try:
            img = self.sct.grab(monitor)
            frame = np.array(img)[:, :, :3]
            self.fail_count = 0
            return frame
        except Exception as e:
            self.fail_count += 1
            if self.fail_count <= 3 or self.fail_count % 30 == 0:
                self.printer.print("screenshot_error", f"截图失败 ({self.fail_count}次): {e}")
            return None

    def close(self):
        try:
            self.sct.close()
        except Exception:
            pass
