from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from point_editor import make_point_editor_html


@dataclass(frozen=True)
class DentParams:
    width: float
    depth: float
    shape: str
    wall_power: float
    flat_bottom_fraction: float
    asymmetry: float
    sample_count: int


def dent_profile(x_pos: np.ndarray, params: DentParams) -> np.ndarray:
    half_width = params.width / 2.0
    u = np.clip(x_pos / half_width, -1.0, 1.0)

    if params.shape == "Cosine bowl":
        profile = -0.5 * params.depth * (1.0 + np.cos(np.pi * u))
    elif params.shape == "Parabolic bowl":
        profile = -params.depth * (1.0 - np.abs(u) ** params.wall_power)
    elif params.shape == "V groove":
        profile = -params.depth * (1.0 - np.abs(u))
    else:
        flat_half = np.clip(params.flat_bottom_fraction, 0.0, 0.9)
        side_span = max(1.0 - flat_half, 1e-6)
        side_t = np.clip((np.abs(u) - flat_half) / side_span, 0.0, 1.0)
        profile = -params.depth * (1.0 - side_t ** params.wall_power)

    if params.asymmetry:
        tilt = params.asymmetry * params.depth * u
        profile = np.minimum(profile + tilt, 0.0)
        profile -= np.min(profile) + params.depth

    return np.minimum(profile, 0.0)


def deposited_surface(
    x_grid: np.ndarray,
    base_x: np.ndarray,
    base_y: np.ndarray,
    deposition: float,
    top_plane_y: float,
) -> np.ndarray:
    if deposition <= 0:
        return np.interp(x_grid, base_x, base_y)

    surface = np.full_like(x_grid, -np.inf, dtype=float)
    for center_x, center_y in zip(base_x, base_y):
        dx = x_grid - center_x
        mask = np.abs(dx) <= deposition
        if np.any(mask):
            candidate = center_y + np.sqrt(np.maximum(deposition**2 - dx[mask] ** 2, 0.0))
            surface[mask] = np.maximum(surface[mask], candidate)

    fallback = np.interp(x_grid, base_x, base_y)
    surface = np.where(np.isfinite(surface), surface, fallback)
    return np.minimum(surface, top_plane_y)


def evaluate_deposition(params: DentParams, deposition: float, view_margin: float = 0.0):
    half_width = params.width / 2.0
    margin = max(params.width * 0.35 + view_margin, deposition * 1.4 + view_margin, params.depth * 0.15)
    sample_count = params.sample_count if params.sample_count % 2 else params.sample_count + 1
    base_x = np.linspace(-half_width - margin, half_width + margin, sample_count)
    inside = np.abs(base_x) <= half_width
    base_y = np.zeros_like(base_x)
    base_y[inside] = dent_profile(base_x[inside], params)

    view_x = np.linspace(-half_width - view_margin, half_width + view_margin, sample_count)
    surface = deposited_surface(view_x, base_x, base_y, deposition, deposition)
    dent_mask = np.abs(view_x) <= half_width
    dent_surface = surface[dent_mask] if np.any(dent_mask) else surface
    dent_x = view_x[dent_mask] if np.any(dent_mask) else view_x
    depth = max(0.0, deposition - float(np.min(dent_surface)))

    if len(dent_x) > 2:
        slope = np.gradient(dent_surface, dent_x)
        max_angle = float(np.degrees(np.arctan(np.max(np.abs(slope)))))
    else:
        max_angle = 0.0

    return view_x, surface, depth, max_angle, base_x, base_y


def sweep(params: DentParams, max_deposition: float, steps: int):
    deposition_values = np.linspace(0.0, max_deposition, steps)
    depths = []
    angles = []

    for value in deposition_values:
        _, _, depth, angle, _, _ = evaluate_deposition(params, float(value))
        depths.append(depth)
        angles.append(angle)

    return deposition_values, np.array(depths), np.array(angles)


def make_sweep_plot(depositions, depths, angles, selected_deposition):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=depositions,
            y=depths,
            name="y: 남은 덴트 깊이",
            mode="lines",
            line={"width": 3, "color": "#2563eb"},
            hovertemplate="증착량 x=%{x:.3f}<br>깊이 y=%{y:.3f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=depositions,
            y=angles,
            name="z: 최대 접선각",
            mode="lines",
            line={"width": 3, "color": "#dc2626"},
            hovertemplate="증착량 x=%{x:.3f}<br>각도 z=%{y:.2f}도<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_vline(
        x=selected_deposition,
        line_width=2,
        line_dash="dash",
        line_color="#334155",
    )
    fig.update_layout(
        height=500,
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hovermode="x unified",
    )
    fig.update_xaxes(title_text="x: 컨포멀 증착량")
    fig.update_yaxes(title_text="y: 남은 덴트 깊이", secondary_y=False)
    fig.update_yaxes(title_text="z: 최대 접선각 (도)", secondary_y=True)
    return fig


