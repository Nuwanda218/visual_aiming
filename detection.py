# -*- coding: utf-8 -*-
import math
import cv2
import numpy as np
from typing import Optional, Tuple
from config import Config

class DetectedTarget:
    def __init__(self, contour: Optional[np.ndarray], bbox: Tuple[int, int, int, int]):
        self.contour = contour
        self.bbox = bbox

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    @property
    def center_x(self) -> int:
        return self.bbox[0] + self.bbox[2] // 2

    @property
    def center_y(self) -> int:
        return self.bbox[1] + self.bbox[3] // 2

    @property
    def aspect_ratio(self) -> float:
        return self.bbox[3] / self.bbox[2] if self.bbox[2] > 0 else 0

    @property
    def area(self) -> float:
        if self.contour is not None:
            return cv2.contourArea(self.contour)
        return self.bbox[2] * self.bbox[3]

class TargetDetector:
    # 人物颜色 RGB 范围（基于调试工具的最佳参数）
    PERSON_R_MIN = 96
    PERSON_R_MAX = 226
    PERSON_G_MIN = 91
    PERSON_G_MAX = 255
    PERSON_B_MIN = 0
    PERSON_B_MAX = 164

    # 绿色瞄准标记 RGB 范围（用于剔除）
    GREEN_R_MIN = 50
    GREEN_R_MAX = 80
    GREEN_G_MIN = 200
    GREEN_G_MAX = 255
    GREEN_B_MIN = 100
    GREEN_B_MAX = 150

    def __init__(self):
        self.debug_window = False

    def set_debug(self, enabled: bool):
        self.debug_window = enabled
        if enabled:
            cv2.namedWindow("Debug - Detection", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty("Debug - Detection", cv2.WND_PROP_TOPMOST, 1)
            # 设置窗口位置到屏幕 (10, 1470)，大小保持 50%
            scale = 0.5  # 缩小到 50%
            window_width = int(410 * 2 * scale)  # ROI 宽度 * 2 * 缩放比例
            window_height = int(315 * scale)  # ROI 高度 * 缩放比例
            
            # 左下角对准 (10, 1470) 像素位置
            x = 10  # 左边距
            y = 1470-197  # 底边距（窗口左下角）
            
            cv2.moveWindow("Debug - Detection", x, y)
            cv2.resizeWindow("Debug - Detection", window_width, window_height)

    def detect(self, frame_bgr: np.ndarray, config: Config,
               roi_center: Tuple[int, int]) -> Optional[DetectedTarget]:
        """
        基于固定 RGB 阈值检测人物轮廓。
        """
        # 分离 BGR 通道
        b, g, r = cv2.split(frame_bgr)

        # 生成人物 mask（满足 RGB 范围）
        person_mask = ((r >= self.PERSON_R_MIN) & (r <= self.PERSON_R_MAX) &
                       (g >= self.PERSON_G_MIN) & (g <= self.PERSON_G_MAX) &
                       (b >= self.PERSON_B_MIN) & (b <= self.PERSON_B_MAX)).astype(np.uint8) * 255

        # 调试：计算 mask 中白色像素数量
        white_pixels = cv2.countNonZero(person_mask)
        total_pixels = person_mask.shape[0] * person_mask.shape[1]
        print(f"[DEBUG] 人物 mask: {white_pixels}/{total_pixels} 像素 ({white_pixels/total_pixels*100:.1f}%)")

        # 剔除绿色瞄准标记（覆盖在人物身上的绿色圈）
        green_mask = ((r >= self.GREEN_R_MIN) & (r <= self.GREEN_R_MAX) &
                      (g >= self.GREEN_G_MIN) & (g <= self.GREEN_G_MAX) &
                      (b >= self.GREEN_B_MIN) & (b <= self.GREEN_B_MAX)).astype(np.uint8) * 255
        person_mask = cv2.bitwise_and(person_mask, cv2.bitwise_not(green_mask))

        # 形态学处理：闭运算填充空洞，开运算去除噪声
        kernel = np.ones((config.morph_kernel_size, config.morph_kernel_size), np.uint8)
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_CLOSE, kernel)
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_OPEN, kernel)

        # 中值滤波去除孤立噪点
        person_mask = cv2.medianBlur(person_mask, 3)

        # 查找轮廓
        contours, _ = cv2.findContours(person_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        print(f"[DEBUG] 找到轮廓数量: {len(contours)}")
        if not contours:
            if self.debug_window:
                self._show_debug(frame_bgr, person_mask, [], None)
            return None

        # 轮廓筛选：面积和宽高比
        min_area = max(50, config.min_contour_area)  # 进一步降低最小面积阈值
        max_area = config.roi_width * config.roi_height * 0.8
        valid_targets = []
        for i, c in enumerate(contours):
            area = cv2.contourArea(c)
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = h / w if w > 0 else 0
            print(f"[DEBUG] 轮廓 {i}: 面积={area:.1f}, 宽高比={aspect_ratio:.2f}, 位置=({x},{y},{w},{h})")
            if min_area <= area <= max_area:
                if 0.1 <= aspect_ratio <= 3.0:  # 进一步放宽宽高比范围
                    valid_targets.append(DetectedTarget(c, (x, y, w, h)))

        print(f"[DEBUG] 有效目标数量: {len(valid_targets)}")
        if not valid_targets:
            if self.debug_window:
                self._show_debug(frame_bgr, person_mask, contours, None)
            return None

        # 选择离 ROI 中心（准星位置）最近的轮廓
        cx_center, cy_center = roi_center
        best_target = None
        best_dist = float('inf')
        for target in valid_targets:
            dist = (target.center_x - cx_center) ** 2 + (target.center_y - cy_center) ** 2
            if dist < best_dist:
                best_dist = dist
                best_target = target

        if self.debug_window:
            self._show_debug(frame_bgr, person_mask, [t.contour for t in valid_targets], best_target)

        return best_target

    def _show_debug(self, frame: np.ndarray, mask: np.ndarray, contours: list, target: Optional[DetectedTarget]):
        """显示调试窗口"""
        # 创建调试图像
        debug_img = frame.copy()
        
        # 显示 mask（转换为彩色）
        mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mask_color = cv2.resize(mask_color, (debug_img.shape[1], debug_img.shape[0]))
        
        # 水平拼接原始图像和 mask
        combined = np.hstack((debug_img, mask_color))
        
        # 绘制所有轮廓
        for i, c in enumerate(contours):
            x, y, w, h = cv2.boundingRect(c)
            cv2.drawContours(combined, [c], -1, (0, 255, 0), 2)
            cv2.putText(combined, f"C{i}", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # 绘制最佳目标
        if target is not None:
            x, y, w, h = target.bbox
            cv2.rectangle(combined, (x, y), (x+w, y+h), (0, 0, 255), 2)
            cv2.putText(combined, "Target", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        
        # 显示
        cv2.imshow("Debug - Detection", combined)
        cv2.waitKey(1)
