# -*- coding: utf-8 -*-
"""
颜色阈值调试工具
用于手动调整人物检测的 RGB 颜色阈值
"""

import cv2
import numpy as np
import mss
import time

class ColorThresholdTuner:
    def __init__(self):
        # 默认阈值（基于用户提供的图片）
        self.r_min = 100
        self.r_max = 255
        self.g_min = 40
        self.g_max = 200
        self.b_min = 0
        self.b_max = 120
        
        # 屏幕捕获设置
        self.roi_width = 300
        self.roi_height = 300
        
        # 初始化窗口
        cv2.namedWindow('Color Threshold Tuner', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Color Threshold Tuner', 800, 600)
        
        # 创建滑块
        cv2.createTrackbar('R Min', 'Color Threshold Tuner', self.r_min, 255, self._on_r_min_change)
        cv2.createTrackbar('R Max', 'Color Threshold Tuner', self.r_max, 255, self._on_r_max_change)
        cv2.createTrackbar('G Min', 'Color Threshold Tuner', self.g_min, 255, self._on_g_min_change)
        cv2.createTrackbar('G Max', 'Color Threshold Tuner', self.g_max, 255, self._on_g_max_change)
        cv2.createTrackbar('B Min', 'Color Threshold Tuner', self.b_min, 255, self._on_b_min_change)
        cv2.createTrackbar('B Max', 'Color Threshold Tuner', self.b_max, 255, self._on_b_max_change)
    
    def _on_r_min_change(self, val):
        self.r_min = val
    
    def _on_r_max_change(self, val):
        self.r_max = val
    
    def _on_g_min_change(self, val):
        self.g_min = val
    
    def _on_g_max_change(self, val):
        self.g_max = val
    
    def _on_b_min_change(self, val):
        self.b_min = val
    
    def _on_b_max_change(self, val):
        self.b_max = val
    
    def capture_screen(self):
        """使用静态图片"""
        # 加载静态图片
        frame = cv2.imread('thermal.png')
        
        if frame is None:
            print("无法加载 thermal.png 文件")
            # 创建一个默认的黑色图像
            frame = np.zeros((300, 300, 3), dtype=np.uint8)
        else:
            # 调整图片大小以适应窗口
            frame = cv2.resize(frame, (self.roi_width, self.roi_height))
        
        return frame
    
    def apply_threshold(self, frame):
        """应用颜色阈值"""
        # 分离 BGR 通道
        b, g, r = cv2.split(frame)
        
        # 生成掩码
        mask = ((r >= self.r_min) & (r <= self.r_max) &
                (g >= self.g_min) & (g <= self.g_max) &
                (b >= self.b_min) & (b <= self.b_max)).astype(np.uint8) * 255
        
        # 形态学处理
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.medianBlur(mask, 3)
        
        return mask
    
    def run(self):
        """运行调试工具"""
        print("颜色阈值调试工具")
        print("使用方法：")
        print("1. 调整滑块以获得最佳掩码效果")
        print("2. 按 's' 保存当前参数")
        print("3. 按 'q' 退出")
        print("\n当前参数：")
        
        while True:
            # 捕获屏幕
            frame = self.capture_screen()
            
            # 应用阈值
            mask = self.apply_threshold(frame)
            
            # 转换掩码为彩色
            mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            
            # 水平拼接原始图像和掩码
            combined = np.hstack((frame, mask_color))
            
            # 显示参数信息
            params = f"R: {self.r_min}-{self.r_max}, G: {self.g_min}-{self.g_max}, B: {self.b_min}-{self.b_max}"
            cv2.putText(combined, params, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # 显示
            cv2.imshow('Color Threshold Tuner', combined)
            
            # 键盘事件
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                # 保存参数
                with open('color_thresholds.txt', 'w') as f:
                    f.write(f"R_MIN = {self.r_min}\n")
                    f.write(f"R_MAX = {self.r_max}\n")
                    f.write(f"G_MIN = {self.g_min}\n")
                    f.write(f"G_MAX = {self.g_max}\n")
                    f.write(f"B_MIN = {self.b_min}\n")
                    f.write(f"B_MAX = {self.b_max}\n")
                print(f"参数已保存到 color_thresholds.txt: {params}")
            
            # 打印当前参数（每10帧）
            if int(time.time() * 10) % 10 == 0:
                print(f"当前参数: {params}", end='\r')
        
        cv2.destroyAllWindows()

if __name__ == "__main__":
    tuner = ColorThresholdTuner()
    tuner.run()