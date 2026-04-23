# -*- coding: utf-8 -*-
import math
import cv2
import numpy as np
from typing import Optional, Tuple

class AimPointCalculator:
    def __init__(self, config):
        self.config = config
        self.wakeup = None
        self.locked_aim = None
        self.track_lost_frames = 0
        self._prev_aim_global = None
        self._velocity = (0, 0)
        self.smooth_factor = getattr(config, 'aim_smooth_factor', 0.7)
        self.max_move_per_frame = getattr(config, 'aim_max_move_per_frame', 50)
        self.head_bias = getattr(config, 'head_bias', 0.25)
        self.adaptive_head_bias = getattr(config, 'adaptive_head_bias', True)
        self.max_step_pixels = max(1, int(getattr(config, 'max_step_pixels', 10)))
        self.unlock_distance = max(0, int(getattr(config, 'unlock_distance', 50)))
        self.max_track_lost = max(0, int(getattr(config, 'max_track_lost', 5)))
        self.firing_follow_x = float(getattr(config, 'firing_follow_x', 0.45))
        self.firing_follow_y = float(getattr(config, 'firing_follow_y', 0.65))
        self.firing_vertical_boost = float(getattr(config, 'firing_vertical_boost', 1.6))

    def set_wakeup(self, wakeup):
        self.wakeup = wakeup

    def calculate(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        if self.wakeup is not None:
            active = self.wakeup.get_active()
            left_held = self.wakeup.get_left_held()
            if left_held and active:
                return self._calculate_during_firing(target, roi_left, roi_top)
            else:
                self._reset_firing_lock()

        if target is None or target.contour is None or len(target.contour) == 0:
            self._prev_aim_global = None
            return None

        raw_aim = self._compute_raw_aim(target, roi_left, roi_top)
        if raw_aim is None:
            self._prev_aim_global = None
            return None

        smoothed_aim = self._smooth_aim(raw_aim)
        return smoothed_aim

    def _calculate_during_firing(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        if target is None or target.contour is None or len(target.contour) == 0:
            self.track_lost_frames += 1
            if self.locked_aim is not None and self.track_lost_frames <= self.max_track_lost:
                return self.locked_aim
            self._reset_firing_lock()
            return None

        raw_aim = self._compute_raw_aim(target, roi_left, roi_top)
        if raw_aim is None:
            self.track_lost_frames += 1
            if self.locked_aim is not None and self.track_lost_frames <= self.max_track_lost:
                return self.locked_aim
            self._reset_firing_lock()
            return None

        self.track_lost_frames = 0
        if self.locked_aim is None:
            self.locked_aim = raw_aim
            self._prev_aim_global = raw_aim
            return raw_aim

        self.locked_aim = self._follow_locked_aim(raw_aim)
        self._prev_aim_global = self.locked_aim
        return self.locked_aim

    def _follow_locked_aim(self, raw_aim: Tuple[int, int]) -> Tuple[int, int]:
        dx = raw_aim[0] - self.locked_aim[0]
        dy = raw_aim[1] - self.locked_aim[1]
        dist = math.hypot(dx, dy)

        if self.unlock_distance > 0 and dist >= self.unlock_distance:
            return raw_aim

        step_x = self._compute_follow_step(dx, self.firing_follow_x, self.max_step_pixels)

        y_limit = self.max_step_pixels
        if dy > 0:
            y_limit = max(y_limit, int(round(self.max_step_pixels * self.firing_vertical_boost)))
        step_y = self._compute_follow_step(dy, self.firing_follow_y, y_limit)

        next_x = self.locked_aim[0] + step_x
        next_y = self.locked_aim[1] + step_y
        return (next_x, next_y)

    def _compute_follow_step(self, delta: int, follow_factor: float, max_step: int) -> int:
        if delta == 0:
            return 0

        scaled_step = int(round(delta * follow_factor))
        if scaled_step == 0:
            scaled_step = 1 if delta > 0 else -1

        return max(-max_step, min(max_step, scaled_step))

    def _reset_firing_lock(self):
        self.locked_aim = None
        self.track_lost_frames = 0
        self._prev_aim_global = None
        self._velocity = (0, 0)

    def _compute_max_rectangle_in_convex_hull(self, hull):
        """在凸包内寻找最大的轴对齐矩形（优化版）"""
        # 计算凸包的边界框
        hull_x, hull_y, hull_w, hull_h = cv2.boundingRect(hull)
        
        # 初始化最大矩形
        max_area = 0
        best_rect = None
        
        # 优化采样步长，根据凸包大小动态调整
        min_dim = min(hull_w, hull_h)
        step = max(2, min_dim // 15)  # 增大步长，减少计算量
        
        # 限制搜索范围，只在凸包中心区域搜索
        center_x = hull_x + hull_w // 2
        center_y = hull_y + hull_h // 2
        search_radius = min(hull_w, hull_h) // 2
        start_x = max(hull_x, center_x - search_radius)
        end_x = min(hull_x + hull_w, center_x + search_radius)
        start_y = max(hull_y, center_y - search_radius)
        end_y = min(hull_y + hull_h, center_y + search_radius)
        
        # 遍历可能的矩形左上角（只在中心区域）
        for x in range(start_x, end_x - step, step):
            for y in range(start_y, end_y - step, step):
                # 限制宽度和高度的范围，避免不必要的计算
                max_possible_w = min(hull_x + hull_w - x, search_radius * 2)
                max_possible_h = min(hull_y + hull_h - y, search_radius * 2)
                
                # 尝试不同的宽度和高度，使用较大的步长
                for w in range(step * 2, max_possible_w, step):
                    for h in range(step * 2, max_possible_h, step):
                        # 快速检查：如果面积不可能超过当前最大值，跳过
                        current_area = w * h
                        if current_area <= max_area:
                            continue
                        
                        # 检查矩形的四个角是否都在凸包内
                        points = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
                        all_inside = True
                        for point in points:
                            # 使用快速点-in-多边形测试
                            if cv2.pointPolygonTest(hull, point, False) < 0:
                                all_inside = False
                                break
                        
                        if all_inside:
                            if current_area > max_area:
                                max_area = current_area
                                best_rect = (x, y, w, h)
        
        # 如果没有找到，使用凸包的边界框作为 fallback
        if best_rect is None:
            best_rect = (hull_x, hull_y, hull_w, hull_h)
        
        return best_rect
    
    def _compute_raw_aim(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        x, y, w, h = target.bbox
        contour = target.contour
        
        # 主要算法：在凸包内寻找最大矩形作为瞄准点的计算基础
        try:
            print("[DEBUG] 使用凸包内最大矩形算法计算瞄准点")
            # 1. 计算凸包
            hull = cv2.convexHull(contour)
            print(f"[DEBUG] 凸包顶点数: {len(hull)}")
            
            # 2. 在凸包内寻找最大矩形
            max_rect = self._compute_max_rectangle_in_convex_hull(hull)
            
            if max_rect is not None:
                mx, my, mw, mh = max_rect
                print(f"[DEBUG] 凸包内最大矩形: x={mx}, y={my}, w={mw}, h={mh}, area={mw*mh}")
                
                # 3. 确保最大矩形有效
                if mw > 20 and mh > 30:  # 确保足够大的矩形
                    # 4. 在最大矩形中选择由上到下比例为0.4的位置
                    aim_x = mx + mw // 2  # 水平居中
                    aim_y = my + int(mh * 0.4)  # 垂直位置为矩形的40%处
                    
                    print(f"[DEBUG] 计算的瞄准点: ({aim_x}, {aim_y})")
                    
                    # 5. 确保瞄准点在原始轮廓内
                    if cv2.pointPolygonTest(contour, (aim_x, aim_y), False) >= 0:
                        new_aim = (roi_left + aim_x, roi_top + aim_y)
                        print(f"[DEBUG] 最终瞄准点: ({new_aim[0]}, {new_aim[1]}) - 使用凸包内最大矩形")
                        self._prev_aim_global = new_aim
                        return new_aim
                    else:
                        print("[DEBUG] 瞄准点不在轮廓内")
                else:
                    print("[DEBUG] 最大矩形尺寸太小")
            else:
                print("[DEBUG] 未找到凸包内的最大矩形")
        except Exception as e:
            print(f"[DEBUG] 凸包内最大矩形算法错误: {e}")
            import traceback
            traceback.print_exc()
            pass
        
        # Fallback: 使用原始外切矩形的40%位置
        print("[DEBUG] 使用外切矩形计算瞄准点")
        aim_x = x + w // 2
        aim_y = y + int(h * 0.4)
        if cv2.pointPolygonTest(contour, (aim_x, aim_y), False) >= 0:
            new_aim = (roi_left + aim_x, roi_top + aim_y)
            print(f"[DEBUG] 最终瞄准点: ({new_aim[0]}, {new_aim[1]}) - 使用外切矩形")
            self._prev_aim_global = new_aim
            return new_aim

        # 最终 Fallback: 使用质心
        print("[DEBUG] 使用质心计算瞄准点")
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            if cv2.pointPolygonTest(contour, (cx, cy), False) >= 0:
                new_aim = (roi_left + cx, roi_top + cy)
                print(f"[DEBUG] 最终瞄准点: ({new_aim[0]}, {new_aim[1]}) - 使用质心")
                self._prev_aim_global = new_aim
                return new_aim

        print("[DEBUG] 未找到有效的瞄准点")
        return None

    def _get_adaptive_head_bias(self, target) -> float:
        if not self.adaptive_head_bias:
            return self.head_bias

        ar = target.aspect_ratio
        if ar > 1.5:
            return 0.15  # 瘦高目标（站立）
        elif ar > 1.0:
            return 0.20  # 中等目标（蹲下）
        elif ar > 0.7:
            return 0.25  # 稍矮目标
        else:
            return 0.30  # 宽矮目标（趴下）

    def _smooth_aim(self, raw_aim: Tuple[int, int]) -> Tuple[int, int]:
        if self._prev_aim_global is None:
            self._prev_aim_global = raw_aim
            self._velocity = (0, 0)
            return raw_aim

        dx = raw_aim[0] - self._prev_aim_global[0]
        dy = raw_aim[1] - self._prev_aim_global[1]

        # 更平滑的速度计算
        alpha = 0.3  # 降低 alpha 以减少抖动
        self._velocity = (alpha * dx + (1 - alpha) * self._velocity[0],
                          alpha * dy + (1 - alpha) * self._velocity[1])

        # 限制速度
        vel_magnitude = (self._velocity[0] ** 2 + self._velocity[1] ** 2) ** 0.5
        if vel_magnitude > self.max_move_per_frame and self.max_move_per_frame > 0:
            scale = self.max_move_per_frame / vel_magnitude
            self._velocity = (self._velocity[0] * scale, self._velocity[1] * scale)

        # 应用平滑因子
        smoothed_aim = (self._prev_aim_global[0] + int(self._velocity[0] * self.smooth_factor),
                        self._prev_aim_global[1] + int(self._velocity[1] * self.smooth_factor))

        self._prev_aim_global = smoothed_aim
        return smoothed_aim