def make_profile_plot(params, deposition):
    view_x, surface, depth, angle, base_x, base_y = evaluate_deposition(params, deposition)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=base_x,
            y=base_y,
            name="초기 덴트",
            mode="lines",
            line={"width": 2, "color": "#64748b", "dash": "dash"},
            hovertemplate="x=%{x:.3f}<br>초기 높이=%{y:.3f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=view_x,
            y=surface,
            name="증착 후 표면",
            mode="lines",
            line={"width": 4, "color": "#059669"},
            hovertemplate="x=%{x:.3f}<br>표면 높이=%{y:.3f}<extra></extra>",
        )
    )
    fig.add_hline(y=deposition, line_width=2, line_color="#111827")
    fig.update_layout(
        height=430,
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
        title=f"선택 증착량 x={deposition:.3f}, 남은 깊이 y={depth:.3f}, 최대 접선각 z={angle:.2f}도",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(title_text="덴트 횡방향 위치")
    fig.update_yaxes(
        title_text="높이",
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
    )
    return fig


def make_build_up_plot(params, selected_deposition, layer_count, frame_index, show_all_layers):
    active_deposition = selected_deposition * frame_index / max(layer_count, 1)
    visible_layers = max(frame_index, 1)
    layer_values = np.linspace(0.0, active_deposition, visible_layers + 1)
    field_margin = max(params.width * 0.25, selected_deposition * 1.15, params.depth * 0.35)

    surfaces = []
    view_x = None
    base_x = None
    base_y = None
    for value in layer_values:
        view_x, surface, _, _, base_x, base_y = evaluate_deposition(
            params,
            float(value),
            view_margin=field_margin,
        )
        surfaces.append(surface)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=base_x,
            y=base_y,
            name="초기 덴트와 필드",
            mode="lines",
            line={"width": 2, "color": "#475569"},
            hovertemplate="위치=%{x:.3f}<br>초기 높이=%{y:.3f}<extra></extra>",
        )
    )

    if show_all_layers:
        previous_surface = surfaces[0]
        for index, current_surface in enumerate(surfaces[1:], start=1):
            opacity = 0.18 + 0.34 * index / max(visible_layers, 1)
            palette = [
                f"rgba(20, 184, 166, {opacity:.3f})",
                f"rgba(16, 185, 129, {opacity:.3f})",
                f"rgba(132, 204, 22, {opacity:.3f})",
            ]
            color = palette[index % len(palette)]
            line_color = ["#0f766e", "#047857", "#4d7c0f"][index % 3]
            fig.add_trace(
                go.Scatter(
                    x=view_x,
                    y=previous_surface,
                    mode="lines",
                    line={"width": 0, "color": "rgba(0,0,0,0)"},
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=view_x,
                    y=current_surface,
                    name=f"증착층 {index}",
                    mode="lines",
                    fill="tonexty",
                    fillcolor=color,
                    line={"width": 1.7, "color": line_color},
                    hovertemplate=(
                        f"증착층 {index}<br>"
                        f"증착량={layer_values[index]:.3f}<br>"
                        "위치=%{x:.3f}<br>높이=%{y:.3f}<extra></extra>"
                    ),
                )
            )
            previous_surface = current_surface
    else:
        fig.add_trace(
            go.Scatter(
                x=view_x,
                y=surfaces[0],
                mode="lines",
                line={"width": 0, "color": "rgba(0,0,0,0)"},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=view_x,
                y=surfaces[-1],
                name="누적 증착막",
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(16, 185, 129, 0.42)",
                line={"width": 3, "color": "#047857"},
                hovertemplate="위치=%{x:.3f}<br>높이=%{y:.3f}<extra></extra>",
            )
        )

    current_depth = active_deposition - float(np.min(surfaces[-1]))
    fig.add_hline(
        y=active_deposition,
        line_width=2,
        line_color="#111827",
        annotation_text=f"필드 상단 = {active_deposition:.3f}",
        annotation_position="top right",
    )
    fig.add_annotation(
        x=0,
        y=float(np.min(surfaces[-1])),
        text=f"남은 깊이 {current_depth:.3f}",
        showarrow=True,
        arrowhead=2,
        ax=0,
        ay=-42,
        bgcolor="rgba(255,255,255,0.86)",
        bordercolor="#94a3b8",
    )
    fig.update_layout(
        height=560,
        margin={"l": 10, "r": 10, "t": 45, "b": 10},
        title=f"증착 적층 보기: 필드 포함, 현재 x={active_deposition:.3f} / 선택 x={selected_deposition:.3f}",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hovermode="x",
    )
    fig.update_xaxes(title_text="횡방향 위치 (필드 + 덴트 + 필드)")
    fig.update_yaxes(
        title_text="높이",
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
    )
    return fig


