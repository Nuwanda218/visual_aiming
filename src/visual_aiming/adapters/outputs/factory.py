from __future__ import annotations

from typing import Callable, Optional

from visual_aiming.adapters.outputs.log_output import LogOutput
from visual_aiming.adapters.outputs.null_output import NullOutput
from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput
from visual_aiming.config.schema import OutputConfig


def create_output_backend(output_config: OutputConfig, mouse_sender: Optional[Callable[[int, int], None]] = None):
    if output_config.backend == "log":
        return LogOutput(output_config.log_path or None)
    if output_config.backend == "win_mouse" and output_config.enable_real_mouse:
        return WinMouseOutput(enable_real_mouse=True, sender=mouse_sender)
    return NullOutput()


def create_real_mouse_output_backend(mouse_sender: Optional[Callable[[int, int], None]] = None):
    return create_output_backend(
        OutputConfig(backend="win_mouse", enable_real_mouse=True),
        mouse_sender=mouse_sender,
    )
