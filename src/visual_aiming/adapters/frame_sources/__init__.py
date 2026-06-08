# -*- coding: utf-8 -*-
"""Frame source adapters."""

__all__ = ["ArrayFrameSource", "VideoFileFrameSource"]


def __getattr__(name: str):
    if name in ("ArrayFrameSource", "VideoFileFrameSource"):
        from visual_aiming.adapters.frame_sources.video_file import ArrayFrameSource, VideoFileFrameSource
        return ArrayFrameSource if name == "ArrayFrameSource" else VideoFileFrameSource
    raise AttributeError(f"module 'visual_aiming.adapters.frame_sources' has no attribute {name!r}")
