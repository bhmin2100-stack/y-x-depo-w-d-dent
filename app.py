import math
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


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


def evaluate_deposition(params: DentParams, deposition: float):
    half_width = params.width / 2.0
    margin = max(params.width * 0.35, deposition * 1.4, params.depth * 0.15)
    sample_count = params.sample_count if params.sample_count % 2 else params.sample_count + 1
    base_x = np.linspace(-half_width - margin, half_width + margin, sample_count)
    inside = np.abs(base_x) <= half_width
    base_y = np.zeros_like(base_x)
    base_y[inside] = dent_profile(base_x[inside], params)

    view_x = np.linspace(-half_width, half_width, sample_count)
    surface = deposited_surface(view_x, base_x, base_y, deposition, deposition)
    depth = max(0.0, deposition - float(np.min(surface)))

    if len(view_x) > 2:
        slope = np.gradient(surface, view_x)
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
            name="y: remaining dent depth",
            mode="lines",
            line={"width": 3, "color": "#2563eb"},
            hovertemplate="depo x=%{x:.3f}<br>depth y=%{y:.3f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=depositions,
            y=angles,
            name="z: max tangent angle",
            mode="lines",
            line={"width": 3, "color": "#dc2626"},
            hovertemplate="depo x=%{x:.3f}<br>angle z=%{y:.2f} deg<extra></extra>",
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
    fig.update_xaxes(title_text="x: conformal deposition amount")
    fig.update_yaxes(title_text="y: remaining dent depth", secondary_y=False)
    fig.update_yaxes(title_text="z: max tangent angle (deg)", secondary_y=True)
    return fig


def make_profile_plot(params, deposition):
    view_x, surface, depth, angle, base_x, base_y = evaluate_deposition(params, deposition)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=base_x,
            y=base_y,
            name="initial dent",
            mode="lines",
            line={"width": 2, "color": "#64748b", "dash": "dash"},
            hovertemplate="x=%{x:.3f}<br>initial y=%{y:.3f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=view_x,
            y=surface,
            name="after deposition",
            mode="lines",
            line={"width": 4, "color": "#059669"},
            hovertemplate="x=%{x:.3f}<br>surface y=%{y:.3f}<extra></extra>",
        )
    )
    fig.add_hline(y=deposition, line_width=2, line_color="#111827")
    fig.update_layout(
        height=430,
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
        title=f"Selected depo x={deposition:.3f}, remaining depth y={depth:.3f}, max angle z={angle:.2f} deg",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(title_text="lateral position across dent")
    fig.update_yaxes(
        title_text="height",
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
    )
    return fig


def main():
    st.set_page_config(page_title="Conformal Deposition Dent Model", layout="wide")
    st.title("Conformal Deposition Dent Model")

    with st.sidebar:
        st.header("Dent geometry")
        width = st.number_input("W: dent width", min_value=0.1, value=10.0, step=0.5)
        depth = st.number_input("D: initial dent depth", min_value=0.1, value=3.0, step=0.25)
        shape = st.selectbox(
            "Dent shape",
            ["Cosine bowl", "Parabolic bowl", "V groove", "Flat-bottom trench"],
        )
        wall_power = st.slider("Wall shape power", min_value=0.5, max_value=6.0, value=2.0, step=0.1)
        flat_bottom = st.slider(
            "Flat bottom fraction",
            min_value=0.0,
            max_value=0.9,
            value=0.35,
            step=0.05,
            disabled=shape != "Flat-bottom trench",
        )
        asymmetry = st.slider("Asymmetry", min_value=-0.8, max_value=0.8, value=0.0, step=0.05)

        st.header("Deposition sweep")
        max_deposition = st.number_input(
            "Max deposition x",
            min_value=0.01,
            value=float(max(depth * 1.25, width * 0.25)),
            step=0.25,
        )
        selected_deposition = st.slider(
            "Selected deposition x",
            min_value=0.0,
            max_value=float(max_deposition),
            value=float(min(depth * 0.5, max_deposition)),
            step=float(max_deposition / 250.0),
        )
        steps = st.slider("Sweep resolution", min_value=50, max_value=450, value=180, step=10)
        samples = st.slider("Shape resolution", min_value=160, max_value=900, value=360, step=20)

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
    metric_cols[0].metric("Remaining depth y", f"{current_depth:.3f}")
    metric_cols[1].metric("Depth improvement", f"{improvement:.3f}", f"{improvement_pct:.1f}%")
    metric_cols[2].metric("Max tangent angle z", f"{current_angle:.2f} deg")
    metric_cols[3].metric("W / D", f"{params.width / params.depth:.2f}")

    left, right = st.columns([1.2, 1.0])
    with left:
        st.plotly_chart(
            make_sweep_plot(depositions, depths, angles, selected_deposition),
            use_container_width=True,
        )
    with right:
        st.plotly_chart(make_profile_plot(params, selected_deposition), use_container_width=True)

    st.caption(
        "Model: the initial dent boundary is expanded by the conformal deposition distance x. "
        "The remaining depth y is measured from the deposited flat top plane, and z is the maximum "
        "absolute tangent angle of the deposited top boundary inside the dent opening."
    )


if __name__ == "__main__":
    main()
