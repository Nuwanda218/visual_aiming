# -*- coding: utf-8 -*-
import ctypes
import ctypes.wintypes
import math
import random
import threading
import time
from typing import Optional, Tuple

from .timing import sleep_precise
from .utils import ThrottledPrinter

user32 = ctypes.windll.user32
MOUSEEVENTF_MOVE = 0x0001


def send_relative_move(dx: int, dy: int):
    """发送相对鼠标移动事件"""
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


def get_cursor_pos() -> Tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


class MouseController:
    def __init__(self, config):
        self.config = config
        self.thread_enabled = bool(getattr(config, "servo_thread_enabled", True))
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self._target_pos: Optional[Tuple[int, int]] = None
        self._crosshair_pos: Optional[Tuple[int, int]] = None
        self._active = False
        self._measurement_seq = 0
        self._servo_thread: Optional[threading.Thread] = None

        self.error_x = 0.0
        self.error_y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.has_error = False

        try:
            self.printer = ThrottledPrinter(2.0)
        except Exception:
            self.printer = None

        if self.thread_enabled:
            self._servo_thread = threading.Thread(
                target=self._servo_worker,
                name="MouseFpsController",
                daemon=True,
            )
            self._servo_thread.start()

    def reset(self):
        if self.thread_enabled:
            with self.state_lock:
                self._target_pos = None
                self._crosshair_pos = None
                self._active = False
        self._reset_controller_state()

    def stop(self):
        if not self.thread_enabled:
            return
        self.stop_event.set()
        if self._servo_thread is not None:
            self._servo_thread.join(timeout=1.0)

    def update_target(
        self,
        target_pos: Optional[Tuple[int, int]],
        crosshair_pos: Optional[Tuple[int, int]] = None,
        has_measurement: bool = True,
        active: bool = True,
    ):
        if not self.thread_enabled:
            self.move_towards(target_pos, crosshair_pos, has_measurement, active)
            return

        with self.state_lock:
            self._target_pos = target_pos
            self._crosshair_pos = crosshair_pos
            self._active = active
            if has_measurement and target_pos is not None and crosshair_pos is not None:
                self._measurement_seq += 1

    def move_towards(
        self,
        target_pos: Optional[Tuple[int, int]],
        crosshair_pos: Optional[Tuple[int, int]] = None,
        has_measurement: bool = True,
        active: bool = True,
    ):
        if not active or crosshair_pos is None:
            self.reset()
            return

        measurement = None
        if has_measurement and target_pos is not None:
            measurement = (
                float(target_pos[0] - crosshair_pos[0]),
                float(target_pos[1] - crosshair_pos[1]),
            )

        self._run_controller_step(measurement, 1.0 / max(float(getattr(self.config, "servo_loop_hz", 240.0)), 1.0))

    def _servo_worker(self):
        last_time = time.perf_counter()
        last_measurement_seq = -1
        was_active = False

        while not self.stop_event.is_set():
            interval = 1.0 / max(float(getattr(self.config, "servo_loop_hz", 240.0)), 1.0)
            loop_start = time.perf_counter()
            dt = max(0.0005, min(loop_start - last_time, 0.05))
            last_time = loop_start

            with self.state_lock:
                target_pos = self._target_pos
                crosshair_pos = self._crosshair_pos
                active = self._active
                measurement_seq = self._measurement_seq

            if not active or crosshair_pos is None:
                if was_active:
                    self._reset_controller_state()
                    was_active = False
                self._sleep_to_next_tick(loop_start, interval)
                continue

            was_active = True
            measurement = None
            if (
                measurement_seq != last_measurement_seq
                and target_pos is not None
                and crosshair_pos is not None
            ):
                measurement = (
                    float(target_pos[0] - crosshair_pos[0]),
                    float(target_pos[1] - crosshair_pos[1]),
                )
                last_measurement_seq = measurement_seq

            self._run_controller_step(measurement, dt)
            self._sleep_to_next_tick(loop_start, interval)

    def _sleep_to_next_tick(self, tick_start: float, interval: float):
        remaining = interval - (time.perf_counter() - tick_start)
        if remaining > 0:
            sleep_precise(remaining)

    def _run_controller_step(self, measurement: Optional[Tuple[float, float]], dt: float):
        if measurement is not None:
            self._accept_measurement(measurement)

        if not self.has_error:
            return

        send_x, send_y = self._compute_move(dt)
        if send_x == 0 and send_y == 0:
            return

        send_relative_move(send_x, send_y)
        self._apply_output_feedback(send_x, send_y, dt)

        if self.printer is not None:
            error_mag = math.hypot(self.error_x, self.error_y)
            command_mag = math.hypot(send_x, send_y)
            self.printer.print(
                "fps_mouse_move",
                f"FPS控制 error={error_mag:.1f} delta={command_mag:.1f}",
            )

    def _accept_measurement(self, measurement: Tuple[float, float]):
        mx, my = measurement
        measurement_distance = math.hypot(mx, my)
        current_distance = math.hypot(self.error_x, self.error_y)
        reacquire_distance = max(1.0, float(getattr(self.config, "fps_reacquire_distance", 180.0)))

        if not self.has_error or abs(measurement_distance - current_distance) >= reacquire_distance:
            self.error_x = mx
            self.error_y = my
            self.velocity_x = 0.0
            self.velocity_y = 0.0
            self.has_error = True
            return

        if self.velocity_x * mx + self.velocity_y * my < 0.0:
            self.velocity_x = 0.0
            self.velocity_y = 0.0

        blend = max(0.0, min(1.0, float(getattr(self.config, "fps_measurement_blend", 0.85))))
        self.error_x = self.error_x * (1.0 - blend) + mx * blend
        self.error_y = self.error_y * (1.0 - blend) + my * blend
        self.has_error = True

    def _compute_move(self, dt: float) -> Tuple[int, int]:
        dt = max(0.0005, min(dt, 0.05))
        distance = math.hypot(self.error_x, self.error_y)
        deadzone = max(0.0, float(getattr(self.config, "servo_deadzone", 2.0)))

        if distance <= deadzone:
            self._brake_to_stop()
            return (0, 0)

        angle = math.atan2(self.error_y, self.error_x)
        jitter_angle = max(0.0, float(getattr(self.config, "fps_jitter_angle", 0.0)))
        if jitter_angle > 0.0:
            jitter_distance = max(1.0, float(getattr(self.config, "fps_jitter_distance", 180.0)))
            angle += random.uniform(-jitter_angle, jitter_angle) * min(1.0, distance / jitter_distance)

        speed_gain = max(0.0, float(getattr(self.config, "fps_speed_gain", 42.0)))
        min_speed = max(0.0, float(getattr(self.config, "fps_min_speed", 0.0)))
        max_speed = max(min_speed, float(getattr(self.config, "fps_max_speed", 7200.0)))
        target_speed = max(min_speed, min(max_speed, distance * speed_gain))

        decel_radius = max(deadzone + 1.0, float(getattr(self.config, "fps_decel_radius", 135.0)))
        near_scale = max(0.01, min(1.0, float(getattr(self.config, "fps_near_speed_scale", 0.10))))
        decel = smoothstep(distance / decel_radius)
        target_speed *= near_scale + (1.0 - near_scale) * decel

        target_vel_x = math.cos(angle) * target_speed
        target_vel_y = math.sin(angle) * target_speed
        accel = max(0.1, float(getattr(self.config, "fps_acceleration", 52.0)))
        alpha = 1.0 - math.exp(-accel * dt)
        self.velocity_x += (target_vel_x - self.velocity_x) * alpha
        self.velocity_y += (target_vel_y - self.velocity_y) * alpha

        brake_radius = max(deadzone + 1.0, float(getattr(self.config, "fps_brake_radius", 90.0)))
        brake = max(0.0, float(getattr(self.config, "fps_brake", 0.72)))
        if distance < brake_radius and brake > 0.0:
            brake_zone = 1.0 - smoothstep(distance / brake_radius)
            retain = max(0.0, 1.0 - brake * brake_zone * dt * 60.0)
            self.velocity_x *= retain
            self.velocity_y *= retain

        move_x = self.velocity_x * dt
        move_y = self.velocity_y * dt
        output_gain = float(getattr(self.config, "servo_output_gain", 1.0))
        move_x *= output_gain
        move_y *= output_gain

        max_step = max(1, int(getattr(self.config, "servo_step_limit", getattr(self.config, "recoil_max_step", 15))))
        move_x, move_y = self._clamp_length(move_x, move_y, float(max_step))
        move_x, move_y = self._apply_overshoot_guard(move_x, move_y)

        move_x += self.subpixel_x
        move_y += self.subpixel_y
        send_x = int(round(move_x))
        send_y = int(round(move_y))
        self.subpixel_x = move_x - send_x
        self.subpixel_y = move_y - send_y
        return (send_x, send_y)

    def _apply_overshoot_guard(self, move_x: float, move_y: float) -> Tuple[float, float]:
        if not bool(getattr(self.config, "servo_overshoot_guard_enabled", True)):
            return move_x, move_y

        distance = math.hypot(self.error_x, self.error_y)
        deadzone = max(0.0, float(getattr(self.config, "servo_deadzone", 2.0)))
        deadzone_scale = max(1.0, float(getattr(self.config, "servo_overshoot_guard_deadzone_scale", 1.45)))

        if distance <= deadzone * deadzone_scale:
            self._brake_to_stop()
            return (0.0, 0.0)

        radius = max(deadzone + 1.0, float(getattr(self.config, "servo_overshoot_guard_radius", 80.0)))
        if distance >= radius:
            return move_x, move_y

        ratio = max(0.05, min(1.0, float(getattr(self.config, "servo_overshoot_guard_ratio", 0.30))))
        min_step = max(0.0, float(getattr(self.config, "servo_overshoot_guard_min_step", 0.0)))
        feedback_gain = max(0.05, abs(float(getattr(self.config, "servo_output_to_error_gain", 1.0))))

        allowed_screen_delta = max(min_step, (distance - deadzone) * ratio)
        allowed_mouse_delta = allowed_screen_delta / feedback_gain
        return self._clamp_length(move_x, move_y, allowed_mouse_delta)

    def _apply_output_feedback(self, send_x: int, send_y: int, dt: float):
        feedback_gain = float(getattr(self.config, "servo_output_to_error_gain", 1.0))
        self.error_x -= send_x * feedback_gain
        self.error_y -= send_y * feedback_gain

        velocity_feedback = float(getattr(self.config, "fps_velocity_feedback", 0.0))
        if dt > 1e-4 and abs(velocity_feedback) > 1e-6:
            self.velocity_x -= (send_x / dt) * velocity_feedback
            self.velocity_y -= (send_y / dt) * velocity_feedback

        if math.hypot(self.error_x, self.error_y) <= float(getattr(self.config, "servo_deadzone", 2.0)):
            self._brake_to_stop()

    def _brake_to_stop(self):
        self.error_x = 0.0
        self.error_y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.has_error = False

    def _reset_controller_state(self):
        self._brake_to_stop()

    def _clamp_length(self, x: float, y: float, max_length: float) -> Tuple[float, float]:
        length = math.hypot(x, y)
        if length <= max_length or length <= 1e-6:
            return x, y
        scale = max_length / length
        return x * scale, y * scale
