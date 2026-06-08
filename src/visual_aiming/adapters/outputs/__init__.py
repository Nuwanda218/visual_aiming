# -*- coding: utf-8 -*-
"""Output backend adapters."""

from visual_aiming.adapters.outputs.log_output import LogOutput
from visual_aiming.adapters.outputs.null_output import NullOutput
from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput

__all__ = ["LogOutput", "NullOutput", "WinMouseOutput"]
