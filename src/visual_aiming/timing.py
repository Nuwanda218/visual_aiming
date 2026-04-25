# -*- coding: utf-8 -*-
import time


def sleep_precise(seconds: float) -> None:
    if seconds <= 0:
        return

    if seconds >= 0.002:
        time.sleep(seconds)
        return

    deadline = time.perf_counter() + seconds
    spin_threshold = 0.0002
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > spin_threshold:
            sleep_for = max(0.0, remaining - spin_threshold)
            if sleep_for >= 0.001:
                time.sleep(sleep_for)
            else:
                time.sleep(0)
