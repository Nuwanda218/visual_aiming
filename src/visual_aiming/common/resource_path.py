# -*- coding: utf-8 -*-
import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径，处理 PyInstaller 打包后的路径问题。

    在开发环境中，返回项目根目录下的资源路径。
    在打包后的 exe 中，返回临时解压目录下的资源路径（sys._MEIPASS）。

    Args:
        relative_path: 相对于项目根目录的资源路径，例如 "models/best.pt"

    Returns:
        资源文件的绝对路径
    """
    requested_path = Path(relative_path)
    if requested_path.is_absolute():
        return str(requested_path.resolve())

    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parents[3]
    return str((base_path / requested_path).resolve())
