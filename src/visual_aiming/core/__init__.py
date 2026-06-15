# -*- coding: utf-8 -*-
"""Core pipeline and schemas.

Use explicit imports from submodules to avoid circular import issues:
    from visual_aiming.core.schemas import Detection, FramePacket
    from visual_aiming.core.pipeline import ModularPipeline
"""

__all__ = [
    "ModularPipeline",
    "AimMeasurement",
    "ControlCommand",
    "Detection",
    "DetectionPacket",
    "FramePacket",
    "PipelineTickResult",
    "Point",
    "PredictedAim",
    "RuntimeMode",
    "SelectedTarget",
]


def __getattr__(name: str):
    """Lazy import to break circular dependency chains."""
    if name == "ModularPipeline":
        from visual_aiming.core.pipeline import ModularPipeline
        return ModularPipeline
    if name in __all__:
        from visual_aiming.core import schemas
        return getattr(schemas, name)
    raise AttributeError(f"module 'visual_aiming.core' has no attribute {name!r}")
