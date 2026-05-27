
# -*- coding: utf-8 -*-
import json
import math
import random
import time
import tkinter as tk
from ctypes import POINTER, Structure, c_int, windll
from threading import Lock, Thread


class POINT(Structure):
    _fields_ = [("x", c_int), ("y", c_int)]


GetCursorPos = windll.user32.GetCursorPos
SetCursorPos = windll.user32.SetCursorPos
GetSystemMetrics = windll.user32.GetSystemMetrics


SCREEN_WIDTH = GetSystemMetrics(0)
SCREEN_HEIGHT = GetSystemMetrics(1)


def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class ProjectMouseController:
    """使用项目移动逻辑的鼠标控制器"""
    
    def __init__(self, config):
        self.config = config
        self.error_x = 0.0
        self.error_y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.has_error = False
    
    def get_cursor_pos(self):
        pt = POINT()
        GetCursorPos(POINTER(POINT)(pt))
        return pt.x, pt.y
    
    def set_cursor_pos(self, x, y):
        SetCursorPos(int(round(x)), int(round(y)))
    
    def compute_move(self, target_x, target_y, dt):
        """项目的 _compute_move 逻辑"""
        cursor_x, cursor_y = self.get_cursor_pos()
        
        self.error_x = target_x - cursor_x
        self.error_y = target_y - cursor_y
        
        dt = max(0.0005, min(dt, 0.05))
        distance = math.hypot(self.error_x, self.error_y)
        deadzone = max(0.0, float(self.config.get("servo_deadzone", 2.0)))
        
        if distance <= deadzone:
            self._brake_to_stop()
            return 0, 0
        
        angle = math.atan2(self.error_y, self.error_x)
        speed_gain = max(0.0, float(self.config.get("fps_speed_gain", 42.0)))
        min_speed = max(0.0, float(self.config.get("fps_min_speed", 0.0)))
        max_speed = max(min_speed, float(self.config.get("fps_max_speed", 7200.0)))
        target_speed = max(min_speed, min(max_speed, distance * speed_gain))
        
        decel_radius = max(deadzone + 1.0, float(self.config.get("fps_decel_radius", 135.0)))
        near_scale = max(0.01, min(1.0, float(self.config.get("fps_near_speed_scale", 0.10))))
        if distance < decel_radius:
            decel = max(0.0, min(1.0, distance / decel_radius))
            target_speed *= near_scale + (1.0 - near_scale) * decel
        
        target_vel_x = math.cos(angle) * target_speed
        target_vel_y = math.sin(angle) * target_speed
        accel = max(0.0, float(self.config.get("fps_acceleration", 52.0)))
        alpha = max(0.0, min(1.0, accel * dt))
        self.velocity_x += (target_vel_x - self.velocity_x) * alpha
        self.velocity_y += (target_vel_y - self.velocity_y) * alpha
        
        brake_radius = max(deadzone + 1.0, float(self.config.get("fps_brake_radius", 90.0)))
        brake = max(0.0, float(self.config.get("fps_brake", 0.72)))
        if distance < brake_radius and brake > 0.0:
            retain = max(0.0, 1.0 - brake * dt)
            self.velocity_x *= retain
            self.velocity_y *= retain
        
        move_x = self.velocity_x * dt
        move_y = self.velocity_y * dt
        output_gain = float(self.config.get("servo_output_gain", 1.0))
        move_x *= output_gain
        move_y *= output_gain
        
        max_step = max(1, int(self.config.get("servo_step_limit", 48)))
        move_x, move_y = self._clamp_length(move_x, move_y, float(max_step))
        
        move_x += self.subpixel_x
        move_y += self.subpixel_y
        send_x = int(round(move_x))
        send_y = int(round(move_y))
        self.subpixel_x = move_x - send_x
        self.subpixel_y = move_y - send_y
        
        return send_x, send_y
    
    def move_absolute(self, target_x, target_y):
        """绝对移动（平滑版）"""
        smooth = max(0.0, min(1.0, float(self.config.get("mouse_absolute_smooth_factor", 1.0))))
        max_step = max(0.0, float(self.config.get("mouse_absolute_max_step", 0.0)))
        
        if smooth >= 1.0 and max_step <= 0.0:
            self.set_cursor_pos(target_x, target_y)
            self._brake_to_stop()
            return
        
        cursor_x, cursor_y = self.get_cursor_pos()
        move_x = (target_x - cursor_x) * max(smooth, 0.01)
        move_y = (target_y - cursor_y) * max(smooth, 0.01)
        if max_step > 0.0:
            move_x, move_y = self._clamp_length(move_x, move_y, max_step)
        
        self.set_cursor_pos(cursor_x + move_x, cursor_y + move_y)
        self._brake_to_stop()
    
    def _clamp_length(self, x, y, max_length):
        length = math.hypot(x, y)
        if length <= max_length or length <= 1e-6:
            return x, y
        scale = max_length / length
        return x * scale, y * scale
    
    def _brake_to_stop(self):
        self.error_x = 0.0
        self.error_y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.subpixel_x = 0.0
        self.subpixel_y = 0.0
        self.has_error = False


