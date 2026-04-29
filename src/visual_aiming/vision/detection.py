# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from ultralytics import YOLO

from ..common.resource_path import resource_path

BBox = Tuple[int, int, int, int]


@dataclass
class DetectedTarget:
    """Detection result in ROI coordinates: (x, y, width, height)."""

    bbox: BBox
    confidence: float = 0.0
    class_id: Optional[int] = None
    class_name: str = "unknown"

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    @property
    def aspect_ratio(self) -> float:
        return self.h / self.w if self.w > 0 else 0.0

    @property
    def area(self) -> int:
        return self.w * self.h


class TargetDetector:
    """
    YOLOv8 detector.

    Backward-compatible class API:
        TargetDetector().detect(frame, config, roi_center=None) -> DetectedTarget | None

    Simple module API:
        detection.detect(frame, config) -> (xc, yc, w, h) | None
    """

    def __init__(self):
        self.model = None
        self.model_path = None
        self.device = None
        self.requested_device = None
        self.class_names: Dict[int, str] = {}
        self.frame_count = 0
        self.last_result: Optional[DetectedTarget] = None
        self.last_result_fresh = False
        self.use_half = False
        self.preloaded_shape = None

    def set_debug(self, enabled: bool):
        # Kept for compatibility. Debug drawing is handled by DebugVisualizer.
        return None

    def load_model(self, model_path: str, device: str = "cpu", use_half: bool = True):
        resolved_path = resource_path(model_path)
        runtime_device, use_half = self._resolve_runtime_device(device, use_half)
        print(
            f"[YOLO] 加载模型: {resolved_path} | requested_device={device} | "
            f"runtime_device={runtime_device} | half={use_half}"
        )
        self.model = YOLO(resolved_path)
        self.model.to(runtime_device)
        self.model_path = model_path
        self.requested_device = device
        self.device = runtime_device
        self.use_half = use_half
        self.class_names = self._extract_class_names()
        print("[YOLO] 模型加载完成")

    def detect(
        self,
        frame_bgr: np.ndarray,
        config,
        roi_center: Optional[Tuple[int, int]] = None,
        firing: bool = False,
    ) -> Optional[DetectedTarget]:
        if frame_bgr is None:
            return None

        self._ensure_model(config)

        self.frame_count += 1
        if firing:
            skip_frames = max(0, int(getattr(config, "firing_yolo_skip_frames", 0)))
        else:
            skip_frames = max(0, int(getattr(config, "yolo_skip_frames", 0)))
        if skip_frames > 0 and self.last_result is not None:
            if (self.frame_count - 1) % (skip_frames + 1) != 0:
                self.last_result_fresh = False
                return self.last_result

        conf_threshold = float(getattr(config, "yolo_conf_threshold", 0.5))
        iou_threshold = float(getattr(config, "yolo_iou_threshold", 0.45))

        self.use_half = bool(getattr(config, "yolo_half", True)) and bool(self.device and self.device.startswith("cuda"))

        try:
            results = self.model(
                frame_bgr,
                conf=conf_threshold,
                iou=iou_threshold,
                imgsz=self._get_inference_imgsz(config),
                classes=self._get_inference_classes(config),
                device=self.device,
                half=self.use_half,
                verbose=False,
            )
        except Exception as exc:
            print(f"[YOLO] 推理失败: {exc}")
            self.last_result = None
            self.last_result_fresh = False
            return None

        boxes = results[0].boxes if results else None
        if boxes is None or len(boxes) == 0:
            self.last_result = None
            self.last_result_fresh = False
            return None

        if roi_center is None:
            h, w = frame_bgr.shape[:2]
            roi_center = (w // 2, h // 2)

        best_target = self._select_best_box(boxes, roi_center, config)
        self.last_result = best_target
        self.last_result_fresh = best_target is not None
        return best_target

    def detect_bbox(
        self,
        frame_bgr: np.ndarray,
        config,
        roi_center: Optional[Tuple[int, int]] = None,
        firing: bool = False,
    ) -> Optional[BBox]:
        target = self.detect(frame_bgr, config, roi_center, firing=firing)
        return target.bbox if target is not None else None

    def _ensure_model(self, config):
        model_path = getattr(config, "yolo_model_path", "models/best.pt")
        device = getattr(config, "yolo_device", "auto")
        use_half = bool(getattr(config, "yolo_half", True))
        if (
            self.model is None
            or self.model_path != model_path
            or self.requested_device != device
        ):
            self.load_model(model_path, device, use_half)
            self.preloaded_shape = None

    def preload(self, config, frame_shape: Tuple[int, int, int]):
        self._ensure_model(config)
        if self.model is None:
            return

        normalized_shape = tuple(int(v) for v in frame_shape)
        if self.preloaded_shape == normalized_shape:
            return

        warmup_frame = np.zeros(normalized_shape, dtype=np.uint8)
        try:
            self.model(
                warmup_frame,
                conf=float(getattr(config, "yolo_conf_threshold", 0.5)),
                iou=float(getattr(config, "yolo_iou_threshold", 0.45)),
                imgsz=self._get_inference_imgsz(config),
                classes=self._get_inference_classes(config),
                device=self.device,
                half=self.use_half,
                verbose=False,
            )
            self.preloaded_shape = normalized_shape
            print(
                f"[YOLO] 模型预热完成 | device={self.device} | "
                f"imgsz={self._get_inference_imgsz(config)}"
            )
        except Exception as exc:
            print(f"[YOLO] 模型预热失败: {exc}")

    def _select_best_box(self, boxes, roi_center: Tuple[int, int], config) -> Optional[DetectedTarget]:
        roi_cx, roi_cy = roi_center
        candidates = []
        max_distance_sq = max(1, roi_cx * roi_cx + roi_cy * roi_cy)
        previous_target = self.last_result
        track_radius = max(1, int(getattr(config, "target_history_radius", 120)))
        track_radius_sq = track_radius * track_radius

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().tolist()
            x = max(0, int(round(x1)))
            y = max(0, int(round(y1)))
            w = max(0, int(round(x2 - x1)))
            h = max(0, int(round(y2 - y1)))
            if w <= 0 or h <= 0:
                continue

            confidence = float(box.conf[0].detach().cpu().item())
            class_id = self._read_class_id(box)
            class_name = self.class_names.get(class_id, "unknown")
            cx = x + w // 2
            cy = y + h // 2
            distance_sq = (cx - roi_cx) ** 2 + (cy - roi_cy) ** 2

            target = DetectedTarget((x, y, w, h), confidence, class_id, class_name)
            base_score = self._score_target(config, class_id, confidence, distance_sq, max_distance_sq)
            total_score = self._apply_target_continuity(config, target, base_score, previous_target, track_radius_sq)
            previous_distance_sq = self._distance_to_previous_target_sq(target, previous_target)
            candidates.append(
                {
                    "score": total_score,
                    "base_score": base_score,
                    "target": target,
                    "previous_distance_sq": previous_distance_sq,
                }
            )

        if not candidates:
            return None

        candidates.sort(key=lambda item: item["score"])
        best_candidate = candidates[0]
        sticky_candidate = self._select_sticky_candidate(candidates, previous_target, track_radius_sq)
        if sticky_candidate is not None and sticky_candidate["target"] is not best_candidate["target"]:
            switch_margin = max(0.0, float(getattr(config, "target_switch_margin", 0.08)))
            if best_candidate["score"] + switch_margin >= sticky_candidate["score"]:
                return sticky_candidate["target"]

        return best_candidate["target"]

    def _extract_class_names(self) -> Dict[int, str]:
        names = getattr(self.model, "names", {})
        if isinstance(names, dict):
            return {int(k): str(v) for k, v in names.items()}
        if isinstance(names, (list, tuple)):
            return {idx: str(name) for idx, name in enumerate(names)}
        return {}

    def _read_class_id(self, box) -> Optional[int]:
        if getattr(box, "cls", None) is None:
            return None
        return int(box.cls[0].detach().cpu().item())

    def _get_inference_classes(self, config):
        head_class_id = int(getattr(config, "yolo_head_class_id", 0))
        person_class_id = int(getattr(config, "yolo_person_class_id", 1))
        classes = sorted({head_class_id, person_class_id})
        return classes if classes else None

    def _get_target_preference(self, config) -> float:
        value = float(getattr(config, "aim_target_preference", 1.0))
        return max(0.0, min(1.0, value))

    def _score_target(
        self,
        config,
        class_id: Optional[int],
        confidence: float,
        distance_sq: int,
        max_distance_sq: int,
    ) -> float:
        preference = self._get_target_preference(config)
        head_class_id = int(getattr(config, "yolo_head_class_id", 0))
        person_class_id = int(getattr(config, "yolo_person_class_id", 1))

        normalized_distance = min(1.0, distance_sq / max_distance_sq)
        confidence_penalty = 1.0 - max(0.0, min(1.0, confidence))

        if class_id == head_class_id:
            class_penalty = 1.0 - preference
        elif class_id == person_class_id:
            class_penalty = preference
        else:
            class_penalty = 1.5

        return (class_penalty * 0.60) + (normalized_distance * 0.30) + (confidence_penalty * 0.10)

    def _apply_target_continuity(
        self,
        config,
        target: DetectedTarget,
        base_score: float,
        previous_target: Optional[DetectedTarget],
        track_radius_sq: int,
    ) -> float:
        if previous_target is None:
            return base_score

        stickiness = max(0.0, min(1.0, float(getattr(config, "target_stickiness", 0.28))))
        class_switch_penalty = max(0.0, float(getattr(config, "target_class_switch_penalty", 0.05)))
        previous_distance_sq = self._distance_to_previous_target_sq(target, previous_target)

        continuity_bonus = 0.0
        if previous_distance_sq is not None and previous_distance_sq <= track_radius_sq:
            normalized_track_distance = min(1.0, previous_distance_sq / max(1, track_radius_sq))
            continuity_bonus = (1.0 - normalized_track_distance) * stickiness

        continuity_score = base_score - continuity_bonus
        if (
            previous_target.class_id is not None
            and target.class_id is not None
            and target.class_id != previous_target.class_id
        ):
            continuity_score += class_switch_penalty

        return continuity_score

    def _distance_to_previous_target_sq(
        self,
        target: DetectedTarget,
        previous_target: Optional[DetectedTarget],
    ) -> Optional[int]:
        if previous_target is None:
            return None
        dx = target.center_x - previous_target.center_x
        dy = target.center_y - previous_target.center_y
        return dx * dx + dy * dy

    def _select_sticky_candidate(self, candidates, previous_target: Optional[DetectedTarget], track_radius_sq: int):
        if previous_target is None:
            return None

        in_radius = [
            candidate
            for candidate in candidates
            if candidate["previous_distance_sq"] is not None and candidate["previous_distance_sq"] <= track_radius_sq
        ]
        if not in_radius:
            return None

        in_radius.sort(key=lambda item: (item["previous_distance_sq"], item["score"]))
        return in_radius[0]

    def _get_inference_imgsz(self, config) -> int:
        return max(32, int(getattr(config, "yolo_imgsz", 640)))

    def _resolve_runtime_device(self, requested_device: str, allow_half: bool) -> Tuple[str, bool]:
        requested = (requested_device or "auto").strip().lower()

        if requested in {"", "gpu", "cuda", "0"}:
            requested = "cuda:0"
        elif requested.isdigit():
            requested = f"cuda:{requested}"

        try:
            import torch
        except Exception as exc:
            if requested != "cpu":
                print(f"[YOLO] 无法导入 torch，回退 CPU: {exc}")
            return "cpu", False

        cuda_available = bool(torch.cuda.is_available())
        if requested == "auto":
            runtime_device = "cuda:0" if cuda_available else "cpu"
        elif requested.startswith("cuda"):
            if cuda_available:
                runtime_device = requested
            else:
                print("[YOLO] 请求 GPU 推理，但当前 CUDA 不可用，回退 CPU")
                runtime_device = "cpu"
        else:
            runtime_device = requested

        use_half = bool(allow_half) and runtime_device.startswith("cuda")
        return runtime_device, use_half


_default_detector = TargetDetector()


def detect(frame_bgr: np.ndarray, config) -> Optional[BBox]:
    """Simple public interface: return (x, y, width, height) in ROI coordinates."""
    return _default_detector.detect_bbox(frame_bgr, config)
