# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scale: float) -> "Vec2":
        return Vec2(self.x * scale, self.y * scale)

    __rmul__ = __mul__

    def __truediv__(self, scale: float) -> "Vec2":
        if abs(scale) <= 1e-9:
            return Vec2()
        return Vec2(self.x / scale, self.y / scale)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        magnitude = self.length()
        if magnitude <= 1e-9:
            return Vec2()
        return self / magnitude

    def clamp_length(self, max_length: float) -> "Vec2":
        magnitude = self.length()
        if magnitude <= max_length or magnitude <= 1e-9:
            return self
        return self * (max_length / magnitude)


@dataclass(frozen=True)
class ServoParams:
    filter_alpha: float
    filter_beta: float
    lead_ms: float
    kp: float
    kd: float
    curve: float
    near_gain: float
    far_gain: float
    arrival_radius: float
    near_brake: float
    brake_radius: float
    deadzone: float
    max_speed: float
    max_accel: float
    output_smooth: float
    coast_ms: float
    lost_brake_ms: float
    reacquire_gate: float
    reacquire_ramp_ms: float


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


class AlphaBetaFilter:
    def __init__(self) -> None:
        self.pos = Vec2()
        self.vel = Vec2()
        self.last_time: Optional[float] = None
        self.initialized = False

    def reset(self, pos: Vec2, now: float) -> None:
        self.pos = pos
        self.vel = Vec2()
        self.last_time = now
        self.initialized = True

    def predict_to(self, now: float) -> None:
        if self.last_time is None:
            self.last_time = now
            return

        dt = max(0.0, min(now - self.last_time, 0.08))
        self.pos = self.pos + self.vel * dt
        self.last_time = now

    def push(self, measurement: Vec2, now: float, alpha: float, beta: float) -> None:
        alpha = max(0.01, min(alpha, 0.95))
        beta = max(0.0, min(beta, 0.80))
        if not self.initialized or self.last_time is None:
            self.reset(measurement, now)
            return

        previous_time = self.last_time
        self.predict_to(now)
        dt = max(now - previous_time, 1e-4)

        residual = measurement - self.pos
        residual_magnitude = residual.length()
        adaptive_alpha = alpha
        adaptive_beta = beta
        if residual_magnitude < 2.0:
            adaptive_alpha *= 0.22
            adaptive_beta *= 0.18
        elif residual_magnitude < 8.0:
            adaptive_alpha *= 0.58
            adaptive_beta *= 0.50

        self.pos = self.pos + residual * adaptive_alpha
        self.vel = (self.vel + residual * (adaptive_beta / dt)).clamp_length(2800.0)

    def estimate(self, now: float, lead_time: float) -> Tuple[Vec2, Vec2]:
        if not self.initialized:
            return Vec2(), Vec2()

        dt = 0.0 if self.last_time is None else max(0.0, min(now - self.last_time, 0.16))
        predicted_pos = self.pos + self.vel * (dt + lead_time)
        return predicted_pos, self.vel


class RelativeServoController:
    def __init__(self) -> None:
        self.command_vel = Vec2()
        self.last_delta = Vec2()

    def reset(self) -> None:
        self.command_vel = Vec2()
        self.last_delta = Vec2()

    def update(self, error: Vec2, error_vel: Vec2, dt: float, params: ServoParams) -> Vec2:
        dt = max(0.0005, min(dt, 0.05))
        distance = error.length()
        brake_zone = 1.0

        if distance <= params.deadzone:
            desired_vel = Vec2()
        else:
            direction = error.normalized()
            active_distance = max(0.0, distance - params.deadzone)
            arrival_radius = max(1.0, params.arrival_radius)
            arrival = smoothstep(active_distance / arrival_radius)
            near_gain = max(0.01, params.near_gain)
            far_gain = max(near_gain, params.far_gain)
            shaped_distance = active_distance * (near_gain + (far_gain - near_gain) * arrival)
            if shaped_distance > 1.0 and params.curve != 1.0:
                shaped_distance = shaped_distance ** params.curve / (arrival_radius ** (params.curve - 1.0))

            brake_radius = max(1.0, params.brake_radius)
            brake_zone = 1.0 - smoothstep(active_distance / brake_radius)

            p_velocity = direction * (params.kp * shaped_distance)
            d_velocity = error_vel * params.kd
            desired_vel = (p_velocity + d_velocity).clamp_length(params.max_speed)

        max_change = params.max_accel * dt
        self.command_vel = self.command_vel + (desired_vel - self.command_vel).clamp_length(max_change)
        smooth = max(0.0, min(params.output_smooth, 0.95))
        self.command_vel = self.command_vel * (1.0 - smooth) + desired_vel * smooth
        near_brake = max(0.0, params.near_brake)
        if near_brake > 0.0 and brake_zone > 0.0:
            retain = max(0.0, 1.0 - near_brake * brake_zone * dt * 60.0)
            self.command_vel = self.command_vel * retain

        delta = self.command_vel * dt
        self.last_delta = delta
        return delta


