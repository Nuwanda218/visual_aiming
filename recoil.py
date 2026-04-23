# -*- coding: utf-8 -*-
import json
from typing import List, Tuple

class RecoilCompensator:
    def __init__(self, profile_path: str):
        self.profile_path = profile_path
        self.offsets: List[Tuple[float, float, float]] = []
        self.duration_total = 0.0
        self.sample_rate = 0.0
        self.load_profile(profile_path)
        self.firing_start_time = 0.0
        self.firing = False

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

    def get_current_offset(self, current_time: float) -> Tuple[int, int]:
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
                t1, dx1, dy1 = self.offsets[i+1]
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