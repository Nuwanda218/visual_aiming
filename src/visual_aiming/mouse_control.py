# -*- coding: utf-8 -*-
import ctypes
import math
import random
import threading
import time
from typing import Optional, Tuple

from .utils import ThrottledPrinter
from .visual_servo import ServoParams, VisualServoLoop
from .timing import sleep_precise

user32 = ctypes.windll.user32
MOUSEEVENTF_MOVE = 0x0001


def send_relative_move(dx: int, dy: int):
    """发送相对鼠标移动事件"""
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


def get_cursor_pos() -> Tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


class MouseController:
    def __init__(self, config, motion_compensator=None):
        self.config = config
        self.motion_compensator = motion_compensator
        self.last_move_time = 0
        self.use_servo = bool(getattr(config, "servo_enabled", True))
        self.thread_enabled = self.use_servo and bool(getattr(config, "servo_thread_enabled", True))
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.servo = VisualServoLoop(self._build_servo_params(config))
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self._target_pos: Optional[Tuple[int, int]] = None
        self._crosshair_pos: Optional[Tuple[int, int]] = None
        self._active = False
        self._measurement_seq = 0
        self._servo_thread: Optional[threading.Thread] = None
        try:
            self.printer = ThrottledPrinter(2.0)
        except:
            self.printer = None

        if self.thread_enabled:
            self._servo_thread = threading.Thread(
                target=self._servo_worker,
                name="MouseServoLoop",
                daemon=True,
            )
            self._servo_thread.start()

    def reset(self):
        if self.thread_enabled:
            with self.state_lock:
                self._target_pos = None
                self._crosshair_pos = None
                self._active = False
            return

        self._reset_servo_state()

    def stop(self):
        if not self.thread_enabled:
            return
        self.stop_event.set()
        if self._servo_thread is not None:
            self._servo_thread.join(timeout=1.0)

    def set_motion_compensator(self, motion_compensator):
        self.motion_compensator = motion_compensator

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
        if not active:
            self.reset()
            return

        if self.thread_enabled:
            self.update_target(target_pos, crosshair_pos, has_measurement, active)
            return

        if self.use_servo:
            self._move_towards_servo(target_pos, crosshair_pos, has_measurement)
            return

        if target_pos is None:
            return
        self._move_towards_legacy(target_pos)

    def _move_towards_legacy(self, target_pos: Tuple[int, int]):
        cur_x, cur_y = get_cursor_pos()
        dx = target_pos[0] - cur_x
        dy = target_pos[1] - cur_y
        dist = math.hypot(dx, dy)

        if dist <= self.config.aim_deadzone:
            return

        now = time.time()
        if now - self.last_move_time > 0.5:
            if self.printer:
                self.printer.print("move_target", f"移动鼠标至: {target_pos} (dist={dist:.1f})")
            else:
                print(f"移动鼠标至: {target_pos} (dist={dist:.1f})")
            self.last_move_time = now

        move_x = dx
        move_y = dy
        max_step = self.config.recoil_max_step
        move_x = max(-max_step, min(max_step, move_x))
        move_y = max(-max_step, min(max_step, move_y))

        jitter = getattr(self.config, "jitter_range", 0)
        move_x += random.uniform(-jitter, jitter)
        move_y += random.uniform(-jitter, jitter)

        noise_std = getattr(self.config, "noise_std", 0)
        move_x += random.gauss(0, noise_std)
        move_y += random.gauss(0, noise_std)
        send_x = int(move_x)
        send_y = int(move_y)
        send_relative_move(send_x, send_y)
        if self.motion_compensator is not None:
            self.motion_compensator.record_view_output(send_x, send_y)

    def _move_towards_servo(
        self,
        target_pos: Optional[Tuple[int, int]],
        crosshair_pos: Optional[Tuple[int, int]],
        has_measurement: bool,
    ):
        if crosshair_pos is None:
            self._reset_servo_state()
            return

        now = time.perf_counter()
        dt = 1.0 / max(int(getattr(self.config, "capture_fps", 30)), 1)

        measurement = None
        if has_measurement and target_pos is not None:
            measurement = (
                float(target_pos[0] - crosshair_pos[0]),
                float(target_pos[1] - crosshair_pos[1]),
            )

        delta = self.servo.update(measurement, now, dt)
        output_gain = float(getattr(self.config, "servo_output_gain", 1.0))
        move_x = delta.x * output_gain
        move_y = delta.y * output_gain

        max_step = max(1, int(getattr(self.config, "servo_step_limit", getattr(self.config, "recoil_max_step", 15))))
        move_x = max(-max_step, min(max_step, move_x))
        move_y = max(-max_step, min(max_step, move_y))

        move_x += self.subpixel_x
        move_y += self.subpixel_y
        send_x = int(round(move_x))
        send_y = int(round(move_y))
        self.subpixel_x = move_x - send_x
        self.subpixel_y = move_y - send_y

        if send_x == 0 and send_y == 0:
            return

        if measurement is not None and self.printer is not None:
            error_mag = math.hypot(measurement[0], measurement[1])
            command_mag = math.hypot(send_x, send_y)
            self.printer.print(
                "servo_move",
                f"伺服控制 state={self.servo.track_state} error={error_mag:.1f} delta={command_mag:.1f}",
            )

        send_relative_move(send_x, send_y)
        if self.motion_compensator is not None:
            self.motion_compensator.record_view_output(send_x, send_y)

    def _servo_worker(self):
        interval = 1.0 / max(float(getattr(self.config, "servo_loop_hz", 240.0)), 1.0)
        last_time = time.perf_counter()
        last_measurement_seq = -1
        was_active = False

        while not self.stop_event.is_set():
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
                    self._reset_servo_state()
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

            self._run_servo_step(measurement, dt, loop_start)
            self._sleep_to_next_tick(loop_start, interval)

    def _sleep_to_next_tick(self, tick_start: float, interval: float):
        remaining = interval - (time.perf_counter() - tick_start)
        if remaining > 0:
            sleep_precise(remaining)

    def _run_servo_step(self, measurement: Optional[Tuple[float, float]], dt: float, now: float):
        delta = self.servo.update(measurement, now, dt)
        output_gain = float(getattr(self.config, "servo_output_gain", 1.0))
        move_x = delta.x * output_gain
        move_y = delta.y * output_gain

        max_step = max(1, int(getattr(self.config, "servo_step_limit", getattr(self.config, "recoil_max_step", 15))))
        move_x = max(-max_step, min(max_step, move_x))
        move_y = max(-max_step, min(max_step, move_y))

        move_x += self.subpixel_x
        move_y += self.subpixel_y
        send_x = int(round(move_x))
        send_y = int(round(move_y))
        self.subpixel_x = move_x - send_x
        self.subpixel_y = move_y - send_y

        if send_x == 0 and send_y == 0:
            return

        if measurement is not None and self.printer is not None:
            error_mag = math.hypot(measurement[0], measurement[1])
            command_mag = math.hypot(send_x, send_y)
            self.printer.print(
                "servo_move",
                f"伺服控制 state={self.servo.track_state} error={error_mag:.1f} delta={command_mag:.1f}",
            )

        send_relative_move(send_x, send_y)
        if self.motion_compensator is not None:
            self.motion_compensator.record_view_output(send_x, send_y)
        output_to_error_gain = float(getattr(self.config, "servo_output_to_error_gain", 1.0))
        output_to_velocity_gain = float(getattr(self.config, "servo_output_to_velocity_gain", 1.0))
        self.servo.apply_output_feedback((send_x, send_y), dt, output_to_error_gain, output_to_velocity_gain)

    def _reset_servo_state(self):
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.servo.reset()

    def _build_servo_params(self, config) -> ServoParams:
        return ServoParams(
            filter_alpha=float(getattr(config, "servo_filter_alpha", 0.602)),
            filter_beta=float(getattr(config, "servo_filter_beta", 0.123)),
            lead_ms=float(getattr(config, "servo_lead_ms", 4.5)),
            kp=float(getattr(config, "servo_kp", 24.0)),
            kd=float(getattr(config, "servo_kd", 0.023)),
            curve=float(getattr(config, "servo_curve", 1.0)),
            near_gain=float(getattr(config, "servo_near_gain", 0.10)),
            far_gain=float(getattr(config, "servo_far_gain", 1.25)),
            arrival_radius=float(getattr(config, "servo_arrival_radius", 95.0)),
            near_brake=float(getattr(config, "servo_near_brake", 0.32)),
            brake_radius=float(getattr(config, "servo_brake_radius", 42.0)),
            deadzone=float(getattr(config, "servo_deadzone", 2.0)),
            max_speed=float(getattr(config, "servo_max_speed", 2719.0)),
            max_accel=float(getattr(config, "servo_max_accel", 20060.0)),
            output_smooth=float(getattr(config, "servo_output_smooth", 0.20)),
            direction_reset_enabled=bool(getattr(config, "servo_direction_reset_enabled", True)),
            direction_reset_speed=float(getattr(config, "servo_direction_reset_speed", 180.0)),
            coast_ms=float(getattr(config, "servo_coast_ms", 235.0)),
            lost_brake_ms=float(getattr(config, "servo_lost_brake_ms", 323.0)),
            reacquire_gate=float(getattr(config, "servo_reacquire_gate", 47.0)),
            reacquire_ramp_ms=float(getattr(config, "servo_reacquire_ramp_ms", 0.0)),
        )
