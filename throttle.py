# -*- coding: utf-8 -*-
import random
import time
from utils import ThrottledPrinter

class Throttle:
    def __init__(self, config):
        self.config = config
        self.cycle_start = time.time()
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
            self.tokens = self.config.active_duration
        else:
            refill_rate = self.config.active_duration / self.config.cycle_duration
            self.tokens += refill_rate * 0.02
            if self.tokens > self.config.active_duration:
                self.tokens = self.config.active_duration
        cost = 0.02
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        else:
            if now - self.last_deny_time > 2.0:
                self.printer.print("time_throttle", "节流: 时间片不足，跳过本次吸附")
                self.last_deny_time = now
            return False
