# -*- coding: utf-8 -*-
import time
import threading
from typing import Optional, Tuple
from pynput import keyboard, mouse

class WakeUpModule:
    def __init__(self, config):
        self.config = config
        self.shift_pressed = False
        self.right_pressed = False
        self.left_held = False
        self.active = False
        self.exit_flag = False
        self.calibrated_crosshair: Optional[Tuple[int, int]] = None
        self.default_crosshair: Optional[Tuple[int, int]] = None   # 新增：预设准星（屏幕中心）
        self.fixed_roi_offset: Optional[Tuple[int, int]] = None
        self.lock = threading.Lock()
        self.ctrl_pressed = False

        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click
        )
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def set_fixed_roi_offset(self, offset: Tuple[int, int]):
        with self.lock:
            self.fixed_roi_offset = offset

    def set_default_crosshair(self, x: int, y: int):
        """外部设置默认准星坐标（例如屏幕中心）"""
        with self.lock:
            self.default_crosshair = (x, y)
            # 如果尚未校准，直接使用默认值
            if self.calibrated_crosshair is None:
                self.calibrated_crosshair = (x, y)
                print(f"[{time.strftime('%H:%M:%S')}] 已设置默认准星: ({x}, {y})")

    def _on_key_press(self, key):
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                with self.lock:
                    self.ctrl_pressed = True
            elif hasattr(key, 'char') and key.char is not None and key.char.lower() == 'q':
                with self.lock:
                    if self.ctrl_pressed:
                        self.exit_flag = True
            elif key == keyboard.Key.shift:
                with self.lock:
                    self.shift_pressed = True
        except Exception:
            pass

    def _on_key_release(self, key):
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                with self.lock:
                    self.ctrl_pressed = False
            elif key == keyboard.Key.shift:
                with self.lock:
                    self.shift_pressed = False
                    if self.active:
                        self.active = False
                        print(f"[{time.strftime('%H:%M:%S')}] 辅助已停用 (Shift 释放)")
        except Exception:
            pass

    def _on_mouse_click(self, x, y, button, pressed):
        if button == mouse.Button.left:
            with self.lock:
                self.left_held = pressed
                if pressed and self.shift_pressed and self.right_pressed and not self.active:
                    # 优先使用预设的默认准星（屏幕中心），如果没有则降级使用鼠标位置（兼容旧逻辑）
                    if self.default_crosshair is not None:
                        self.calibrated_crosshair = self.default_crosshair
                    else:
                        self.calibrated_crosshair = (x, y)
                    self.active = True
                    print(f"[{time.strftime('%H:%M:%S')}] 辅助已激活 | 准星: {self.calibrated_crosshair}")
        elif button == mouse.Button.right:
            with self.lock:
                if pressed:
                    self.right_pressed = True
                else:
                    self.right_pressed = False
                    if self.active:
                        self.active = False
                        print(f"[{time.strftime('%H:%M:%S')}] 辅助已停用 (右键释放)")

    def get_active(self) -> bool:
        with self.lock:
            return self.active

    def get_left_held(self) -> bool:
        with self.lock:
            return self.left_held

    def get_crosshair(self) -> Optional[Tuple[int, int]]:
        with self.lock:
            return self.calibrated_crosshair

    def get_roi_offset(self) -> Optional[Tuple[int, int]]:
        with self.lock:
            return self.fixed_roi_offset

    def should_exit(self) -> bool:
        with self.lock:
            return self.exit_flag

    def stop(self):
        self.keyboard_listener.stop()
        self.mouse_listener.stop()