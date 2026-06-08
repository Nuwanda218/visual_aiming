# -*- coding: utf-8 -*-
"""Port protocols — the contracts that adapters must satisfy."""

from visual_aiming.ports.detector import Detector
from visual_aiming.ports.diagnostics import DiagnosticsSink
from visual_aiming.ports.frame_source import FrameSource
from visual_aiming.ports.output import OutputBackend

__all__ = ["Detector", "DiagnosticsSink", "FrameSource", "OutputBackend"]
