# -*- coding: utf-8 -*-
import json
from typing import List, Tuple


class RecoilCompensator:
    def __init__(
        self,
        profile_path: str,
        load_profile: bool = True,
        config=None,
    ):
        self.profile_path = profile_path
        self.offsets: List[Tuple[float, float, float]] = []
        self.duration_total = 0.0
        self.sample_rate = 0.0
        self.firing_start_time = 0.0
        self.firing = False

        self.parametric_enabled = True
        self.parametric_start_delay_ms = 80.0
        self.parametric_ramp_ms = 450.0
        self.parametric_pull_y_per_sec = 180.0
        self.parametric_max_y = 90.0
        self.parametric_pull_x_per_sec = 0.0
        self.parametric_max_x = 30.0

        if config is not None:
            self.configure_from(config)

        if load_profile:
            self.load_profile(profile_path)
        else:
            print("[压枪] 静态压枪曲线已禁用")

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
            print(f"[压枪] 加载失败: {e}, 将使用参数化压枪")
            self.offsets = []

    def configure_from(self, config):
        self.parametric_enabled = bool(getattr(config, "recoil_parametric_enabled", True))
        self.parametric_start_delay_ms = max(
            0.0,
            float(getattr(config, "recoil_parametric_start_delay_ms", 80.0)),
        )
        self.parametric_ramp_ms = max(
            1.0,
            float(getattr(config, "recoil_parametric_ramp_ms", 450.0)),
        )
        self.parametric_pull_y_per_sec = float(
            getattr(config, "recoil_parametric_pull_y_per_sec", 180.0)
        )
        self.parametric_max_y = max(
            0.0,
            float(getattr(config, "recoil_parametric_max_y", 90.0)),
        )
        self.parametric_pull_x_per_sec = float(
            getattr(config, "recoil_parametric_pull_x_per_sec", 0.0)
        )
        self.parametric_max_x = max(
            0.0,
            float(getattr(config, "recoil_parametric_max_x", 30.0)),
        )

    def start_firing(self, start_time: float):
        self.firing_start_time = start_time
        self.firing = True

    def stop_firing(self):
        self.firing = False

    def get_recoil_offset(self, current_time: float) -> Tuple[int, int]:
        if not self.firing:
            return (0, 0)

        if self.offsets:
            return self._get_profile_offset(current_time)

        if self.parametric_enabled:
            return self._get_parametric_offset(current_time)

        return (0, 0)

    def _get_profile_offset(self, current_time: float) -> Tuple[int, int]:
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

    def _get_parametric_offset(self, current_time: float) -> Tuple[int, int]:
        elapsed = current_time - self.firing_start_time
        effective = elapsed - self.parametric_start_delay_ms / 1000.0
        if effective <= 0:
            return (0, 0)

        ramp_seconds = self.parametric_ramp_ms / 1000.0
        ramp = max(0.0, min(1.0, effective / ramp_seconds))
        eased = ramp * ramp * (3.0 - 2.0 * ramp)

        raw_x = self.parametric_pull_x_per_sec * effective * eased
        raw_y = self.parametric_pull_y_per_sec * effective * eased
        raw_x = self._clamp(raw_x, -self.parametric_max_x, self.parametric_max_x)
        raw_y = self._clamp(raw_y, -self.parametric_max_y, self.parametric_max_y)
        return (int(round(raw_x)), int(round(raw_y)))

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value
