# -*- coding: utf-8 -*-
import ctypes
import math
import random
import time
from typing import Tuple
from utils import ThrottledPrinter   # 确保 utils 模块存在，或注释掉相关行

user32 = ctypes.windll.user32
MOUSEEVENTF_MOVE = 0x0001

def send_relative_move(dx: int, dy: int):
    """发送相对鼠标移动事件"""
    user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)

def get_cursor_pos() -> Tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

class MouseController:
    def __init__(self, config):
        self.config = config
        self.last_move_time = 0
        # 如果 utils.ThrottledPrinter 不可用，可以替换为简单的 print 或注释
        try:
            self.printer = ThrottledPrinter(2.0)
        except:
            self.printer = None

    def move_towards(self, target_pos: Tuple[int, int]):
        """将鼠标从当前位置向目标绝对坐标移动（相对移动，带步长限制）"""
        cur_x, cur_y = get_cursor_pos()
        dx = target_pos[0] - cur_x
        dy = target_pos[1] - cur_y
        dist = math.hypot(dx, dy)

        # 死区：距离小于阈值不移动
        if dist <= self.config.aim_deadzone:
            return

        # 可选：打印调试信息（限制频率）
        now = time.time()
        if now - self.last_move_time > 0.5:
            if self.printer:
                self.printer.print("move_target", f"移动鼠标至: {target_pos} (dist={dist:.1f})")
            else:
                print(f"移动鼠标至: {target_pos} (dist={dist:.1f})")
            self.last_move_time = now

        # 计算本次移动的偏移量（绝对值受 recoil_max_step 限制）
        move_x = dx
        move_y = dy
        max_step = self.config.recoil_max_step
        move_x = max(-max_step, min(max_step, move_x))
        move_y = max(-max_step, min(max_step, move_y))

        # 额外抖动（建议设为0，让瞄准点计算层的抖动负责自然运动）
        jitter = getattr(self.config, 'jitter_range', 0)
        move_x += random.uniform(-jitter, jitter)
        move_y += random.uniform(-jitter, jitter)

        noise_std = getattr(self.config, 'noise_std', 0)
        move_x += random.gauss(0, noise_std)
        move_y += random.gauss(0, noise_std)

        send_relative_move(int(move_x), int(move_y))
