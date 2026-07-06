from __future__ import annotations

from typing import Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Detection


class StaticDetector:
    """测试用检测器：固定返回预设 Detection，隔离模型依赖。"""

    def __init__(self, detections: Sequence[Detection]) -> None:
        self._detections = list(detections)

    def detect(self, image) -> list[Detection]:
        return list(self._detections)


class YoloDetector:
    """YOLO 适配器：把 ultralytics 的输出转换成项目内部 Detection。"""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None

    def detect(self, image) -> list[Detection]:
        # 懒加载模型：创建 detector 不等于立刻加载权重，CLI 组装和测试更轻。
        if self._model is None:
            self._load_model()
        results = self._model(
            image,
            conf=self.config.perception.confidence,
            iou=self.config.perception.iou,
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                # ultralytics 使用 xyxy，这里转换为 V2 内部统一的 x/y/w/h。
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
        """加载 YOLO 模型并打印设备信息。"""
        from ultralytics import YOLO
        import torch

        # 检测 CUDA 可用性
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            cuda_version = torch.version.cuda
            print(f"[YOLO] CUDA 已启用 | GPU: {gpu_name} | CUDA: {cuda_version}")
        else:
            print("[YOLO] CUDA 不可用，使用 CPU 推理")

        perception = self.config.perception
        print(f"[YOLO] 加载模型: {perception.model_path} | device={perception.device}")
        self._model = YOLO(perception.model_path)

        # 设备分配
        if perception.device == "auto":
            runtime_device = "cuda:0" if cuda_available else "cpu"
        else:
            runtime_device = perception.device
        self._model.to(runtime_device)

        print(f"[YOLO] 模型已加载 | 运行设备: {runtime_device}")
