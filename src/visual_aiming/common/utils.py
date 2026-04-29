# -*- coding: utf-8 -*-
import time

class ThrottledPrinter:
    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.last_print = {}

    def print(self, key: str, message: str):
        now = time.time()
        if key not in self.last_print or (now - self.last_print[key]) >= self.interval:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")
            self.last_print[key] = now