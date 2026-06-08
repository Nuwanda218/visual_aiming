# -*- coding: utf-8 -*-
"""Modular algorithm implementations.

Use explicit imports from submodules:
    from visual_aiming.algorithms.aim_point import AimStrategy
    from visual_aiming.algorithms.control import RelativeController
"""

__all__ = ["AimStrategy", "AlphaBetaPredictor", "RelativeController", "TargetSelector"]


def __getattr__(name: str):
    if name == "AimStrategy":
        from visual_aiming.algorithms.aim_point import AimStrategy
        return AimStrategy
    if name == "AlphaBetaPredictor":
        from visual_aiming.algorithms.prediction import AlphaBetaPredictor
        return AlphaBetaPredictor
    if name == "RelativeController":
        from visual_aiming.algorithms.control import RelativeController
        return RelativeController
    if name == "TargetSelector":
        from visual_aiming.algorithms.target_selection import TargetSelector
        return TargetSelector
    raise AttributeError(f"module 'visual_aiming.algorithms' has no attribute {name!r}")
