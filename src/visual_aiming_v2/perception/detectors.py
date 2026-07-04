from __future__ import annotations

from typing import Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Detection


class StaticDetector:
    def __init__(self, detections: Sequence[Detection]) -> None:
        self._detections = list(detections)

    def detect(self, image) -> list[Detection]:
        return list(self._detections)


class YoloDetector:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None

    def detect(self, image) -> list[Detection]:
        if self._model is None:
            self._load_model()
        results = self._model(
            image,
            conf=self.config.confidence,
            iou=self.config.iou,
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                cls_id = int(box.cls[0]) if getattr(box, "cls", None) is not None else -1
                names = getattr(self._model, "names", {})
                label = names.get(cls_id, "unknown") if isinstance(names, dict) else "unknown"
                detections.append(Detection(
                    x=x1, y=y1,
                    w=max(0, x2 - x1), h=max(0, y2 - y1),
                    confidence=conf, label=label,
                ))
        return detections

    def _load_model(self) -> None:
        from ultralytics import YOLO

        self._model = YOLO(self.config.model_path)
        if self.config.device != "auto":
            self._model.to(self.config.device)
