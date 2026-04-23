# -*- coding: utf-8 -*-
import cv2
import numpy as np
from typing import Optional, Tuple

class DebugVisualizer:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.window_name = "Debug - Real-time Detection"
        if self.enabled:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
            # 设置窗口位置到屏幕 (10, 1352)，大小保持 50%
            scale = 0.5  # 缩小到 50%
            window_width = int(410 * scale)  # ROI 宽度 * 缩放比例
            window_height = int(315 * scale)  # ROI 高度 * 缩放比例
            
            # 左下角对准 (10, 1352) 像素位置
            x = 10  # 左边距
            y = 1357-240  # 底边距（窗口左下角）
            
            cv2.moveWindow(self.window_name, x, y)
            cv2.resizeWindow(self.window_name, window_width, window_height)

    def update(self, frame: np.ndarray, contour: Optional[np.ndarray],
               aim_point: Optional[Tuple[int, int]],
               calibrate_point: Tuple[int, int],
               roi_left: int, roi_top: int,
               bbox: Optional[Tuple[int, int, int, int]] = None):
        if not self.enabled:
            return

        disp = frame.copy()
        h, w = disp.shape[:2]

        # 1. 绘制原始轮廓（绿色）
        if contour is not None:
            cv2.drawContours(disp, [contour], -1, (0, 255, 0), 2)

        # 2. 绘制最外层矩形边框（黄色）
        if bbox is not None:
            bx, by, bw, bh = bbox
            cv2.rectangle(disp, (bx, by), (bx + bw, by + bh), (255, 255, 0), 2)
            cv2.putText(disp, "Outer", (bx, by - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            
            # 3. 绘制凸包多边形（紫色）
            try:
                if contour is not None:
                    hull = cv2.convexHull(contour)
                    cv2.drawContours(disp, [hull], -1, (255, 0, 255), 2)
                    cv2.putText(disp, "Convex Hull", (hull[0][0][0], hull[0][0][1] - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)
                    
                    # 4. 绘制凸包的内接矩形（青色）
                    # 计算凸包的边界框
                    hull_x, hull_y, hull_w, hull_h = cv2.boundingRect(hull)
                    # 使用青色绘制，更明显
                    cv2.rectangle(disp, (hull_x, hull_y), (hull_x + hull_w, hull_y + hull_h), (0, 255, 255), 2, cv2.LINE_AA)
                    cv2.putText(disp, "Hull BBox", (hull_x, hull_y - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
                    
                    # 打印凸包内接矩形信息
                    print(f"[DEBUG] 凸包内接矩形: x={hull_x}, y={hull_y}, w={hull_w}, h={hull_h}")
                    
                    # 5. 绘制凸包内的最大矩形（红色，瞄准点确认矩形）
                    # 实现优化版的最大矩形查找算法
                    def compute_max_rectangle_in_convex_hull(hull):
                        hull_x, hull_y, hull_w, hull_h = cv2.boundingRect(hull)
                        max_area = 0
                        best_rect = None
                        
                        # 优化采样步长
                        min_dim = min(hull_w, hull_h)
                        step = max(3, min_dim // 12)  # 更大的步长，减少计算量
                        
                        # 限制搜索范围
                        center_x = hull_x + hull_w // 2
                        center_y = hull_y + hull_h // 2
                        search_radius = min(hull_w, hull_h) // 2
                        start_x = max(hull_x, center_x - search_radius)
                        end_x = min(hull_x + hull_w, center_x + search_radius)
                        start_y = max(hull_y, center_y - search_radius)
                        end_y = min(hull_y + hull_h, center_y + search_radius)
                        
                        # 简化搜索：只尝试几个可能的矩形大小
                        # 尝试不同的宽度
                        for w in range(step * 3, search_radius * 2, step * 2):
                            # 尝试不同的高度
                            for h in range(step * 3, search_radius * 2, step * 2):
                                # 计算矩形中心位置
                                x = center_x - w // 2
                                y = center_y - h // 2
                                
                                # 确保矩形在凸包边界内
                                if x < hull_x or y < hull_y or x + w > hull_x + hull_w or y + h > hull_y + hull_h:
                                    continue
                                
                                # 检查矩形的四个角是否都在凸包内
                                points = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
                                all_inside = True
                                for point in points:
                                    if cv2.pointPolygonTest(hull, point, False) < 0:
                                        all_inside = False
                                        break
                                
                                if all_inside:
                                    area = w * h
                                    if area > max_area:
                                        max_area = area
                                        best_rect = (x, y, w, h)
                        
                        # 如果没有找到，使用凸包的边界框作为 fallback
                        if best_rect is None:
                            best_rect = (hull_x, hull_y, hull_w, hull_h)
                        
                        return best_rect
                    
                    # 计算凸包内的最大矩形（使用优化算法）
                    max_rect = compute_max_rectangle_in_convex_hull(hull)
                    
                    if max_rect is not None:
                        mx, my, mw, mh = max_rect
                        # 绘制最大矩形（红色）
                        cv2.rectangle(disp, (mx, my), (mx + mw, my + mh), (0, 0, 255), 2, cv2.LINE_AA)
                        cv2.putText(disp, "Max Rect", (mx, my - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                        
                        # 6. 绘制瞄准点位置（蓝色十字）
                        aim_x = mx + mw // 2
                        aim_y = my + int(mh * 0.4)
                        cv2.drawMarker(disp, (aim_x, aim_y), (255, 0, 0), cv2.MARKER_CROSS, 10, 2)
                        cv2.putText(disp, "Aim", (aim_x + 5, aim_y - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
            except Exception as e:
                pass

        if aim_point is not None:
            ax = aim_point[0] - roi_left
            ay = aim_point[1] - roi_top
            if 0 <= ax < w and 0 <= ay < h:
                cv2.circle(disp, (ax, ay), 4, (0, 0, 255), -1)
                cv2.putText(disp, "Aim", (ax+5, ay-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

        if calibrate_point is not None:
            cx = calibrate_point[0] - roi_left
            cy = calibrate_point[1] - roi_top
            if 0 <= cx < w and 0 <= cy < h:
                cv2.drawMarker(disp, (cx, cy), (255, 0, 0), cv2.MARKER_CROSS, 10, 2)
                cv2.putText(disp, "Calibrate", (cx+5, cy-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)

        cv2.imshow(self.window_name, disp)
        key = cv2.waitKey(1)
        if key == 27:
            cv2.destroyWindow(self.window_name)
            self.enabled = False