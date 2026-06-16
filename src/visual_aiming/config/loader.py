from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from visual_aiming.config.schema import ModularConfig


def modular_config_from_mapping(data: Mapping[str, Any]) -> ModularConfig:
    config = ModularConfig()

    roi_width = int(data.get("roi_width", config.frame.roi_size[0]))
    roi_height = int(data.get("roi_height", config.frame.roi_size[1]))
    config.frame.roi_size = (roi_width, roi_height)
    config.frame.capture_fps = float(data.get("capture_fps", config.frame.capture_fps))
    config.frame.source = str(data.get("modular_frame_source", config.frame.source))
    config.frame.video_path = str(data.get("modular_video_path", config.frame.video_path))

    config.runtime.poll_fps = float(data.get("poll_fps", config.runtime.poll_fps))
    config.runtime.detect_fps = float(data.get("detect_fps", config.runtime.detect_fps))
    config.runtime.idle_detect_fps = float(data.get("idle_detect_fps", config.runtime.idle_detect_fps))

    config.detector.model_path = str(data.get("yolo_model_path", config.detector.model_path))
    config.detector.confidence = float(data.get("yolo_conf_threshold", config.detector.confidence))
    config.detector.iou = float(data.get("yolo_iou_threshold", config.detector.iou))
    config.detector.device = str(data.get("yolo_device", config.detector.device))
    config.detector.half = bool(data.get("yolo_half", config.detector.half))
    config.detector.imgsz = int(data.get("yolo_imgsz", config.detector.imgsz))

    config.target_selection.head_class_id = int(data.get("yolo_head_class_id", config.target_selection.head_class_id))
    config.target_selection.person_class_id = int(data.get("yolo_person_class_id", config.target_selection.person_class_id))
    config.target_selection.target_preference = float(data.get("aim_target_preference", config.target_selection.target_preference))
    config.target_selection.sticky_enabled = bool(data.get("target_sticky_enabled", config.target_selection.sticky_enabled))
    config.target_selection.stickiness = float(data.get("target_stickiness", config.target_selection.stickiness))
    config.target_selection.history_radius = int(data.get("target_history_radius", config.target_selection.history_radius))
    switch_margin = float(data.get("target_switch_margin", config.target_selection.switch_margin))
    config.target_selection.switch_margin = switch_margin
    config.target_selection.sticky_switch_margin = float(data.get("target_sticky_switch_margin", switch_margin))
    config.target_selection.class_switch_penalty = float(data.get("target_class_switch_penalty", config.target_selection.class_switch_penalty))

    config.aim.head_bias = float(data.get("head_bias", config.aim.head_bias))

    config.prediction.alpha = float(data.get("tracker_smoothing_factor", config.prediction.alpha))
    config.prediction.lead_time = float(data.get("tracker_prediction_time", config.prediction.lead_time))
    config.prediction.reset_distance = float(data.get("tracker_reset_distance", config.prediction.reset_distance))
    hold_ms = float(data.get("tracker_max_prediction_ms", config.prediction.hold_ms))
    config.prediction.hold_ms = float(data.get("tracker_hold_ms", hold_ms))
    config.prediction.hold_confidence = float(data.get("tracker_hold_confidence", config.prediction.hold_confidence))
    config.prediction.max_hold_ms = config.prediction.hold_ms
    config.prediction.firing_freeze = bool(data.get("firing_disable_tracker_prediction", config.prediction.firing_freeze))

    config.control.deadzone = float(data.get("servo_deadzone", config.control.deadzone))
    config.control.speed_gain = float(data.get("fps_speed_gain", config.control.speed_gain))
    config.control.max_speed = float(data.get("fps_max_speed", config.control.max_speed))
    config.control.acceleration = float(data.get("fps_acceleration", config.control.acceleration))
    config.control.decel_radius = float(data.get("fps_decel_radius", config.control.decel_radius))
    config.control.near_speed_scale = float(data.get("fps_near_speed_scale", config.control.near_speed_scale))
    config.control.max_step = int(data.get("servo_step_limit", config.control.max_step))
    config.control.output_gain = float(data.get("servo_output_gain", config.control.output_gain))

    if bool(data.get("mouse_absolute_mode_enabled", False)):
        config.output.command_mode = "absolute"
    config.output.backend = str(data.get("modular_output_backend", config.output.backend))
    config.output.enable_real_mouse = bool(data.get("modular_enable_real_mouse", config.output.enable_real_mouse))
    config.output.mouse_method = str(data.get("modular_mouse_method", config.output.mouse_method))
    config.output.log_path = str(data.get("modular_output_log_path", config.output.log_path))

    config.diagnostics.enabled = bool(data.get("modular_diagnostics_enabled", config.diagnostics.enabled))
    config.diagnostics.jsonl_path = str(data.get("modular_diagnostics_jsonl_path", config.diagnostics.jsonl_path))
    config.diagnostics.summary_path = str(data.get("modular_diagnostics_summary_path", config.diagnostics.summary_path))
    return config


def load_modular_config(path: str | Path) -> ModularConfig:
    config_path = Path(path)
    if not config_path.exists():
        return ModularConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")
    return modular_config_from_mapping(data)
