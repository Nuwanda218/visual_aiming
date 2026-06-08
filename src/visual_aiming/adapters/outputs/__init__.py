# -*- coding: utf-8 -*-
"""Output backend adapters."""

__all__ = ["LogOutput", "NullOutput", "WinMouseOutput"]


def __getattr__(name: str):
    if name == "LogOutput":
        from visual_aiming.adapters.outputs.log_output import LogOutput
        return LogOutput
    if name == "NullOutput":
        from visual_aiming.adapters.outputs.null_output import NullOutput
        return NullOutput
    if name == "WinMouseOutput":
        from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput
        return WinMouseOutput
    raise AttributeError(f"module 'visual_aiming.adapters.outputs' has no attribute {name!r}")
