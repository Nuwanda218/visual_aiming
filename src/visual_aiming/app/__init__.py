# -*- coding: utf-8 -*-
"""Application-level composition and runners."""

__all__ = ["create_output_backend", "create_pipeline", "run_replay", "run_video_file"]


def __getattr__(name: str):
    if name in ("create_output_backend", "create_pipeline"):
        from visual_aiming.app import realtime
        return getattr(realtime, name)
    if name in ("run_replay", "run_video_file"):
        from visual_aiming.app import replay
        return getattr(replay, name)
    raise AttributeError(f"module 'visual_aiming.app' has no attribute {name!r}")
