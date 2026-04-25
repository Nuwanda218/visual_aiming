# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Optional


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    minimum: float
    maximum: float
    step: float
    description: str
    value_type: type = float


@dataclass(frozen=True)
class BoolSpec:
    key: str
    label: str
    description: str


class ConfigWindow:
    def __init__(self, config, config_path: str):
        self.config = config
        self.config_path = config_path
        self.root: Optional[tk.Tk] = None
        self.thread: Optional[threading.Thread] = None
        self._save_after_id = None
        self._status_var = None

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="ConfigWindow", daemon=True)
        self.thread.start()

    def stop(self):
        root = self.root
        if root is not None:
            try:
                root.after(0, root.destroy)
            except Exception:
                pass

    def _run(self):
        try:
            self.root = tk.Tk()
            self.root.title("Visual Aiming Runtime Config")
            self.root.geometry("980x720")
            self.root.minsize(860, 560)
            self._build()
            self.root.mainloop()
        except Exception as exc:
            print(f"[配置窗口] 启动失败: {exc}")
        finally:
            self.root = None

    def _build(self):
        assert self.root is not None
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, padding=(12, 10, 12, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="运行时参数面板",
            font=("Microsoft YaHei UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="拖动滑块会立即影响当前运行参数，并自动保存到 config.json。",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        notebook = ttk.Notebook(root)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=8)

        for title, items in self._sections():
            notebook.add(self._make_section(notebook, items), text=title)

        footer = ttk.Frame(root, padding=(12, 2, 12, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self._status_var = tk.StringVar(value="等待调整")
        ttk.Label(footer, textvariable=self._status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="立即保存", command=self._save_now).grid(row=0, column=1, sticky="e")

    def _make_section(self, parent, items):
        outer = ttk.Frame(parent)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, padding=(8, 8, 8, 16))
        body.columnconfigure(1, weight=1)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())

        body.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_configure)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        row = 0
        for item in items:
            if isinstance(item, ParamSpec):
                self._add_numeric_row(body, row, item)
            else:
                self._add_bool_row(body, row, item)
            row += 1

        return outer

    def _add_numeric_row(self, parent, row: int, spec: ParamSpec):
        current = self._read_value(spec.key, spec.minimum)
        value_var = tk.DoubleVar(value=float(current))
        text_var = tk.StringVar(value=self._format_value(current, spec))

        ttk.Label(parent, text=spec.label, width=18).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=7)
        scale = ttk.Scale(
            parent,
            from_=spec.minimum,
            to=spec.maximum,
            variable=value_var,
            command=lambda _value, s=spec, v=value_var, t=text_var: self._on_numeric_scale(s, v, t),
        )
        scale.grid(row=row, column=1, sticky="ew", pady=7)
        entry = ttk.Entry(parent, width=10, textvariable=text_var)
        entry.grid(row=row, column=2, sticky="ne", padx=(8, 8), pady=7)
        ttk.Label(parent, text=spec.description, wraplength=300).grid(
            row=row,
            column=3,
            sticky="nw",
            pady=7,
        )
        entry.bind("<Return>", lambda _event, s=spec, v=value_var, t=text_var: self._on_numeric_entry(s, v, t))
        entry.bind("<FocusOut>", lambda _event, s=spec, v=value_var, t=text_var: self._on_numeric_entry(s, v, t))

    def _add_bool_row(self, parent, row: int, spec: BoolSpec):
        value_var = tk.BooleanVar(value=bool(self._read_value(spec.key, False)))
        check = ttk.Checkbutton(
            parent,
            text=spec.label,
            variable=value_var,
            command=lambda s=spec, v=value_var: self._set_value(s.key, bool(v.get())),
        )
        check.grid(row=row, column=0, columnspan=2, sticky="w", pady=7)
        ttk.Label(parent, text=spec.description, wraplength=460).grid(
            row=row,
            column=2,
            columnspan=2,
            sticky="w",
            pady=7,
        )

    def _on_numeric_scale(self, spec: ParamSpec, value_var: tk.DoubleVar, text_var: tk.StringVar):
        value = self._snap(value_var.get(), spec)
        text_var.set(self._format_value(value, spec))
        self._set_value(spec.key, value)

    def _on_numeric_entry(self, spec: ParamSpec, value_var: tk.DoubleVar, text_var: tk.StringVar):
        try:
            raw = float(text_var.get())
        except ValueError:
            raw = float(self._read_value(spec.key, spec.minimum))
        value = self._snap(raw, spec)
        value_var.set(float(value))
        text_var.set(self._format_value(value, spec))
        self._set_value(spec.key, value)

    def _set_value(self, key: str, value: Any):
        setattr(self.config, key, value)
        self._schedule_save()

    def _read_value(self, key: str, fallback: Any):
        return getattr(self.config, key, fallback)

    def _snap(self, value: float, spec: ParamSpec):
        value = max(spec.minimum, min(spec.maximum, value))
        if spec.step > 0:
            value = round(value / spec.step) * spec.step
        if spec.value_type is int:
            return int(round(value))
        return round(float(value), self._decimals(spec.step))

    def _format_value(self, value: Any, spec: ParamSpec) -> str:
        if spec.value_type is int:
            return str(int(round(float(value))))
        decimals = self._decimals(spec.step)
        return f"{float(value):.{decimals}f}"

    def _decimals(self, step: float) -> int:
        text = f"{step:.8f}".rstrip("0")
        if "." not in text:
            return 0
        return min(6, len(text.split(".", 1)[1]))

    def _schedule_save(self):
        root = self.root
        if root is None:
            return
        if self._status_var is not None:
            self._status_var.set("参数已修改，等待自动保存...")
        if self._save_after_id is not None:
            try:
                root.after_cancel(self._save_after_id)
            except Exception:
                pass
        delay = max(50, int(getattr(self.config, "config_ui_autosave_ms", 350)))
        self._save_after_id = root.after(delay, self._save_now)

    def _save_now(self):
        try:
            self.config.save(self.config_path)
            if self._status_var is not None:
                self._status_var.set(f"已保存 config.json - {time.strftime('%H:%M:%S')}")
        except Exception as exc:
            if self._status_var is not None:
                self._status_var.set(f"保存失败: {exc}")

    def _sections(self):
        return [
            (
                "运动灵敏度",
                [
                    ParamSpec("servo_output_gain", "整体输出增益", 0.2, 3.0, 0.01, "整体放大/缩小鼠标移动量。大了更跟手，也更容易过冲。"),
                    ParamSpec("servo_step_limit", "单步最大输出", 4, 120, 1, "每个控制 tick 最多发送多少像素位移。决定瞬间追赶上限。", int),
                    ParamSpec("servo_kp", "吸附力度 Kp", 1, 80, 0.5, "误差越大输出越大。提高后起步更猛。"),
                    ParamSpec("servo_kd", "阻尼 Kd", 0, 0.2, 0.001, "根据目标速度做抑制。提高后更稳，但可能变钝。"),
                    ParamSpec("servo_max_speed", "最大速度", 200, 8000, 10, "伺服内部速度上限。限制远距离追赶速度。"),
                    ParamSpec("servo_max_accel", "最大加速度", 1000, 60000, 100, "速度变化上限。提高后响应更快，降低后更柔。"),
                    ParamSpec("servo_loop_hz", "控制线程频率", 60, 500, 5, "鼠标控制线程频率。过高会增加 CPU 调度压力。"),
                ],
            ),
            (
                "近场刹车",
                [
                    ParamSpec("servo_deadzone", "死区", 0, 10, 0.1, "误差小于该值时停止输出。小了更准，大了更稳。"),
                    ParamSpec("servo_near_gain", "近场增益", 0.01, 0.8, 0.01, "接近中心时的速度比例。降低会更容易收住。"),
                    ParamSpec("servo_far_gain", "远场增益", 0.2, 2.5, 0.01, "远距离时的速度比例。提高会更快追目标。"),
                    ParamSpec("servo_arrival_radius", "减速半径", 10, 220, 1, "从快到慢的过渡范围。增大会更早减速。"),
                    ParamSpec("servo_near_brake", "近场制动", 0, 1.0, 0.01, "进入刹车区后的额外制动强度。提高能减少冲过头。"),
                    ParamSpec("servo_brake_radius", "制动半径", 5, 140, 1, "额外制动开始生效的范围。"),
                    ParamSpec("servo_output_smooth", "输出平滑", 0, 0.9, 0.01, "输出速度平滑程度。高了更柔，但响应滞后。"),
                ],
            ),
            (
                "预测跟踪",
                [
                    BoolSpec("tracker_enabled", "启用目标预测", "用位置差分速度预测短期目标位置。"),
                    ParamSpec("tracker_prediction_time", "预测时间", 0, 0.12, 0.001, "预测未来多少秒。提高能提前量更多，也更容易误判。"),
                    ParamSpec("tracker_smoothing_factor", "速度平滑", 0, 0.95, 0.01, "越高越平滑但越滞后；越低越灵敏。"),
                    ParamSpec("tracker_stop_threshold", "小速度清零", 0, 80, 1, "速度低于该值时视为静止，减少微漂移。"),
                    ParamSpec("tracker_max_prediction_ms", "最大预测保留", 0, 500, 5, "丢失新测量后最多继续预测多久。"),
                    ParamSpec("tracker_reset_distance", "跳变重置距离", 20, 600, 5, "新目标跳得太远时重置预测，避免拖着旧速度。"),
                    BoolSpec("tracker_prediction_as_measurement", "预测喂给伺服", "开启后预测点会作为临时测量输入伺服。"),
                    BoolSpec("servo_direction_reset_enabled", "伺服反向重置", "目标突然反向时清掉旧速度惯性。"),
                    ParamSpec("servo_direction_reset_speed", "反向重置速度阈值", 20, 800, 5, "速度超过该值且方向相反时触发重置。"),
                    ParamSpec("servo_lead_ms", "伺服提前量", 0, 40, 0.5, "伺服内部估计向前看的时间。"),
                ],
            ),
            (
                "检测节奏",
                [
                    ParamSpec("runtime_poll_fps", "主轮询频率", 30, 300, 5, "主循环喂控制目标的频率，不等于 YOLO 推理频率。", int),
                    ParamSpec("capture_fps", "截图频率", 5, 120, 1, "截图线程采样频率。高了更及时，也更占资源。", int),
                    ParamSpec("detect_fps", "普通检测频率", 1, 120, 1, "默认 YOLO 检测频率。", int),
                    ParamSpec("firing_detect_fps", "开火检测频率", 1, 120, 1, "开火时 YOLO 检测频率。", int),
                    ParamSpec("idle_detect_fps", "空闲检测频率", 1, 60, 1, "已激活但未开火时的低频检测。", int),
                    BoolSpec("idle_detect_enabled", "启用空闲降频", "未开火时降低检测频率，减少占用。"),
                    BoolSpec("detect_only_new_frames", "只检测新截图帧", "避免同一帧画面被重复推理。"),
                    ParamSpec("yolo_imgsz", "YOLO 输入尺寸", 256, 960, 32, "越大越准但越慢。更改后立即影响后续推理。", int),
                    ParamSpec("yolo_conf_threshold", "置信度阈值", 0.05, 0.95, 0.01, "越高越保守，越低越容易检测到但误检更多。"),
                    ParamSpec("yolo_iou_threshold", "NMS IOU 阈值", 0.1, 0.9, 0.01, "控制重叠框合并强度。"),
                ],
            ),
            (
                "瞄点与目标",
                [
                    ParamSpec("aim_target_preference", "头/人倾向", 0, 1, 0.01, "1 更偏 head，0 更偏 person。"),
                    ParamSpec("aim_smooth_factor", "瞄点平滑", 0.05, 1.0, 0.01, "越低越稳但越慢，越高越跟手。"),
                    ParamSpec("aim_switch_distance", "大跳变距离", 10, 220, 1, "超过该距离认为目标/瞄点发生切换。"),
                    ParamSpec("aim_switch_smooth_factor", "切换平滑", 0.05, 0.8, 0.01, "大跳变时使用的低速平滑因子。"),
                    ParamSpec("target_stickiness", "目标粘性", 0, 1, 0.01, "提高后更不容易在多个目标间跳。"),
                    ParamSpec("target_history_radius", "历史半径", 10, 300, 5, "判定同一目标连续性的范围。", int),
                    ParamSpec("target_switch_margin", "切换门槛", 0, 0.5, 0.01, "新目标需要比旧目标好多少才切换。"),
                    ParamSpec("target_class_switch_penalty", "类别切换惩罚", 0, 0.5, 0.01, "head/person 类别切换时的额外惩罚。"),
                    ParamSpec("head_bias", "Person 头部偏置", 0.05, 0.55, 0.01, "person 框内估算头部位置的高度比例。"),
                ],
            ),
            (
                "补偿",
                [
                    BoolSpec("view_compensation_enabled", "启用视角补偿", "根据已发送鼠标位移修正旧瞄点。"),
                    ParamSpec("view_compensation_gain_x", "视角补偿 X", 0, 2, 0.01, "横向视角补偿增益。"),
                    ParamSpec("view_compensation_gain_y", "视角补偿 Y", 0, 2, 0.01, "纵向视角补偿增益。"),
                    ParamSpec("view_compensation_max_offset", "补偿最大偏移", 20, 600, 5, "限制旧瞄点被补偿拉开的最大距离。"),
                    BoolSpec("view_compensation_as_measurement", "补偿喂给伺服", "把补偿后的旧瞄点作为临时测量。"),
                    BoolSpec("recoil_enabled", "启用压枪曲线", "读取 recoil_profile.json 的静态压枪曲线。"),
                    ParamSpec("firing_follow_x", "开火锁点 X 跟随", 0, 1, 0.01, "开火锁定时横向跟随新瞄点的比例。"),
                    ParamSpec("firing_follow_y", "开火锁点 Y 跟随", 0, 1, 0.01, "开火锁定时纵向跟随新瞄点的比例。"),
                    ParamSpec("firing_vertical_boost", "开火下拉增强", 0.5, 3, 0.05, "开火时向下跟随的额外上限倍率。"),
                ],
            ),
        ]
