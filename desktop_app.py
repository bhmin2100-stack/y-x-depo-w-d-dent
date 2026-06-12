# -*- coding: utf-8 -*-
"""Qt desktop app for conformal deposition dent modeling.

This is a Windows-first desktop implementation. It does not use HTML,
Streamlit, localhost, or a browser. The UI follows the same broad direction as
Gapseam: a dense Qt main window with a left parameter/control rail and
graphics-heavy work views.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


Point = Tuple[float, float]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def polyline_path(points: Sequence[QPointF]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    return path


def fmt_number(value: float) -> str:
    if abs(value) >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


@dataclass
class DepositionResult:
    view_x: List[float]
    surface: List[float]
    base_x: List[float]
    base_y: List[float]
    depth: float
    angle: float
    angle_index: int
    depth_index: int


class DentModel:
    def __init__(self) -> None:
        self.width = 10.0
        self.depth = 3.0
        self.max_depo = 20
        self.current_depo = 2
        self.smooth = False
        self.next_id = 1
        self.points: List[dict] = []
        self.reset_points()

    def reset_points(self) -> None:
        half = self.width / 2.0
        inset = max(self.width * 0.08, 0.01)
        coords = [
            (-half, 0.0, True),
            (-half + inset, 0.0, False),
            (-half + inset, -self.depth, False),
            (0.0, -self.depth, False),
            (half - inset, -self.depth, False),
            (half - inset, 0.0, False),
            (half, 0.0, True),
        ]
        self.points = []
        for x, y, locked in coords:
            self.points.append({"id": self.next_id, "x": float(x), "y": float(y), "locked": bool(locked)})
            self.next_id += 1

    def sorted_points(self) -> List[dict]:
        return sorted(self.points, key=lambda p: (float(p["x"]), int(p["id"])))

    def profile_at(self, x: float) -> float:
        pts = self.sorted_points()
        if not pts:
            return 0.0
        if x <= pts[0]["x"] or x >= pts[-1]["x"]:
            return 0.0
        for idx in range(len(pts) - 1):
            a = pts[idx]
            b = pts[idx + 1]
            if a["x"] <= x <= b["x"]:
                span = float(b["x"] - a["x"])
                if abs(span) < 1e-12:
                    return min(float(a["y"]), float(b["y"]))
                t = (x - float(a["x"])) / span
                if self.smooth and 0 < idx < len(pts) - 2:
                    p0 = pts[idx - 1]
                    p1 = a
                    p2 = b
                    p3 = pts[idx + 2]
                    t2 = t * t
                    t3 = t2 * t
                    y = 0.5 * (
                        2 * p1["y"]
                        + (-p0["y"] + p2["y"]) * t
                        + (2 * p0["y"] - 5 * p1["y"] + 4 * p2["y"] - p3["y"]) * t2
                        + (-p0["y"] + 3 * p1["y"] - 3 * p2["y"] + p3["y"]) * t3
                    )
                else:
                    y = float(a["y"]) + (float(b["y"]) - float(a["y"])) * t
                return min(0.0, float(y))
        return 0.0

    def field_margin(self) -> float:
        return max(self.width * 0.25, self.max_depo * 1.05, self.depth * 0.35)

    def evaluate_deposition(self, deposition: float, sample_count: int = 181, include_field: bool = False) -> DepositionResult:
        if sample_count % 2 == 0:
            sample_count += 1
        half = self.width / 2.0
        view_margin = self.field_margin() if include_field else 0.0
        margin = max(self.width * 0.35 + view_margin, deposition * 1.4 + view_margin, self.depth * 0.15)

        base_x = [(-half - margin) + (2 * (half + margin) * i) / (sample_count - 1) for i in range(sample_count)]
        base_y = [self.profile_at(x) if abs(x) <= half else 0.0 for x in base_x]
        view_min = -half - view_margin
        view_span = self.width + view_margin * 2
        view_x = [view_min + (view_span * i) / (sample_count - 1) for i in range(sample_count)]

        surface: List[float] = []
        for x in view_x:
            if deposition <= 0:
                surface.append(self.profile_at(x) if abs(x) <= half else 0.0)
                continue
            highest = -1e100
            for bx, by in zip(base_x, base_y):
                dx = x - bx
                if abs(dx) <= deposition:
                    cand = by + math.sqrt(max(deposition * deposition - dx * dx, 0.0))
                    if cand > highest:
                        highest = cand
            if highest < -1e90:
                highest = self.profile_at(x) if abs(x) <= half else 0.0
            surface.append(min(highest, deposition))

        dent_indices = [idx for idx, x in enumerate(view_x) if abs(x) <= half + 1e-9]
        if not dent_indices:
            dent_indices = list(range(len(view_x)))
        depth_index = min(dent_indices, key=lambda i: surface[i])
        depth = max(0.0, deposition - surface[depth_index])
        angle_index = -1
        max_slope = 0.0
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
        return DepositionResult(
            view_x=view_x,
            surface=surface,
            base_x=base_x,
            base_y=base_y,
            depth=depth,
            angle=math.degrees(math.atan(max_slope)),
            angle_index=angle_index,
            depth_index=depth_index,
        )

    def sweep(self) -> Tuple[List[float], List[float], List[float]]:
        count = max(70, self.max_depo * 7)
        xs = [self.max_depo * i / (count - 1) for i in range(count)]
        depths: List[float] = []
        angles: List[float] = []
        for value in xs:
            result = self.evaluate_deposition(value, sample_count=151, include_field=False)
            depths.append(result.depth)
            angles.append(result.angle)
        return xs, depths, angles


class PlotPanel(QFrame):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("plotPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        top.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("panelSubtle")
            top.addStretch(1)
            top.addWidget(sub)
        layout.addLayout(top)

    def add_canvas(self, canvas: QWidget) -> None:
        self.layout().addWidget(canvas, 1)


class BasePlotWidget(QWidget):
    def __init__(self, model: DentModel) -> None:
        super().__init__()
        self.model = model
        self.setMinimumSize(420, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._plot_rect = QRectF()

    def draw_frame(self, painter: QPainter, y_axis_color: QColor = QColor("#64748b")) -> QRectF:
        rect = self.rect().adjusted(54, 24, -26, -42)
        self._plot_rect = QRectF(rect)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for i in range(6):
            x = rect.left() + rect.width() * i / 5
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#94a3b8"), 1.2))
        painter.drawRect(rect)
        painter.setFont(QFont("Malgun Gothic", 8))
        painter.setPen(y_axis_color)
        return rect

    @staticmethod
    def draw_label_box(painter: QPainter, anchor: QPointF, text: str, fg: QColor, bg: QColor) -> None:
        font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 12
        height = metrics.height() + 6
        rect = QRectF(anchor.x(), anchor.y() - height, width, height)
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(fg)
        painter.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, text)


class SweepPlotWidget(BasePlotWidget):
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.draw_frame(painter)
        xs, depths, angles = self.model.sweep()
        max_depo = max(1, self.model.max_depo)
        y_max = max(max(depths) * 1.08 if depths else 0.0, self.model.depth, 1.0)

        def map_x(x: float) -> float:
            return rect.left() + x / max_depo * rect.width()

        def map_y(y: float) -> float:
            return rect.bottom() - y / y_max * rect.height()

        def map_z(z: float) -> float:
            return rect.bottom() - z / 90.0 * rect.height()

        painter.setFont(QFont("Malgun Gothic", 8))
        for i in range(6):
            x_val = max_depo * i / 5
            y_val = y_max * i / 5
            z_val = 90 * i / 5
            painter.setPen(QColor("#64748b"))
            painter.drawText(QRectF(map_x(x_val) - 28, rect.bottom() + 6, 56, 18), Qt.AlignmentFlag.AlignCenter, f"{x_val:.0f}")
            painter.setPen(QColor("#2563eb"))
            painter.drawText(QRectF(2, map_y(y_val) - 9, rect.left() - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{y_val:.1f}")
            painter.setPen(QColor("#dc2626"))
            painter.drawText(QRectF(rect.right() + 5, map_z(z_val) - 9, 40, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{z_val:.0f}")

        y_path = polyline_path([QPointF(map_x(x), map_y(y)) for x, y in zip(xs, depths)])
        z_path = polyline_path([QPointF(map_x(x), map_z(z)) for x, z in zip(xs, angles)])
        painter.setPen(QPen(QColor("#2563eb"), 2.6))
        painter.drawPath(y_path)
        painter.setPen(QPen(QColor("#dc2626"), 2.4))
        painter.drawPath(z_path)

        current_x = map_x(self.model.current_depo)
        pen = QPen(QColor("#334155"), 1.8)
        pen.setDashPattern([5, 4])
        painter.setPen(pen)
        painter.drawLine(QPointF(current_x, rect.top()), QPointF(current_x, rect.bottom()))

        painter.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#334155"))
        painter.drawText(QRectF(rect.left(), self.height() - 24, rect.width(), 20), Qt.AlignmentFlag.AlignCenter, "x 증착량")
        painter.setPen(QColor("#2563eb"))
        painter.drawText(QPointF(rect.left() + 8, rect.top() + 14), "y 깊이")
        painter.setPen(QColor("#dc2626"))
        painter.drawText(QPointF(rect.right() - 44, rect.top() + 14), "z 각도")


class BuildPlotWidget(BasePlotWidget):
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.draw_frame(painter)
        active = max(0, int(self.model.current_depo))
        half = self.model.width / 2.0
        x_min = -half
        x_span = self.model.width
        y_min = -self.model.depth * 1.12
        y_max = max(active * 1.18, self.model.depth * 0.24, 0.25)

        def map_x(x: float) -> float:
            return rect.left() + (x - x_min) / x_span * rect.width()

        def map_y(y: float) -> float:
            return rect.bottom() - (y - y_min) / (y_max - y_min) * rect.height()

        painter.setFont(QFont("Malgun Gothic", 8))
        for i in range(6):
            x_val = x_min + x_span * i / 5
            y_val = y_min + (y_max - y_min) * i / 5
            painter.setPen(QColor("#64748b"))
            painter.drawText(QRectF(map_x(x_val) - 28, rect.bottom() + 6, 56, 18), Qt.AlignmentFlag.AlignCenter, f"{x_val:.1f}")
            painter.drawText(QRectF(0, map_y(y_val) - 9, rect.left() - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{y_val:.1f}")

        layers = [self.model.evaluate_deposition(dep, sample_count=231, include_field=True) for dep in range(active + 1)]
        painter.save()
        painter.setClipRect(rect)
        fills = [QColor("#bff2e9"), QColor("#c8f7d4"), QColor("#e1f6aa")]
        lines = [QColor("#0f766e"), QColor("#047857"), QColor("#4d7c0f")]
        for i in range(1, len(layers)):
            prev = layers[i - 1]
            cur = layers[i]
            poly = QPolygonF()
            for x, y in zip(cur.view_x, cur.surface):
                poly.append(QPointF(map_x(x), map_y(y)))
            for x, y in reversed(list(zip(prev.view_x, prev.surface))):
                poly.append(QPointF(map_x(x), map_y(y)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fills[i % len(fills)]))
            painter.drawPolygon(poly)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(lines[i % len(lines)], 1.2))
            painter.drawPath(polyline_path([QPointF(map_x(x), map_y(y)) for x, y in zip(cur.view_x, cur.surface)]))

        base = layers[0]
        last = layers[-1]
        base_pen = QPen(QColor("#475569"), 1.8)
        base_pen.setDashPattern([5, 5])
        painter.setPen(base_pen)
        painter.drawPath(polyline_path([QPointF(map_x(x), map_y(y)) for x, y in zip(base.view_x, base.surface)]))
        painter.setPen(QPen(QColor("#047857"), 2.5))
        painter.drawPath(polyline_path([QPointF(map_x(x), map_y(y)) for x, y in zip(last.view_x, last.surface)]))
        painter.restore()

        flat_y = map_y(active)
        painter.setPen(QPen(QColor("#111827"), 2))
        painter.drawLine(QPointF(rect.left(), flat_y), QPointF(rect.right(), flat_y))
        self.draw_label_box(painter, QPointF(rect.left() + 8, max(rect.top() + 24, flat_y - 8)), f"현재 적층량 x={active}", QColor("#0f172a"), QColor("#f8fafc"))

        if last.angle_index >= 0:
            x = clamp(map_x(last.view_x[last.angle_index]), rect.left(), rect.right())
            y = clamp(map_y(last.surface[last.angle_index]), rect.top(), rect.bottom())
            painter.setPen(QPen(QColor("#dc2626"), 1.5))
            painter.setBrush(QBrush(QColor("#dc2626")))
            painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
            self.draw_label_box(painter, QPointF(x + 10, y - 12), f"최대각 {last.angle:.1f}도", QColor("#991b1b"), QColor("#fee2e2"))

        if last.depth_index >= 0:
            x = clamp(map_x(last.view_x[last.depth_index]), rect.left(), rect.right())
            y = clamp(map_y(last.surface[last.depth_index]), rect.top(), rect.bottom())
            pen = QPen(QColor("#2563eb"), 1.8)
            pen.setDashPattern([4, 4])
            painter.setPen(pen)
            painter.drawLine(QPointF(x, flat_y), QPointF(x, y))
            painter.setBrush(QBrush(QColor("#2563eb")))
            painter.drawEllipse(QPointF(x, y), 4.0, 4.0)
            self.draw_label_box(painter, QPointF(x + 10, (flat_y + y) / 2), f"현재 깊이 {last.depth:.2f}", QColor("#1d4ed8"), QColor("#dbeafe"))

        painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#64748b"))
        painter.drawText(QPointF(rect.left() + 10, rect.bottom() - 8), "필드")
        painter.drawText(QRectF(map_x(0) - 30, rect.bottom() - 24, 60, 18), Qt.AlignmentFlag.AlignCenter, "덴트")
        painter.drawText(QRectF(rect.right() - 50, rect.bottom() - 24, 48, 18), Qt.AlignmentFlag.AlignRight, "필드")
        self.model.last_depth = last.depth
        self.model.last_angle = last.angle


class StructureEditorWidget(BasePlotWidget):
    changed = Signal()

    def __init__(self, model: DentModel) -> None:
        super().__init__(model)
        self.setMinimumHeight(280)
        self.mode = "move"
        self.selected_id: Optional[int] = None
        self.dragging_id: Optional[int] = None
        self.setMouseTracking(True)
        self._map: Optional[Tuple[QRectF, float, float, float, float]] = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.draw_frame(painter)
        half = self.model.width / 2.0
        x_min = -half
        x_span = self.model.width
        y_min = -self.model.depth * 1.15
        y_max = max(self.model.depth * 0.25, 0.25)
        self._map = (rect, x_min, x_span, y_min, y_max)

        def map_x(x: float) -> float:
            return rect.left() + (x - x_min) / x_span * rect.width()

        def map_y(y: float) -> float:
            return rect.bottom() - (y - y_min) / (y_max - y_min) * rect.height()

        painter.setFont(QFont("Malgun Gothic", 8))
        for i in range(6):
            x_val = x_min + x_span * i / 5
            y_val = y_min + (y_max - y_min) * i / 5
            painter.setPen(QColor("#64748b"))
            painter.drawText(QRectF(map_x(x_val) - 28, rect.bottom() + 6, 56, 18), Qt.AlignmentFlag.AlignCenter, f"{x_val:.1f}")
            painter.drawText(QRectF(0, map_y(y_val) - 9, rect.left() - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{y_val:.1f}")

        samples = []
        for i in range(241):
            x = -half + self.model.width * i / 240
            samples.append(QPointF(map_x(x), map_y(self.model.profile_at(x))))
        area = QPolygonF([QPointF(map_x(-half), map_y(0.0))] + samples + [QPointF(map_x(half), map_y(0.0))])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(219, 234, 254, 160)))
        painter.drawPolygon(area)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#2563eb"), 2.5))
        painter.drawPath(polyline_path(samples))
        painter.setPen(QPen(QColor("#111827"), 1.7))
        painter.drawLine(QPointF(map_x(-half), map_y(0)), QPointF(map_x(half), map_y(0)))

        for idx, point in enumerate(self.model.sorted_points(), start=1):
            px = map_x(point["x"])
            py = map_y(point["y"])
            radius = 5.5 if point["locked"] else 7.5
            painter.setBrush(QBrush(QColor("#facc15" if point["id"] == self.selected_id else "#ffffff")))
            painter.setPen(QPen(QColor("#64748b" if point["locked"] else "#0f172a"), 2))
            painter.drawEllipse(QPointF(px, py), radius, radius)
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            painter.drawText(QPointF(px + 10, py - 9), str(idx))

        painter.setPen(QColor("#334155"))
        painter.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        painter.drawText(QPointF(rect.left(), self.height() - 12), f"W={self.model.width:.3f}, D={self.model.depth:.3f}")
        painter.drawText(QRectF(rect.left(), self.height() - 24, rect.width(), 20), Qt.AlignmentFlag.AlignCenter, "x 위치")
        painter.drawText(QPointF(12, rect.center().y()), "y 높이")

    def model_from_pos(self, pos: QPointF) -> Point:
        assert self._map is not None
        rect, x_min, x_span, y_min, y_max = self._map
        x = x_min + ((pos.x() - rect.left()) / rect.width()) * x_span
        y = y_max - ((pos.y() - rect.top()) / rect.height()) * (y_max - y_min)
        return x, y

    def point_at(self, pos: QPointF) -> Optional[dict]:
        if self._map is None:
            return None
        rect, x_min, x_span, y_min, y_max = self._map

        def map_x(x: float) -> float:
            return rect.left() + (x - x_min) / x_span * rect.width()

        def map_y(y: float) -> float:
            return rect.bottom() - (y - y_min) / (y_max - y_min) * rect.height()

        best = None
        best_dist = 14.0
        for point in self.model.points:
            dist = math.hypot(pos.x() - map_x(point["x"]), pos.y() - map_y(point["y"]))
            if dist <= best_dist:
                best = point
                best_dist = dist
        return best

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        point = self.point_at(pos)
        if self.mode == "delete":
            if point and not point["locked"]:
                self.model.points = [p for p in self.model.points if p["id"] != point["id"]]
                self.selected_id = None
                self.changed.emit()
            return
        if self.mode == "add" and point is None:
            self.add_point(pos)
            return
        if point:
            self.selected_id = int(point["id"])
            self.dragging_id = None if point["locked"] else int(point["id"])
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.dragging_id is None:
            return
        point = next((p for p in self.model.points if p["id"] == self.dragging_id), None)
        if not point or point["locked"]:
            return
        x, y = self.model_from_pos(event.position())
        gap = self.model.width * 0.01
        point["x"] = clamp(x, -self.model.width / 2 + gap, self.model.width / 2 - gap)
        point["y"] = clamp(y, -self.model.depth * 1.15, 0.0)
        self.changed.emit()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self.dragging_id = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.point_at(event.position()) is None:
            self.add_point(event.position())

    def add_point(self, pos: QPointF) -> None:
        x, y = self.model_from_pos(pos)
        gap = self.model.width * 0.02
        point = {
            "id": self.model.next_id,
            "x": clamp(x, -self.model.width / 2 + gap, self.model.width / 2 - gap),
            "y": clamp(y, -self.model.depth * 1.15, 0.0),
            "locked": False,
        }
        self.model.next_id += 1
        self.model.points.append(point)
        self.selected_id = point["id"]
        self.changed.emit()

    def delete_selected(self) -> None:
        if self.selected_id is None:
            return
        selected = next((p for p in self.model.points if p["id"] == self.selected_id), None)
        if selected is None or selected["locked"]:
            return
        self.model.points = [p for p in self.model.points if p["id"] != self.selected_id]
        self.selected_id = None
        self.changed.emit()


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        self.value_label = QLabel("-")
        self.value_label.setObjectName("metricValue")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.model = DentModel()
        self.setWindowTitle("Dent Deposition Model - Windows")
        self.resize(1380, 900)
        self.setMinimumSize(1120, 760)
        self._syncing_controls = False
        self._build_ui()
        self._wire()
        self.refresh_all()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #e5e7eb; }
            QWidget { font-family: "Malgun Gothic", "Segoe UI"; font-size: 10pt; color: #0f172a; }
            QFrame#leftRail, QFrame#plotPanel, QFrame#metricCard {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            QLabel#appTitle { font-size: 18pt; font-weight: 800; color: #0f172a; }
            QLabel#sectionTitle, QLabel#panelTitle { font-weight: 800; color: #172033; }
            QLabel#panelSubtle, QLabel#metricTitle, QLabel#hint { color: #64748b; }
            QLabel#metricValue { font-size: 16pt; font-weight: 800; color: #0f172a; }
            QDoubleSpinBox, QSpinBox {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 6px;
                background: #ffffff;
            }
            QPushButton, QToolButton {
                border: 1px solid #94a3b8;
                border-radius: 4px;
                padding: 6px 8px;
                background: #f8fafc;
                font-weight: 700;
            }
            QPushButton:hover, QToolButton:hover { background: #eef2ff; }
            QToolButton:checked {
                background: #2563eb;
                color: #ffffff;
                border-color: #1d4ed8;
            }
            QSlider::groove:horizontal { height: 6px; background: #dbeafe; border-radius: 3px; }
            QSlider::handle:horizontal { width: 16px; margin: -5px 0; border-radius: 8px; background: #2563eb; }
            """
        )

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.setCentralWidget(central)

        left = QFrame()
        left.setObjectName("leftRail")
        left.setFixedWidth(310)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        title = QLabel("컨포멀 증착\n덴트 모델")
        title.setObjectName("appTitle")
        left_layout.addWidget(title)

        subtitle = QLabel("Windows 전용 Qt 프로그램")
        subtitle.setObjectName("hint")
        left_layout.addWidget(subtitle)

        self.metric_depth = MetricCard("현재 덴트 깊이")
        self.metric_angle = MetricCard("최대 접선각")
        metric_grid = QGridLayout()
        metric_grid.setContentsMargins(0, 0, 0, 0)
        metric_grid.setSpacing(8)
        metric_grid.addWidget(self.metric_depth, 0, 0)
        metric_grid.addWidget(self.metric_angle, 0, 1)
        left_layout.addLayout(metric_grid)

        left_layout.addWidget(self._section_label("형상 / 적층 조건"))
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(0.1, 1000.0)
        self.spin_width.setDecimals(3)
        self.spin_width.setSingleStep(0.5)
        self.spin_width.setValue(self.model.width)
        self.spin_depth = QDoubleSpinBox()
        self.spin_depth.setRange(0.1, 1000.0)
        self.spin_depth.setDecimals(3)
        self.spin_depth.setSingleStep(0.25)
        self.spin_depth.setValue(self.model.depth)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 1000)
        self.spin_max.setValue(self.model.max_depo)
        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)
        self._add_form_row(form, 0, "W 덴트 폭", self.spin_width)
        self._add_form_row(form, 1, "D 초기 깊이", self.spin_depth)
        self._add_form_row(form, 2, "최대 적층량", self.spin_max)
        left_layout.addLayout(form)

        self.current_label = QLabel("현재 적층량: 2")
        self.current_label.setObjectName("sectionTitle")
        left_layout.addWidget(self.current_label)
        self.slider_current = QSlider(Qt.Orientation.Horizontal)
        self.slider_current.setRange(0, self.model.max_depo)
        self.slider_current.setSingleStep(1)
        self.slider_current.setPageStep(1)
        self.slider_current.setValue(self.model.current_depo)
        left_layout.addWidget(self.slider_current)

        self.chk_smooth = QCheckBox("부드러운 곡선")
        self.chk_smooth.setChecked(self.model.smooth)
        left_layout.addWidget(self.chk_smooth)

        left_layout.addWidget(self._section_label("점 편집 모드"))
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        self.btn_move = QToolButton()
        self.btn_move.setText("이동")
        self.btn_move.setCheckable(True)
        self.btn_move.setChecked(True)
        self.btn_add = QToolButton()
        self.btn_add.setText("점 추가")
        self.btn_add.setCheckable(True)
        self.btn_delete = QToolButton()
        self.btn_delete.setText("점 삭제")
        self.btn_delete.setCheckable(True)
        mode_row.addWidget(self.btn_move)
        mode_row.addWidget(self.btn_add)
        mode_row.addWidget(self.btn_delete)
        left_layout.addLayout(mode_row)

        self.btn_reset = QPushButton("기본 직사각형으로 초기화")
        left_layout.addWidget(self.btn_reset)

        hint = QLabel(
            "아래 점 편집창에서 흰 점을 직접 드래그합니다.\n"
            "추가 모드: 빈 곳 클릭\n"
            "삭제 모드: 점 클릭\n"
            "양 끝 경계점은 W 폭 고정용이라 삭제되지 않습니다."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)
        left_layout.addStretch(1)

        root.addWidget(left)

        workspace = QSplitter(Qt.Orientation.Vertical)
        workspace.setChildrenCollapsible(False)
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)

        self.sweep_view = SweepPlotWidget(self.model)
        self.build_view = BuildPlotWidget(self.model)
        sweep_panel = PlotPanel("y(x), z(x) 그래프", "깊이와 최대 접선각")
        build_panel = PlotPanel("쌓이는 모습", "1 단위 적층 / W 폭 고정")
        sweep_panel.add_canvas(self.sweep_view)
        build_panel.add_canvas(self.build_view)
        top.addWidget(sweep_panel)
        top.addWidget(build_panel)
        top.setSizes([1, 1])

        self.editor_view = StructureEditorWidget(self.model)
        editor_panel = PlotPanel("기본 덴트 구조 점 편집", "계산 전 기본 구조만 표시")
        editor_panel.add_canvas(self.editor_view)
        workspace.addWidget(top)
        workspace.addWidget(editor_panel)
        workspace.setSizes([560, 310])
        root.addWidget(workspace, 1)

        self.setStatusBar(QStatusBar())
        self.act_exit = QAction("종료", self)
        self.act_exit.triggered.connect(self.close)
        self.menuBar().addMenu("파일").addAction(self.act_exit)

    def _wire(self) -> None:
        self.spin_width.valueChanged.connect(self.on_width_changed)
        self.spin_depth.valueChanged.connect(self.on_depth_changed)
        self.spin_max.valueChanged.connect(self.on_max_changed)
        self.slider_current.valueChanged.connect(self.on_current_changed)
        self.chk_smooth.toggled.connect(self.on_smooth_changed)
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_move.clicked.connect(lambda: self.set_editor_mode("move"))
        self.btn_add.clicked.connect(lambda: self.set_editor_mode("add"))
        self.btn_delete.clicked.connect(lambda: self.set_editor_mode("delete"))
        self.editor_view.changed.connect(self.refresh_all)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    @staticmethod
    def _add_form_row(layout: QGridLayout, row: int, label: str, widget: QWidget) -> None:
        lab = QLabel(label)
        lab.setObjectName("hint")
        layout.addWidget(lab, row, 0)
        layout.addWidget(widget, row, 1)

    def set_editor_mode(self, mode: str) -> None:
        self.btn_move.setChecked(mode == "move")
        self.btn_add.setChecked(mode == "add")
        self.btn_delete.setChecked(mode == "delete")
        self.editor_view.set_mode(mode)
        self.statusBar().showMessage(f"점 편집 모드: {mode}", 1500)

    def on_width_changed(self, value: float) -> None:
        if self._syncing_controls:
            return
        old_half = max(abs(self.model.points[0]["x"]), abs(self.model.points[-1]["x"]), 0.1)
        self.model.width = max(0.1, float(value))
        scale = (self.model.width / 2.0) / old_half
        for point in self.model.points:
            point["x"] *= scale
        pts = self.model.sorted_points()
        pts[0]["x"] = -self.model.width / 2.0
        pts[-1]["x"] = self.model.width / 2.0
        self.refresh_all()

    def on_depth_changed(self, value: float) -> None:
        if self._syncing_controls:
            return
        old_depth = max(0.1, abs(min(p["y"] for p in self.model.points)))
        self.model.depth = max(0.1, float(value))
        scale = self.model.depth / old_depth
        for point in self.model.points:
            point["y"] = clamp(point["y"] * scale, -self.model.depth * 1.2, 0.0)
        self.refresh_all()

    def on_max_changed(self, value: int) -> None:
        if self._syncing_controls:
            return
        self.model.max_depo = max(1, int(value))
        self.model.current_depo = min(self.model.current_depo, self.model.max_depo)
        self.refresh_all()

    def on_current_changed(self, value: int) -> None:
        if self._syncing_controls:
            return
        self.model.current_depo = int(value)
        self.refresh_all()

    def on_smooth_changed(self, checked: bool) -> None:
        self.model.smooth = bool(checked)
        self.refresh_all()

    def on_reset(self) -> None:
        self.model.reset_points()
        self.editor_view.selected_id = None
        self.refresh_all()

    def refresh_all(self) -> None:
        self._syncing_controls = True
        try:
            self.spin_width.setValue(self.model.width)
            self.spin_depth.setValue(self.model.depth)
            self.spin_max.setValue(self.model.max_depo)
            self.slider_current.setRange(0, self.model.max_depo)
            self.slider_current.setValue(self.model.current_depo)
            self.current_label.setText(f"현재 적층량: {self.model.current_depo}")
        finally:
            self._syncing_controls = False

        for widget in (self.sweep_view, self.build_view, self.editor_view):
            widget.update()
        result = self.model.evaluate_deposition(self.model.current_depo, sample_count=231, include_field=False)
        self.metric_depth.set_value(f"{result.depth:.2f}")
        self.metric_angle.set_value(f"{result.angle:.1f}°")
        self.statusBar().showMessage(
            f"W={self.model.width:.3f}, D={self.model.depth:.3f}, x={self.model.current_depo}, 깊이={result.depth:.3f}, 최대각={result.angle:.2f}°"
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.editor_view.delete_selected()
            return
        super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Dent Deposition Model")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
