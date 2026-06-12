# -*- coding: utf-8 -*-
"""Windows desktop app for conformal deposition dent modeling.

This version intentionally avoids Streamlit/HTML. It uses only the Python
standard library so it can be packaged into a simple Windows executable.
"""

import math
import tkinter as tk
from tkinter import ttk


class DentDepositionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("컨포멀 증착 덴트 모델")
        self.geometry("1320x900")
        self.minsize(1040, 720)

        self.next_id = 1
        self.width_value = tk.DoubleVar(value=10.0)
        self.depth_value = tk.DoubleVar(value=3.0)
        self.max_depo_value = tk.IntVar(value=20)
        self.current_depo_value = tk.IntVar(value=2)
        self.smooth_value = tk.BooleanVar(value=False)
        self.mode_value = tk.StringVar(value="move")

        self.points = self.make_default_points()
        self.selected_id = None
        self.dragging_id = None
        self.last_metrics = {"depth": 0.0, "angle": 0.0}
        self._ready = False
        self._updating_slider = False

        self.configure(bg="#f8fafc")
        self._build_ui()
        self.bind("<Delete>", lambda _event: self.delete_selected_point())
        self.bind("<BackSpace>", lambda _event: self.delete_selected_point())
        self.bind("<Configure>", self._on_resize)
        self._ready = True
        self.after(80, self.redraw_all)

    def make_default_points(self):
        width = max(0.1, float(self.width_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        half = width / 2.0
        inset = max(width * 0.08, 0.01)
        coords = [
            (-half, 0.0, True),
            (-half + inset, 0.0, False),
            (-half + inset, -depth, False),
            (0.0, -depth, False),
            (half - inset, -depth, False),
            (half - inset, 0.0, False),
            (half, 0.0, True),
        ]
        points = []
        for x, y, locked in coords:
            points.append({"id": self.next_id, "x": x, "y": y, "locked": locked})
            self.next_id += 1
        return points

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f8fafc")
        style.configure("Panel.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("TLabel", background="#f8fafc", foreground="#0f172a")
        style.configure("Panel.TLabel", background="#ffffff", foreground="#0f172a")
        style.configure("TButton", padding=(10, 5), font=("Malgun Gothic", 10, "bold"))
        style.configure("Active.TButton", padding=(10, 5), font=("Malgun Gothic", 10, "bold"))
        style.map("Active.TButton", background=[("!disabled", "#2563eb")], foreground=[("!disabled", "#ffffff")])

        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        title = ttk.Label(root, text="컨포멀 증착 덴트 모델", font=("Malgun Gothic", 20, "bold"))
        title.grid(row=0, column=0, sticky="w")

        controls = ttk.Frame(root)
        controls.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        for col in range(10):
            controls.columnconfigure(col, weight=1 if col in (3, 4) else 0)

        self._number_control(controls, "W: 덴트 폭", self.width_value, 0, self.on_width_changed)
        self._number_control(controls, "D: 초기 깊이", self.depth_value, 1, self.on_depth_changed)
        self._number_control(controls, "최대 적층량", self.max_depo_value, 2, self.on_max_depo_changed, integer=True)

        slider_box = ttk.Frame(controls)
        slider_box.grid(row=0, column=3, columnspan=2, sticky="ew", padx=5)
        slider_box.columnconfigure(0, weight=1)
        self.current_label = ttk.Label(slider_box, text="현재 적층량: 2")
        self.current_label.grid(row=0, column=0, sticky="w")
        self.current_slider = ttk.Scale(
            slider_box,
            from_=0,
            to=self.max_depo_value.get(),
            orient=tk.HORIZONTAL,
            command=self.on_current_depo_changed,
        )
        self.current_slider.set(self.current_depo_value.get())
        self.current_slider.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        smooth = ttk.Checkbutton(
            controls,
            text="부드러운 곡선",
            variable=self.smooth_value,
            command=self.redraw_all,
        )
        smooth.grid(row=0, column=5, sticky="w", padx=8)

        self.add_button = ttk.Button(controls, text="점 추가", command=lambda: self.set_mode("add"))
        self.add_button.grid(row=0, column=6, padx=4, sticky="ew")
        self.delete_button = ttk.Button(controls, text="점 삭제", command=lambda: self.set_mode("delete"))
        self.delete_button.grid(row=0, column=7, padx=4, sticky="ew")
        reset = ttk.Button(controls, text="형상 초기화", command=self.reset_shape)
        reset.grid(row=0, column=8, padx=4, sticky="ew")

        self.status_label = ttk.Label(
            controls,
            text="",
            foreground="#334155",
            font=("Malgun Gothic", 10, "bold"),
        )
        self.status_label.grid(row=0, column=9, padx=(10, 0), sticky="e")

        split = ttk.Frame(root)
        split.grid(row=2, column=0, sticky="nsew")
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=1)
        split.rowconfigure(0, weight=1)
        split.rowconfigure(1, weight=1)

        graph_panel = self._panel(split, "y(x), z(x) 그래프", 0, 0)
        self.graph_canvas = tk.Canvas(graph_panel, bg="white", highlightthickness=1, highlightbackground="#cbd5e1")
        self.graph_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        build_panel = self._panel(split, "쌓이는 모습 (1 단위 적층)", 0, 1)
        self.build_canvas = tk.Canvas(build_panel, bg="white", highlightthickness=1, highlightbackground="#cbd5e1")
        self.build_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        editor_panel = self._panel(split, "기본 덴트 구조 점 편집", 1, 0, columnspan=2)
        self.editor_canvas = tk.Canvas(editor_panel, bg="white", height=300, highlightthickness=1, highlightbackground="#cbd5e1")
        self.editor_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        hint = ttk.Label(
            editor_panel,
            text="기본 구조만 편집합니다. 점을 드래그해서 이동, 점 추가 모드에서 빈 곳 클릭, 점 삭제 모드에서 점 클릭.",
            style="Panel.TLabel",
            foreground="#64748b",
        )
        hint.pack(anchor="w", padx=8, pady=(0, 8))

        self.editor_canvas.bind("<Button-1>", self.on_editor_press)
        self.editor_canvas.bind("<B1-Motion>", self.on_editor_drag)
        self.editor_canvas.bind("<ButtonRelease-1>", self.on_editor_release)
        self.editor_canvas.bind("<Double-Button-1>", self.on_editor_double_click)

    def _number_control(self, parent, label, variable, column, callback, integer=False):
        box = ttk.Frame(parent)
        box.grid(row=0, column=column, padx=5, sticky="w")
        ttk.Label(box, text=label).grid(row=0, column=0, sticky="w")
        validate = self.register(lambda value: self._valid_number(value, integer))
        entry = ttk.Entry(box, textvariable=variable, width=10, validate="key", validatecommand=(validate, "%P"))
        entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        entry.bind("<Return>", callback)
        entry.bind("<FocusOut>", callback)
        return entry

    @staticmethod
    def _valid_number(value, integer):
        if value in ("", "-", "."):
            return True
        try:
            number = int(value) if integer else float(value)
            return number >= 0
        except ValueError:
            return False

    def _panel(self, parent, title, row, column, columnspan=1):
        panel = ttk.Frame(parent, style="Panel.TFrame")
        panel.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=5, pady=5)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        label = ttk.Label(panel, text=title, style="Panel.TLabel", font=("Malgun Gothic", 11, "bold"))
        label.pack(anchor="w", padx=8, pady=8)
        return panel

    def _on_resize(self, _event):
        if hasattr(self, "_resize_job"):
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self.redraw_all)

    def set_mode(self, mode):
        self.mode_value.set("move" if self.mode_value.get() == mode else mode)
        self.update_mode_buttons()

    def update_mode_buttons(self):
        self.add_button.configure(style="Active.TButton" if self.mode_value.get() == "add" else "TButton")
        self.delete_button.configure(style="Active.TButton" if self.mode_value.get() == "delete" else "TButton")

    def on_width_changed(self, _event=None):
        old_width = max(0.1, self._get_float(self.width_value, 10.0))
        new_width = max(0.1, old_width)
        self.width_value.set(round(new_width, 3))
        current_half = max(abs(self.points[0]["x"]), abs(self.points[-1]["x"]), 0.1)
        scale = (new_width / 2.0) / current_half
        for point in self.points:
            point["x"] *= scale
        sorted_points = self.sorted_points()
        sorted_points[0]["x"] = -new_width / 2.0
        sorted_points[-1]["x"] = new_width / 2.0
        self.redraw_all()

    def on_depth_changed(self, _event=None):
        new_depth = max(0.1, self._get_float(self.depth_value, 3.0))
        old_bottom = min((p["y"] for p in self.points), default=-new_depth)
        old_depth = max(0.1, abs(old_bottom))
        scale = new_depth / old_depth
        self.depth_value.set(round(new_depth, 3))
        for point in self.points:
            point["y"] *= scale
            point["y"] = min(0.0, max(-new_depth * 1.2, point["y"]))
        self.redraw_all()

    def on_max_depo_changed(self, _event=None):
        max_depo = max(1, int(round(self._get_float(self.max_depo_value, 1))))
        self.max_depo_value.set(max_depo)
        self.current_slider.configure(to=max_depo)
        if self.current_depo_value.get() > max_depo:
            self.current_depo_value.set(max_depo)
            self.current_slider.set(max_depo)
        self.redraw_all()

    def on_current_depo_changed(self, value):
        depo = int(round(float(value)))
        depo = max(0, min(depo, self.max_depo_value.get()))
        self.current_depo_value.set(depo)
        if self._updating_slider:
            return
        if not self._ready:
            return
        self._updating_slider = True
        try:
            self.current_slider.set(depo)
        finally:
            self._updating_slider = False
        self.redraw_all()

    def reset_shape(self):
        self.selected_id = None
        self.dragging_id = None
        self.points = self.make_default_points()
        self.redraw_all()

    @staticmethod
    def _get_float(var, default):
        try:
            return float(var.get())
        except (tk.TclError, ValueError):
            return default

    def sorted_points(self):
        return sorted(self.points, key=lambda p: (p["x"], p["id"]))

    def profile_at(self, x):
        points = self.sorted_points()
        if not points:
            return 0.0
        if x <= points[0]["x"] or x >= points[-1]["x"]:
            return 0.0
        for idx in range(len(points) - 1):
            a = points[idx]
            b = points[idx + 1]
            if a["x"] <= x <= b["x"]:
                span = b["x"] - a["x"]
                if abs(span) < 1e-9:
                    return min(a["y"], b["y"])
                t = (x - a["x"]) / span
                if self.smooth_value.get() and 0 < idx < len(points) - 2:
                    p0 = points[idx - 1]
                    p1 = a
                    p2 = b
                    p3 = points[idx + 2]
                    t2 = t * t
                    t3 = t2 * t
                    y = 0.5 * (
                        2 * p1["y"]
                        + (-p0["y"] + p2["y"]) * t
                        + (2 * p0["y"] - 5 * p1["y"] + 4 * p2["y"] - p3["y"]) * t2
                        + (-p0["y"] + 3 * p1["y"] - 3 * p2["y"] + p3["y"]) * t3
                    )
                else:
                    y = a["y"] + (b["y"] - a["y"]) * t
                return min(0.0, y)
        return 0.0

    def field_margin(self):
        width = max(0.1, float(self.width_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        max_depo = max(1, int(self.max_depo_value.get()))
        return max(width * 0.25, max_depo * 1.05, depth * 0.35)

    def evaluate_deposition(self, deposition, sample_count=181, include_field=False):
        if sample_count % 2 == 0:
            sample_count += 1
        width = max(0.1, float(self.width_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        half = width / 2.0
        view_margin = self.field_margin() if include_field else 0.0
        margin = max(width * 0.35 + view_margin, deposition * 1.4 + view_margin, depth * 0.15)

        base_x = [(-half - margin) + (2 * (half + margin) * i) / (sample_count - 1) for i in range(sample_count)]
        base_y = [self.profile_at(x) if abs(x) <= half else 0.0 for x in base_x]

        view_min = -half - view_margin
        view_span = width + view_margin * 2
        view_x = [view_min + view_span * i / (sample_count - 1) for i in range(sample_count)]
        surface = []
        for x in view_x:
            if deposition <= 0:
                surface.append(self.profile_at(x) if abs(x) <= half else 0.0)
                continue
            highest = -1e100
            for bx, by in zip(base_x, base_y):
                dx = x - bx
                if abs(dx) <= deposition:
                    candidate = by + math.sqrt(max(deposition * deposition - dx * dx, 0.0))
                    if candidate > highest:
                        highest = candidate
            if highest < -1e90:
                highest = self.profile_at(x) if abs(x) <= half else 0.0
            surface.append(min(highest, deposition))

        dent_indices = [i for i, x in enumerate(view_x) if abs(x) <= half + 1e-9]
        if not dent_indices:
            dent_indices = list(range(len(view_x)))
        min_index = min(dent_indices, key=lambda i: surface[i])
        depth_left = max(0.0, deposition - surface[min_index])
        max_slope = 0.0
        angle_index = -1
        for i in range(1, len(view_x) - 1):
            if abs(view_x[i]) > half:
                continue
            dx = view_x[i + 1] - view_x[i - 1]
            if abs(dx) < 1e-12:
                continue
            slope = (surface[i + 1] - surface[i - 1]) / dx
            if abs(slope) > max_slope:
                max_slope = abs(slope)
                angle_index = i
        return {
            "view_x": view_x,
            "surface": surface,
            "depth": depth_left,
            "angle": math.degrees(math.atan(max_slope)),
            "angle_index": angle_index,
            "depth_index": min_index,
            "base_x": base_x,
            "base_y": base_y,
        }

    def run_sweep(self):
        max_depo = max(1, int(self.max_depo_value.get()))
        count = max(60, max_depo * 6)
        xs = [max_depo * i / (count - 1) for i in range(count)]
        depths = []
        angles = []
        for x in xs:
            result = self.evaluate_deposition(x, sample_count=151, include_field=False)
            depths.append(result["depth"])
            angles.append(result["angle"])
        return xs, depths, angles

    def canvas_size(self, canvas):
        width = max(100, canvas.winfo_width())
        height = max(100, canvas.winfo_height())
        return width, height

    def draw_axes(self, canvas, pad):
        canvas.delete("all")
        width, height = self.canvas_size(canvas)
        plot_w = width - pad["l"] - pad["r"]
        plot_h = height - pad["t"] - pad["b"]
        canvas.create_rectangle(pad["l"], pad["t"], width - pad["r"], height - pad["b"], fill="#ffffff", outline="#cbd5e1")
        for i in range(6):
            x = pad["l"] + plot_w * i / 5
            y = pad["t"] + plot_h * i / 5
            canvas.create_line(x, pad["t"], x, height - pad["b"], fill="#e2e8f0")
            canvas.create_line(pad["l"], y, width - pad["r"], y, fill="#e2e8f0")
        return width, height, plot_w, plot_h

    def draw_graph(self):
        canvas = self.graph_canvas
        pad = {"l": 64, "r": 56, "t": 28, "b": 48}
        width, height, plot_w, plot_h = self.draw_axes(canvas, pad)
        xs, depths, angles = self.run_sweep()
        max_depo = max(1, int(self.max_depo_value.get()))
        y_max = max(max(depths) * 1.08, float(self.depth_value.get()), 1.0)
        z_max = 90.0

        def map_x(value):
            return pad["l"] + value / max_depo * plot_w

        def map_y(value):
            return height - pad["b"] - value / y_max * plot_h

        def map_z(value):
            return height - pad["b"] - value / z_max * plot_h

        for i in range(6):
            x_val = max_depo * i / 5
            y_val = y_max * i / 5
            z_val = z_max * i / 5
            x = map_x(x_val)
            canvas.create_text(x, height - pad["b"] + 18, text=f"{x_val:.0f}", fill="#64748b", font=("Malgun Gothic", 9))
            canvas.create_text(pad["l"] - 10, map_y(y_val), text=f"{y_val:.1f}", fill="#2563eb", anchor="e", font=("Malgun Gothic", 9))
            canvas.create_text(width - pad["r"] + 8, map_z(z_val), text=f"{z_val:.0f}", fill="#dc2626", anchor="w", font=("Malgun Gothic", 9))

        self._draw_polyline(canvas, [(map_x(x), map_y(y)) for x, y in zip(xs, depths)], "#2563eb", 3)
        self._draw_polyline(canvas, [(map_x(x), map_z(z)) for x, z in zip(xs, angles)], "#dc2626", 3)

        current = max(0, min(int(self.current_depo_value.get()), max_depo))
        cx = map_x(current)
        canvas.create_line(cx, pad["t"], cx, height - pad["b"], fill="#334155", dash=(6, 5), width=2)
        canvas.create_text(width / 2, height - 16, text="x 증착량", fill="#334155", font=("Malgun Gothic", 10, "bold"))
        canvas.create_text(pad["l"] + 8, pad["t"] + 12, text="y 깊이", fill="#2563eb", anchor="w", font=("Malgun Gothic", 10, "bold"))
        canvas.create_text(width - pad["r"] - 8, pad["t"] + 12, text="z 각도", fill="#dc2626", anchor="e", font=("Malgun Gothic", 10, "bold"))

    def draw_build(self):
        canvas = self.build_canvas
        pad = {"l": 64, "r": 28, "t": 30, "b": 48}
        width, height, plot_w, plot_h = self.draw_axes(canvas, pad)
        active = max(0, int(self.current_depo_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        half = max(0.1, float(self.width_value.get())) / 2.0
        x_min = -half
        x_span = half * 2
        y_min = -depth * 1.12
        y_max = max(active * 1.18, depth * 0.24, 0.25)

        def map_x(value):
            return pad["l"] + (value - x_min) / x_span * plot_w

        def map_y(value):
            return height - pad["b"] - (value - y_min) / (y_max - y_min) * plot_h

        for i in range(6):
            x_val = x_min + x_span * i / 5
            y_val = y_min + (y_max - y_min) * i / 5
            canvas.create_text(map_x(x_val), height - pad["b"] + 18, text=f"{x_val:.1f}", fill="#64748b", font=("Malgun Gothic", 9))
            canvas.create_text(pad["l"] - 10, map_y(y_val), text=f"{y_val:.1f}", fill="#64748b", anchor="e", font=("Malgun Gothic", 9))

        layers = [self.evaluate_deposition(i, sample_count=231, include_field=True) for i in range(active + 1)]
        if not layers:
            layers = [self.evaluate_deposition(0, sample_count=231, include_field=True)]

        clip = (pad["l"], pad["t"], width - pad["r"], height - pad["b"])
        colors = ["#99f6e4", "#bbf7d0", "#d9f99d"]
        lines = ["#0f766e", "#047857", "#4d7c0f"]
        for i in range(1, len(layers)):
            prev = layers[i - 1]
            cur = layers[i]
            poly = []
            for x, y in zip(cur["view_x"], cur["surface"]):
                poly.append((map_x(x), map_y(y)))
            for x, y in reversed(list(zip(prev["view_x"], prev["surface"]))):
                poly.append((map_x(x), map_y(y)))
            self._draw_clipped_polygon(canvas, poly, colors[i % len(colors)], clip)
            self._draw_clipped_polyline(canvas, [(map_x(x), map_y(y)) for x, y in zip(cur["view_x"], cur["surface"])], lines[i % len(lines)], 1, clip)

        base = layers[0]
        last = layers[-1]
        self._draw_clipped_polyline(canvas, [(map_x(x), map_y(y)) for x, y in zip(base["view_x"], base["surface"])], "#475569", 2, clip, dash=(6, 5))
        self._draw_clipped_polyline(canvas, [(map_x(x), map_y(y)) for x, y in zip(last["view_x"], last["surface"])], "#047857", 3, clip)

        flat_y = map_y(active)
        canvas.create_line(pad["l"], flat_y, width - pad["r"], flat_y, fill="#111827", width=2)
        canvas.create_text(pad["l"] + 8, max(pad["t"] + 14, flat_y - 10), text=f"현재 적층량 x={active}", fill="#0f172a", anchor="w", font=("Malgun Gothic", 9, "bold"))

        if last["angle_index"] >= 0:
            idx = last["angle_index"]
            ax = map_x(last["view_x"][idx])
            ay = map_y(last["surface"][idx])
            ax = max(pad["l"], min(width - pad["r"], ax))
            ay = max(pad["t"], min(height - pad["b"], ay))
            canvas.create_oval(ax - 5, ay - 5, ax + 5, ay + 5, fill="#dc2626", outline="#dc2626")
            self._label(canvas, ax + 12, ay - 26, f"최대각 {last['angle']:.1f}도", "#991b1b", "#fee2e2")

        if last["depth_index"] >= 0:
            idx = last["depth_index"]
            dx = map_x(last["view_x"][idx])
            dy = map_y(last["surface"][idx])
            dx = max(pad["l"], min(width - pad["r"], dx))
            canvas.create_line(dx, flat_y, dx, dy, fill="#2563eb", width=2, dash=(5, 4))
            canvas.create_oval(dx - 4, dy - 4, dx + 4, dy + 4, fill="#2563eb", outline="#2563eb")
            self._label(canvas, dx + 12, (flat_y + dy) / 2 - 12, f"현재 깊이 {last['depth']:.2f}", "#1d4ed8", "#dbeafe")

        canvas.create_text(pad["l"] + 12, height - pad["b"] - 10, text="필드", fill="#64748b", anchor="w", font=("Malgun Gothic", 9))
        canvas.create_text(map_x(0), height - pad["b"] - 10, text="덴트", fill="#64748b", font=("Malgun Gothic", 9))
        canvas.create_text(width - pad["r"] - 12, height - pad["b"] - 10, text="필드", fill="#64748b", anchor="e", font=("Malgun Gothic", 9))
        self.last_metrics = {"depth": last["depth"], "angle": last["angle"]}

    def draw_editor(self):
        canvas = self.editor_canvas
        pad = {"l": 64, "r": 28, "t": 26, "b": 42}
        width, height, plot_w, plot_h = self.draw_axes(canvas, pad)
        half = max(0.1, float(self.width_value.get())) / 2.0
        depth = max(0.1, float(self.depth_value.get()))
        x_min = -half
        x_span = half * 2
        y_min = -depth * 1.15
        y_max = max(depth * 0.25, 0.25)

        def map_x(value):
            return pad["l"] + (value - x_min) / x_span * plot_w

        def map_y(value):
            return height - pad["b"] - (value - y_min) / (y_max - y_min) * plot_h

        self.editor_map = (map_x, map_y, x_min, x_span, y_min, y_max, pad, width, height)

        for i in range(6):
            x_val = x_min + x_span * i / 5
            y_val = y_min + (y_max - y_min) * i / 5
            canvas.create_text(map_x(x_val), height - pad["b"] + 18, text=f"{x_val:.1f}", fill="#64748b", font=("Malgun Gothic", 9))
            canvas.create_text(pad["l"] - 10, map_y(y_val), text=f"{y_val:.1f}", fill="#64748b", anchor="e", font=("Malgun Gothic", 9))

        samples = []
        for i in range(181):
            x = -half + (2 * half * i) / 180
            samples.append((map_x(x), map_y(self.profile_at(x))))
        area = [(map_x(-half), map_y(0.0))] + samples + [(map_x(half), map_y(0.0))]
        canvas.create_polygon([coord for point in area for coord in point], fill="#dbeafe", outline="")
        self._draw_polyline(canvas, samples, "#2563eb", 3)
        canvas.create_line(map_x(-half), map_y(0.0), map_x(half), map_y(0.0), fill="#111827", width=2)

        for index, point in enumerate(self.sorted_points(), start=1):
            x = map_x(point["x"])
            y = map_y(point["y"])
            radius = 6 if point["locked"] else 8
            fill = "#facc15" if point["id"] == self.selected_id else "#ffffff"
            outline = "#64748b" if point["locked"] else "#0f172a"
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline=outline, width=2, tags=("point", f"point:{point['id']}"))
            canvas.create_text(x + 12, y - 12, text=str(index), fill="#64748b", font=("Malgun Gothic", 9))

        canvas.create_text(pad["l"], height - 12, text=f"W={half * 2:.3f}, D={depth:.3f}", fill="#64748b", anchor="w", font=("Malgun Gothic", 9))
        canvas.create_text(width / 2, height - 12, text="x 위치", fill="#334155", font=("Malgun Gothic", 9, "bold"))
        canvas.create_text(18, height / 2, text="y 높이", fill="#334155", angle=90, font=("Malgun Gothic", 9, "bold"))

    def _draw_polyline(self, canvas, points, color, width, dash=None):
        if len(points) < 2:
            return
        flat = [coord for point in points for coord in point]
        canvas.create_line(*flat, fill=color, width=width, dash=dash, smooth=False)

    def _draw_clipped_polyline(self, canvas, points, color, width, clip, dash=None):
        clipped = [(max(clip[0], min(clip[2], x)), max(clip[1], min(clip[3], y))) for x, y in points]
        self._draw_polyline(canvas, clipped, color, width, dash=dash)

    def _draw_clipped_polygon(self, canvas, points, color, clip):
        clipped = [(max(clip[0], min(clip[2], x)), max(clip[1], min(clip[3], y))) for x, y in points]
        if len(clipped) >= 3:
            canvas.create_polygon([coord for point in clipped for coord in point], fill=color, outline="")

    def _label(self, canvas, x, y, text, text_color, bg_color):
        x = max(68, min(canvas.winfo_width() - 130, x))
        y = max(32, min(canvas.winfo_height() - 64, y))
        font = ("Malgun Gothic", 9, "bold")
        width = max(86, len(text) * 8 + 10)
        canvas.create_rectangle(x - 4, y - 13, x + width, y + 9, fill=bg_color, outline="#cbd5e1")
        canvas.create_text(x, y - 2, text=text, fill=text_color, anchor="w", font=font)

    def editor_to_model(self, canvas_x, canvas_y):
        map_x, map_y, x_min, x_span, y_min, y_max, pad, width, height = self.editor_map
        plot_w = width - pad["l"] - pad["r"]
        plot_h = height - pad["t"] - pad["b"]
        x = x_min + ((canvas_x - pad["l"]) / plot_w) * x_span
        y = y_max - ((canvas_y - pad["t"]) / plot_h) * (y_max - y_min)
        return x, y

    def find_point_at(self, canvas_x, canvas_y):
        if not hasattr(self, "editor_map"):
            return None
        map_x, map_y, *_ = self.editor_map
        best = None
        best_dist = 14
        for point in self.points:
            px = map_x(point["x"])
            py = map_y(point["y"])
            dist = math.hypot(canvas_x - px, canvas_y - py)
            if dist <= best_dist:
                best = point
                best_dist = dist
        return best

    def on_editor_press(self, event):
        point = self.find_point_at(event.x, event.y)
        mode = self.mode_value.get()
        if mode == "delete":
            if point and not point["locked"]:
                self.points = [p for p in self.points if p["id"] != point["id"]]
                self.selected_id = None
                self.redraw_all()
            return
        if mode == "add" and point is None:
            self.add_point_at(event.x, event.y)
            return
        if point is not None:
            self.selected_id = point["id"]
            self.dragging_id = None if point["locked"] else point["id"]
            self.redraw_all()

    def on_editor_double_click(self, event):
        if self.find_point_at(event.x, event.y) is None:
            self.add_point_at(event.x, event.y)

    def on_editor_drag(self, event):
        if self.dragging_id is None:
            return
        point = next((p for p in self.points if p["id"] == self.dragging_id), None)
        if point is None or point["locked"]:
            return
        x, y = self.editor_to_model(event.x, event.y)
        width = max(0.1, float(self.width_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        gap = width * 0.01
        point["x"] = max(-width / 2 + gap, min(width / 2 - gap, x))
        point["y"] = min(0.0, max(-depth * 1.15, y))
        self.redraw_all()

    def on_editor_release(self, _event):
        self.dragging_id = None

    def add_point_at(self, canvas_x, canvas_y):
        x, y = self.editor_to_model(canvas_x, canvas_y)
        width = max(0.1, float(self.width_value.get()))
        depth = max(0.1, float(self.depth_value.get()))
        gap = width * 0.02
        point = {
            "id": self.next_id,
            "x": max(-width / 2 + gap, min(width / 2 - gap, x)),
            "y": min(0.0, max(-depth * 1.15, y)),
            "locked": False,
        }
        self.next_id += 1
        self.points.append(point)
        self.selected_id = point["id"]
        self.redraw_all()

    def delete_selected_point(self):
        if self.selected_id is None:
            return
        selected = next((p for p in self.points if p["id"] == self.selected_id), None)
        if selected is None or selected["locked"]:
            return
        self.points = [p for p in self.points if p["id"] != self.selected_id]
        self.selected_id = None
        self.redraw_all()

    def redraw_all(self):
        max_depo = max(1, int(round(self._get_float(self.max_depo_value, 1))))
        current = max(0, min(int(round(self._get_float(self.current_depo_value, 0))), max_depo))
        self.max_depo_value.set(max_depo)
        self.current_depo_value.set(current)
        self.current_slider.configure(to=max_depo)
        self._updating_slider = True
        try:
            self.current_slider.set(current)
        finally:
            self._updating_slider = False
        self.current_label.configure(text=f"현재 적층량: {current}")
        self.update_mode_buttons()

        self.draw_graph()
        self.draw_build()
        self.draw_editor()
        self.status_label.configure(
            text=f"현재 깊이 {self.last_metrics['depth']:.2f} / 최대각 {self.last_metrics['angle']:.1f}도"
        )


def main():
    app = DentDepositionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
