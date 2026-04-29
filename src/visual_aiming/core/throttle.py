# -*- coding: utf-8 -*-
import random
import time
from ..common.utils import ThrottledPrinter

class Throttle:
    def __init__(self, config):
        self.config = config
        self.cycle_start = time.time()
        self.last_refill_time = self.cycle_start
        self.tokens = config.active_duration
        self.last_deny_time = 0
        self.printer = ThrottledPrinter(2.0)

    def allow(self) -> bool:
        if random.random() > self.config.adsorb_prob:
            now = time.time()
            if now - self.last_deny_time > 2.0:
                self.printer.print("prob_skip", "节流: 概率跳过本次吸附")
                self.last_deny_time = now
            return False
        if not self.config.enable_time_throttle:
            return True
        now = time.time()
        elapsed = now - self.cycle_start
        if elapsed >= self.config.cycle_duration:
            self.cycle_start = now
            self.last_refill_time = now
            self.tokens = self.config.active_duration
        else:
            refill_rate = self.config.active_duration / self.config.cycle_duration
            refill_elapsed = max(0.0, now - self.last_refill_time)
            self.last_refill_time = now
            self.tokens += refill_rate * refill_elapsed
            if self.tokens > self.config.active_duration:
                self.tokens = self.config.active_duration
        cost = 1.0 / max(float(getattr(self.config, "detect_fps", 30)), 1.0)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        else:
            if now - self.last_deny_time > 2.0:
                self.printer.print("time_throttle", "节流: 时间片不足，跳过本次吸附")
                self.last_deny_time = now
            return False
