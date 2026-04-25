# -*- coding: utf-8 -*-
import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List

@dataclass
class Config:
    roi_width: int = 410
    roi_height: int = 315
    capture_fps: int = 30
    capture_thread_enabled: bool = True
    detect_fps: int = 30
    detect_only_new_frames: bool = True

    gaussian_ksize: int = 5
    canny_sigma: float = 0.33
    min_contour_area: int = 150
    morph_kernel_size: int = 3

    max_attempts: int = 30
    head_bias: float = 0.25
    aim_smooth_factor: float = 0.7
    aim_switch_distance: float = 70.0
    aim_switch_smooth_factor: float = 0.35
    aim_target_preference: float = 0.85
    tracker_enabled: bool = True
    tracker_prediction_time: float = 0.025
    tracker_smoothing_factor: float = 0.66
    tracker_stop_threshold: float = 10.0
    tracker_reset_distance: float = 200.0

    recoil_smooth_factor: float = 0.3
    recoil_max_step: int = 15
    jitter_range: float = 5.0
    noise_std: float = 2.0
    aim_deadzone: int = 8
    servo_enabled: bool = True
    servo_thread_enabled: bool = True
    servo_loop_hz: float = 240.0
    servo_filter_alpha: float = 0.602
    servo_filter_beta: float = 0.123
    servo_lead_ms: float = 4.5
    servo_kp: float = 24.0
    servo_kd: float = 0.023
    servo_curve: float = 1.0
    servo_near_gain: float = 0.10
    servo_far_gain: float = 1.25
    servo_arrival_radius: float = 95.0
    servo_near_brake: float = 0.32
    servo_brake_radius: float = 42.0
    servo_deadzone: float = 2.0
    servo_output_gain: float = 1.35
    servo_output_to_error_gain: float = 1.0
    servo_output_to_velocity_gain: float = 1.0
    servo_step_limit: int = 36
    servo_max_speed: float = 2719.0
    servo_max_accel: float = 20060.0
    servo_output_smooth: float = 0.20
    servo_direction_reset_enabled: bool = True
    servo_direction_reset_speed: float = 180.0
    servo_coast_ms: float = 235.0
    servo_lost_brake_ms: float = 323.0
    servo_reacquire_gate: float = 47.0
    servo_reacquire_ramp_ms: float = 0.0

    adsorb_prob: float = 0.8
    cycle_duration: float = 2.0
    active_duration: float = 0.5
    enable_time_throttle: bool = True

    max_step_pixels: int = 10
    unlock_distance: int = 50
    max_track_lost: int = 5
    firing_follow_x: float = 0.45
    firing_follow_y: float = 0.65
    firing_vertical_boost: float = 1.6
    firing_bypass_throttle: bool = True
    firing_yolo_skip_frames: int = 0
    firing_hold_last_aim: bool = True

    recoil_enabled: bool = True
    recoil_profile_path: str = "recoil_profile.json"
    view_compensation_enabled: bool = True
    view_compensation_gain_x: float = 1.0
    view_compensation_gain_y: float = 1.0
    view_compensation_max_offset: float = 220.0
    view_compensation_as_measurement: bool = True

    yolo_model_path: str = "models/best.pt"
    yolo_conf_threshold: float = 0.5
    yolo_iou_threshold: float = 0.45
    yolo_device: str = "auto"
    yolo_half: bool = True
    yolo_head_class_id: int = 0
    yolo_person_class_id: int = 1
    target_stickiness: float = 0.28
    target_history_radius: int = 120
    target_switch_margin: float = 0.08
    target_class_switch_penalty: float = 0.05
    yolo_skip_frames: int = 1
    yolo_imgsz: int = 416
    yolo_preload: bool = False
    debug_enabled: bool = False
    debug_log_enabled: bool = False
    debug_window_scale: float = 1.6

    def load(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=4)
