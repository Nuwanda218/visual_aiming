"""交互接入层 — 全局热键监听（pynput 事件驱动）。

激活条件：同时按住 Shift + 右键，然后按左键
停用条件：释放 Shift 或释放右键
退出条件：Ctrl+Q

复用 V1 的 WakeUpModule 逻辑，精简为只保留激活/停用/退出状态。
"""
from __future__ import annotations

import threading
import time

from pynput import keyboard, mouse


class HotkeyListener:
    """全局热键监听器，事件驱动，独立线程运行。

    通过 is_active / should_exit 查询状态，开销为零（只读 bool 变量）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shift_pressed = False
        self._right_pressed = False
        self._left_held = False
        self._ctrl_pressed = False
        self._active = False
        self._exit_flag = False

        # pynput 监听器（独立线程，事件驱动）
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
        )

    def start(self) -> None:
        """启动键鼠监听。"""
        self._kb_listener.start()
        self._mouse_listener.start()
        print(f"[{time.strftime('%H:%M:%S')}] 热键监听已启动 | Shift+右键+左键=激活 | Ctrl+Q=退出")

    def stop(self) -> None:
        """停止键鼠监听。"""
        self._kb_listener.stop()
        self._mouse_listener.stop()

    @property
    def is_active(self) -> bool:
        """当前是否处于激活状态。"""
        with self._lock:
            return self._active

    @property
    def should_exit(self) -> bool:
        """用户是否请求退出。"""
        with self._lock:
            return self._exit_flag

    def _on_key_press(self, key) -> None:
        try:
            with self._lock:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._ctrl_pressed = True
                elif hasattr(key, "char") and key.char is not None and key.char.lower() == "q":
                    if self._ctrl_pressed:
                        self._exit_flag = True
                elif key == keyboard.Key.shift:
                    self._shift_pressed = True
        except Exception:
            pass

    def _on_key_release(self, key) -> None:
        try:
            with self._lock:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._ctrl_pressed = False
                elif key == keyboard.Key.shift:
                    self._shift_pressed = False
                    if self._active:
                        self._active = False
                        print(f"[{time.strftime('%H:%M:%S')}] 辅助已停用 (Shift 释放)")
        except Exception:
            pass

    def _on_mouse_click(self, x, y, button, pressed) -> None:
        try:
            with self._lock:
                if button == mouse.Button.left:
                    self._left_held = pressed
                    if pressed and self._shift_pressed and self._right_pressed and not self._active:
                        self._active = True
                        print(f"[{time.strftime('%H:%M:%S')}] 辅助已激活")
                elif button == mouse.Button.right:
                    if pressed:
                        self._right_pressed = True
                    else:
                        self._right_pressed = False
                        if self._active:
                            self._active = False
                            print(f"[{time.strftime('%H:%M:%S')}] 辅助已停用 (右键释放)")
        except Exception:
            pass
