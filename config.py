# -*- coding: utf-8 -*-
import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List

@dataclass
class Config:
    roi_width: int = 410
    roi_height: int = 315
    capture_fps: int = 30

    gaussian_ksize: int = 5
    canny_sigma: float = 0.33
    min_contour_area: int = 150
    morph_kernel_size: int = 3

    max_attempts: int = 30
    head_bias: float = 0.25
    aim_smooth_factor: float = 0.7
    aim_target_preference: float = 0.85

    recoil_smooth_factor: float = 0.3
    recoil_max_step: int = 15
    jitter_range: float = 5.0
    noise_std: float = 2.0
    aim_deadzone: int = 8

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

    yolo_model_path: str = "models/best.pt"
    yolo_conf_threshold: float = 0.5
    yolo_iou_threshold: float = 0.45
    yolo_device: str = "auto"
    yolo_half: bool = True
    yolo_head_class_id: int = 0
    yolo_person_class_id: int = 1
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
