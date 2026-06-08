# -*- coding: utf-8 -*-
"""Port protocols — the contracts that adapters must satisfy."""

__all__ = ["Detector", "DiagnosticsSink", "FrameSource", "OutputBackend"]


def __getattr__(name: str):
    if name == "Detector":
        from visual_aiming.ports.detector import Detector
        return Detector
    if name == "DiagnosticsSink":
        from visual_aiming.ports.diagnostics import DiagnosticsSink
        return DiagnosticsSink
    if name == "FrameSource":
        from visual_aiming.ports.frame_source import FrameSource
        return FrameSource
    if name == "OutputBackend":
        from visual_aiming.ports.output import OutputBackend
        return OutputBackend
    raise AttributeError(f"module 'visual_aiming.ports' has no attribute {name!r}")
