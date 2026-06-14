from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):
    ANALYZE_LOG = "analyze_log"
    VIDEO_TEST = "video_test"
    MODULAR_REPLAY = "modular_replay"
    MODULAR_REALTIME = "modular_realtime"
    LEGACY_REALTIME = "legacy_realtime"


def choose_runtime_mode(args) -> RuntimeMode:
    if getattr(args, "analyze_log", ""):
        return RuntimeMode.ANALYZE_LOG
    if getattr(args, "video_test", False):
        return RuntimeMode.VIDEO_TEST
    if getattr(args, "modular", False) and getattr(args, "video", ""):
        return RuntimeMode.MODULAR_REPLAY
    if getattr(args, "modular", False):
        return RuntimeMode.MODULAR_REALTIME
    return RuntimeMode.LEGACY_REALTIME
