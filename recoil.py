# -*- coding: utf-8 -*-
import json
import threading
from typing import List, Tuple


class RecoilCompensator:
    def __init__(
        self,
        profile_path: str,
        load_profile: bool = True,
        view_enabled: bool = True,
        view_gain_x: float = 1.0,
        view_gain_y: float = 1.0,
        view_max_offset: float = 220.0,
    ):
        self.profile_path = profile_path
        self.offsets: List[Tuple[float, float, float]] = []
        self.duration_total = 0.0
        self.sample_rate = 0.0
        self.firing_start_time = 0.0
        self.firing = False

        self.view_enabled = bool(view_enabled)
        self.view_gain_x = float(view_gain_x)
        self.view_gain_y = float(view_gain_y)
        self.view_max_offset = max(1.0, float(view_max_offset))
        self._view_offset_x = 0.0
        self._view_offset_y = 0.0
        self._lock = threading.Lock()

        if load_profile:
            self.load_profile(profile_path)
        else:
            print("[压枪] 静态压枪曲线已禁用，仅启用动态视角补偿")

    def load_profile(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.sample_rate = data.get("sample_rate_hz", 100)
            self.duration_total = data.get("duration", 0)
            raw_offsets = data.get("offsets", [])
            self.offsets = [(item["t"], item["dx"], item["dy"]) for item in raw_offsets]
            print(f"[压枪] 已加载曲线: {path}, 时长={self.duration_total:.2f}s, 采样点={len(self.offsets)}")
            if self.offsets:
                total_dx, total_dy = self.offsets[-1][1], self.offsets[-1][2]
                print(f"[压枪] 总偏移: dx={total_dx}px, dy={total_dy}px")
        except Exception as e:
            print(f"[压枪] 加载失败: {e}, 将使用零补偿")
            self.offsets = []

    def start_firing(self, start_time: float):
        self.firing_start_time = start_time
        self.firing = True

    def stop_firing(self):
        self.firing = False

    def note_measurement(self):
        with self._lock:
            self._view_offset_x = 0.0
            self._view_offset_y = 0.0

    def record_view_output(self, dx: int, dy: int):
        if not self.view_enabled:
            return

        with self._lock:
            self._view_offset_x = self._clamp_view_offset(self._view_offset_x - dx * self.view_gain_x)
            self._view_offset_y = self._clamp_view_offset(self._view_offset_y - dy * self.view_gain_y)

    def clear_view_compensation(self):
        self.note_measurement()

    def has_view_compensation(self) -> bool:
        if not self.view_enabled:
            return False
        with self._lock:
            return abs(self._view_offset_x) > 1e-3 or abs(self._view_offset_y) > 1e-3

    def get_view_offset(self) -> Tuple[int, int]:
        if not self.view_enabled:
            return (0, 0)
        with self._lock:
            return (int(round(self._view_offset_x)), int(round(self._view_offset_y)))

    def apply_view_compensation(self, point: Tuple[int, int]) -> Tuple[int, int]:
        view_dx, view_dy = self.get_view_offset()
        return (point[0] + view_dx, point[1] + view_dy)

    def get_recoil_offset(self, current_time: float) -> Tuple[int, int]:
        if not self.firing or not self.offsets:
            return (0, 0)
        elapsed = current_time - self.firing_start_time
        if elapsed <= 0:
            return (0, 0)
        if elapsed >= self.offsets[-1][0]:
            raw_dx, raw_dy = self.offsets[-1][1], self.offsets[-1][2]
        else:
            for i in range(len(self.offsets) - 1):
                t0, dx0, dy0 = self.offsets[i]
                t1, dx1, dy1 = self.offsets[i + 1]
                if t0 <= elapsed <= t1:
                    ratio = (elapsed - t0) / (t1 - t0)
                    raw_dx = dx0 + ratio * (dx1 - dx0)
                    raw_dy = dy0 + ratio * (dy1 - dy0)
                    break
            else:
                raw_dx, raw_dy = 0, 0
        comp_x = -int(raw_dx)
        comp_y = -int(raw_dy)
        return (comp_x, comp_y)

    def get_current_offset(self, current_time: float) -> Tuple[int, int]:
        recoil_x, recoil_y = self.get_recoil_offset(current_time)
        view_x, view_y = self.get_view_offset()
        return (recoil_x + view_x, recoil_y + view_y)

    def _clamp_view_offset(self, value: float) -> float:
        if value > self.view_max_offset:
            return self.view_max_offset
        if value < -self.view_max_offset:
            return -self.view_max_offset
        return value