class CircleGame:
    def __init__(self, screen_width=None, screen_height=None):
        self.screen_width = screen_width or SCREEN_WIDTH
        self.screen_height = screen_height or SCREEN_HEIGHT
        self.center_width = self.screen_width * 2 / 3
        self.center_height = self.screen_height * 2 / 3
        self.min_x = (self.screen_width - self.center_width) / 2
        self.max_x = (self.screen_width + self.center_width) / 2
        self.min_y = (self.screen_height - self.center_height) / 2
        self.max_y = (self.screen_height + self.center_height) / 2
        
        self.circle_radius = 10
        self.circle_x = self.screen_width // 2
        self.circle_y = self.screen_height // 2
        self.move_speed = 100
        self.running = True
        self.lock = Lock()
        self.frame_times = []
        print(f"屏幕分辨率: {self.screen_width}x{self.screen_height}")
    
    def update_circle_position(self, dx=0, dy=0, random_pos=False, new_radius=None):
        with self.lock:
            if random_pos:
                self.circle_x = random.randint(int(self.min_x + self.circle_radius), int(self.max_x - self.circle_radius))
                self.circle_y = random.randint(int(self.min_y + self.circle_radius), int(self.max_y - self.circle_radius))
                print(f"🎯 随机移动圆心 → ({self.circle_x:.0f}, {self.circle_y:.0f})")
            else:
                self.circle_x = max(self.min_x + self.circle_radius, min(self.max_x - self.circle_radius, self.circle_x + dx))
                self.circle_y = max(self.min_y + self.circle_radius, min(self.max_y - self.circle_radius, self.circle_y + dy))
            
            if new_radius is not None:
                self.circle_radius = max(20, min(400, new_radius))
    
    def update_speed(self, delta):
        with self.lock:
            self.move_speed = max(1, min(100, self.move_speed + delta))
    
    def get_state(self):
        with self.lock:
            return {
                'circle_x': self.circle_x,
                'circle_y': self.circle_y,
                'circle_radius': self.circle_radius,
                'move_speed': self.move_speed,
            }
    
    def stop(self):
        self.running = False
    
    def get_fps(self):
        if self.frame_times:
            avg_time = sum(self.frame_times) / len(self.frame_times)
            return 1.0 / avg_time if avg_time > 0 else 0
        return 0
    
    def record_frame_time(self, elapsed):
        self.frame_times.append(elapsed)
        if len(self.frame_times) > 60:
            self.frame_times.pop(0)


