"""控制执行层 — 瞄准点 Kalman 平滑滤波器。

用 Kalman 滤波器对帧间瞄准点进行平滑，消除检测框尺寸抖动带来的瞄准点跳变。
状态向量 [x, y, vx, vy]，同时估计位置和速度。
"""
from __future__ import annotations

import numpy as np
from typing import Optional


class AimSmoother:
    """瞄准点 Kalman 平滑器。

    每帧接收原始瞄准点 → 输出平滑后的瞄准点。
    目标丢失时用速度继续预测（hold 机制）。
    目标切换时重置滤波器。
    """

    def __init__(
        self,
        process_noise: float = 0.1,
        measurement_noise: float = 1.0,
        hold_frames: int = 5,
    ) -> None:
        self._process_noise = process_noise
        self._measurement_noise = measurement_noise
        self._hold_frames = hold_frames

        # 状态向量 [x, y, vx, vy]
        self._x = np.zeros(4)
        # 协方差矩阵
        self._P = np.eye(4) * 1000.0
        # 状态转移矩阵（匀速模型，dt=1）
        self._F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=float)
        # 观测矩阵（只观测位置）
        self._H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=float)
        # 过程噪声
        self._Q = np.eye(4) * self._process_noise
        # 观测噪声
        self._R = np.eye(2) * self._measurement_noise

        self._initialized = False
        self._hold_count = 0

    def smooth(self, raw_point: Optional[tuple[int, int]]) -> Optional[tuple[int, int]]:
        """输入原始瞄准点，输出平滑后的瞄准点。None 表示目标丢失。"""
        if raw_point is not None:
            self._hold_count = 0
            if not self._initialized:
                # 首次观测：直接初始化状态
                self._x = np.array([raw_point[0], raw_point[1], 0.0, 0.0])
                self._P = np.eye(4) * 10.0
                self._initialized = True
                return raw_point

            # Kalman 预测步
            x_pred = self._F @ self._x
            P_pred = self._F @ self._P @ self._F.T + self._Q

            # Kalman 更新步
            z = np.array([raw_point[0], raw_point[1]], dtype=float)
            y = z - self._H @ x_pred                         # 残差
            S = self._H @ P_pred @ self._H.T + self._R       # 残差协方差
            K = P_pred @ self._H.T @ np.linalg.inv(S)        # Kalman 增益
            self._x = x_pred + K @ y
            self._P = (np.eye(4) - K @ self._H) @ P_pred

            return (int(round(self._x[0])), int(round(self._x[1])))

        # 目标丢失：用速度继续预测
        if not self._initialized:
            return None

        self._hold_count += 1
        if self._hold_count > self._hold_frames:
            return None

        # 只做预测，不更新
        self._x = self._F @ self._x
        self._P = self._F @ self._P @ self._F.T + self._Q
        return (int(round(self._x[0])), int(round(self._x[1])))

    def reset(self) -> None:
        """目标切换或热键停用时重置滤波器。"""
        self._x = np.zeros(4)
        self._P = np.eye(4) * 1000.0
        self._initialized = False
        self._hold_count = 0