def initial_control_points(params: DentParams, point_count: int = 9):
    xs = np.linspace(-params.width / 2.0, params.width / 2.0, point_count)
    ys = dent_profile(xs, params)
    ys[0] = 0.0
    ys[-1] = 0.0
    return [{"x": float(x), "y": float(y)} for x, y in zip(xs, ys)]


def main():
    st.set_page_config(page_title="컨포멀 증착 덴트 모델", layout="wide")
    st.title("컨포멀 증착 덴트 모델")

    with st.sidebar:
        st.header("덴트 형상")
        width = st.number_input("W: 덴트 폭", min_value=0.1, value=10.0, step=0.5)
        depth = st.number_input("D: 초기 덴트 깊이", min_value=0.1, value=3.0, step=0.25)
        shape_options = {
            "코사인 볼": "Cosine bowl",
            "포물선 볼": "Parabolic bowl",
            "V 홈": "V groove",
            "평평한 바닥 트렌치": "Flat-bottom trench",
        }
        shape_label = st.selectbox("덴트 형상", list(shape_options.keys()))
        shape = shape_options[shape_label]
        wall_power = st.slider("벽면 형상 지수", min_value=0.5, max_value=6.0, value=2.0, step=0.1)
        flat_bottom = st.slider(
            "평평한 바닥 비율",
            min_value=0.0,
            max_value=0.9,
            value=0.35,
            step=0.05,
            disabled=shape != "Flat-bottom trench",
        )
        asymmetry = st.slider("비대칭", min_value=-0.8, max_value=0.8, value=0.0, step=0.05)

        st.header("증착량 sweep")
        max_deposition = st.number_input(
            "최대 증착량 x",
            min_value=0.01,
            value=float(max(depth * 1.25, width * 0.25)),
            step=0.25,
        )
        selected_deposition = st.slider(
            "선택 증착량 x",
            min_value=0.0,
            max_value=float(max_deposition),
            value=float(min(depth * 0.5, max_deposition)),
            step=float(max_deposition / 250.0),
        )
        steps = st.slider("Sweep 해상도", min_value=50, max_value=450, value=180, step=10)
        samples = st.slider("형상 해상도", min_value=160, max_value=900, value=360, step=20)

        st.header("증착 적층 보기")
        layer_count = st.slider("층 개수", min_value=3, max_value=30, value=12, step=1)
        build_frame = st.slider("적층 단계", min_value=0, max_value=int(layer_count), value=int(layer_count))
        show_all_layers = st.checkbox("개별 층 경계 표시", value=True)

    params = DentParams(
        width=float(width),
        depth=float(depth),
        shape=shape,
        wall_power=float(wall_power),
        flat_bottom_fraction=float(flat_bottom),
        asymmetry=float(asymmetry),
        sample_count=int(samples),
    )

    depositions, depths, angles = sweep(params, float(max_deposition), int(steps))
    current_depth = float(np.interp(selected_deposition, depositions, depths))
    current_angle = float(np.interp(selected_deposition, depositions, angles))
    improvement = max(0.0, params.depth - current_depth)
    improvement_pct = 100.0 * improvement / params.depth

    metric_cols = st.columns(4)
    metric_cols[0].metric("남은 깊이 y", f"{current_depth:.3f}")
    metric_cols[1].metric("깊이 개선", f"{improvement:.3f}", f"{improvement_pct:.1f}%")
    metric_cols[2].metric("최대 접선각 z", f"{current_angle:.2f}도")
    metric_cols[3].metric("W / D", f"{params.width / params.depth:.2f}")

    charts_tab, build_tab, point_editor_tab = st.tabs(["y(x), z(x)", "증착 적층", "점 편집"])
    with charts_tab:
        left, right = st.columns([1.2, 1.0])
        with left:
            st.plotly_chart(
                make_sweep_plot(depositions, depths, angles, selected_deposition),
                use_container_width=True,
            )
        with right:
            st.plotly_chart(make_profile_plot(params, selected_deposition), use_container_width=True)

    with build_tab:
        st.plotly_chart(
            make_build_up_plot(
                params,
                float(selected_deposition),
                int(layer_count),
                int(build_frame),
                bool(show_all_layers),
            ),
            use_container_width=True,
        )

    with point_editor_tab:
        components.html(
            make_point_editor_html(
                {
                    "width": params.width,
                    "depth": params.depth,
                    "maxDeposition": float(max_deposition),
                    "selectedDeposition": float(selected_deposition),
                    "layerCount": int(layer_count),
                    "points": initial_control_points(params),
                }
            ),
            height=1230,
            scrolling=True,
        )

    st.caption(
        "모델: 초기 덴트 경계를 컨포멀 증착 거리 x만큼 확장한 것으로 계산합니다. "
        "남은 깊이 y는 증착 후 필드 상단면에서 덴트 내부의 가장 낮은 지점까지의 거리이고, "
        "z는 덴트 내부 증착 표면의 최대 절대 접선각입니다."
    )


if __name__ == "__main__":
    main()
