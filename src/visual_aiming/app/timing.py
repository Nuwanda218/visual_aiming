from __future__ import annotations


def compute_active_wait_ms(fps: float, previous_frame_ms: float) -> int:
    frame_budget_ms = 1000.0 / max(1.0, float(fps))
    remaining_ms = frame_budget_ms - max(0.0, float(previous_frame_ms))
    return max(1, int(remaining_ms))