class GameUI:
    def __init__(self, game: CircleGame, screen_width=None, screen_height=None):
        self.game = game
        self.screen_width = screen_width or SCREEN_WIDTH
        self.screen_height = screen_height or SCREEN_HEIGHT
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.title("鼠标控制器测试 - 项目逻辑版 - WASD移动 R随机 Q退出")
        self.root.configure(bg='black')
        self.root.attributes('-topmost', True)
        
        self.canvas = tk.Canvas(self.root, width=self.screen_width, height=self.screen_height, bg='black', highlightthickness=0)
        self.canvas.pack()
        
        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def bind_keys(self):
        self.root.bind('<KeyPress-w>', lambda e: self.game.update_circle_position(dy=-5))
        self.root.bind('<KeyPress-s>', lambda e: self.game.update_circle_position(dy=5))
        self.root.bind('<KeyPress-a>', lambda e: self.game.update_circle_position(dx=-5))
        self.root.bind('<KeyPress-d>', lambda e: self.game.update_circle_position(dx=5))
        self.root.bind('<KeyPress-r>', lambda e: self.game.update_circle_position(random_pos=True))
        self.root.bind('<KeyPress-minus>', lambda e: self.game.update_speed(-1))
        self.root.bind('<KeyPress-equal>', lambda e: self.game.update_speed(1))
        self.root.bind('<KeyPress-bracketleft>', lambda e: self.on_radius_change(-5))
        self.root.bind('<KeyPress-bracketright>', lambda e: self.on_radius_change(5))
        self.root.bind('<KeyPress-q>', lambda e: self.on_close())
    
    def on_radius_change(self, delta):
        state = self.game.get_state()
        self.game.update_circle_position(new_radius=state['circle_radius'] + delta)
    
    def on_close(self):
        self.game.stop()
        self.root.quit()
    
    def update_display(self):
        if not self.game.running:
            return
        
        state = self.game.get_state()
        self.canvas.delete('all')
        
        self.canvas.create_oval(
            state['circle_x'] - state['circle_radius'],
            state['circle_y'] - state['circle_radius'],
            state['circle_x'] + state['circle_radius'],
            state['circle_y'] + state['circle_radius'],
            outline='red', width=3
        )
        
        fps = self.game.get_fps()
        self.canvas.create_text(
            10, 10,
            text=f"FPS: {fps:.1f} | 速度: {state['move_speed']} | WASD移动 | R随机 | +/-调速 | Q退出",
            fill='red', anchor='nw', font=('Arial', 12)
        )
        
        self.root.after(16, self.update_display)
    
    def run(self):
        self.update_display()
        self.root.mainloop()


def servo_worker(game, controller, config):
    """240Hz Servo 循环 - 使用项目的移动逻辑"""
    target_fps = float(config.get("servo_loop_hz", 240.0))
    frame_time = 1.0 / target_fps
    last_time = time.perf_counter()
    
    while game.running:
        loop_start = time.perf_counter()
        dt = max(0.0005, min(loop_start - last_time, 0.05))
        last_time = loop_start
        
        state = game.get_state()
        
        target_x = state['circle_x']
        target_y = state['circle_y']
        
        cursor_x, cursor_y = controller.get_cursor_pos()
        dist = math.hypot(target_x - cursor_x, target_y - cursor_y)
        
        if dist > 1.0:
            send_x, send_y = controller.compute_move(target_x, target_y, dt)
            if send_x != 0 or send_y != 0:
                controller.set_cursor_pos(cursor_x + send_x, cursor_y + send_y)
        
        elapsed = time.perf_counter() - loop_start
        game.record_frame_time(elapsed)
        
        sleep_time = frame_time - (time.perf_counter() - loop_start)
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == '__main__':
    config = load_config()
    
    print("=" * 60)
    print("鼠标控制器测试 - 项目逻辑版")
    print("=" * 60)
    print("\n按 Enter 开始全屏测试...")
    input()
    
    game = CircleGame()
    controller = ProjectMouseController(config)
    
    mouse_thread = Thread(target=lambda: servo_worker(game, controller, config), daemon=True)
    mouse_thread.start()
    
    GameUI(game).run()