class VisualServoLoop:
    def __init__(self, params: ServoParams) -> None:
        self.params = params
        self.filter = AlphaBetaFilter()
        self.controller = RelativeServoController()
        self.track_state = "lost"
        self.confidence = 0.0
        self.last_seen_time: Optional[float] = None

    def reset(self) -> None:
        self.filter = AlphaBetaFilter()
        self.controller.reset()
        self.track_state = "lost"
        self.confidence = 0.0
        self.last_seen_time = None

    def update(self, measurement: Optional[Tuple[float, float]], now: float, dt: float) -> Vec2:
        dt = max(0.0005, min(dt, 0.05))
        saw_measurement = False

        if measurement is not None:
            measurement_vec = Vec2(float(measurement[0]), float(measurement[1]))
            self._accept_measurement(measurement_vec, now)
            saw_measurement = True

        self._update_track_state(now, dt, saw_measurement)
        estimate, estimate_vel = self.filter.estimate(now, self.params.lead_ms / 1000.0)
        control_error = estimate * self.confidence
        control_vel = estimate_vel * self.confidence
        return self.controller.update(control_error, control_vel, dt, self.params)

    def apply_output_feedback(
        self,
        delta: Tuple[float, float],
        dt: float,
        gain: float = 1.0,
        velocity_gain: float = 1.0,
    ) -> None:
        if not self.filter.initialized:
            return

        gain = float(gain)
        if abs(gain) <= 1e-6:
            return

        compensation = Vec2(float(delta[0]) * gain, float(delta[1]) * gain)
        self.filter.pos = self.filter.pos - compensation
        if dt > 1e-4:
            velocity_gain = float(velocity_gain)
            compensation_vel = (compensation / dt) * velocity_gain
            self.filter.vel = (self.filter.vel - compensation_vel).clamp_length(2800.0)

    def _accept_measurement(self, measurement: Vec2, now: float) -> None:
        predicted, _ = self.filter.estimate(now, 0.0)
        gap = (measurement - predicted).length()

        if self.last_seen_time is None:
            missing_ms = float("inf")
        else:
            missing_ms = max(0.0, (now - self.last_seen_time) * 1000.0)

        should_hard_reacquire = (
            self.track_state == "lost" or missing_ms > self.params.coast_ms
        ) and gap > self.params.reacquire_gate

        if should_hard_reacquire:
            self.filter.reset(measurement, now)
            self.controller.reset()
            self.confidence = 0.0
            self.track_state = "reacquire"
        else:
            self.filter.push(
                measurement,
                now,
                self.params.filter_alpha,
                self.params.filter_beta,
            )

        self.last_seen_time = now

    def _update_track_state(self, now: float, dt: float, saw_measurement: bool) -> None:
        if saw_measurement:
            ramp_seconds = max(self.params.reacquire_ramp_ms / 1000.0, 0.001)
            self.confidence = min(1.0, self.confidence + dt / ramp_seconds)
            self.track_state = "track" if self.confidence >= 0.995 else "reacquire"
            return

        if self.last_seen_time is None:
            self.confidence = 0.0
            self.track_state = "lost"
            return

        missing_ms = max(0.0, (now - self.last_seen_time) * 1000.0)
        if missing_ms <= self.params.coast_ms:
            coast_seconds = max(self.params.coast_ms / 1000.0, 0.001)
            self.confidence = max(0.55, self.confidence - dt * 0.35 / coast_seconds)
            self.track_state = "coast"
            return

        brake_seconds = max(self.params.lost_brake_ms / 1000.0, 0.001)
        self.confidence = max(0.0, self.confidence - dt / brake_seconds)
        self.track_state = "lost"
