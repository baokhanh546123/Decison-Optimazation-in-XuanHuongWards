"""
visualize_plot.py — Trực quan hóa Pareto front MO-MCLP (bám notebook).

Khác notebook: không chỉ hiển thị trong cell mà **export** ra:
  - HTML  (pydeck interactive — deck.to_html)
  - JPEG  (matplotlib static map — không cần browser)

API chính
---------
  deck = plot_pareto_map_pydeck(candidate_gdf, sweep_results, demand_gdf, mode="dot")
  paths = export_pareto_map(
      candidate_gdf, sweep_results, demand_gdf,
      out_dir="outputs/maps", stem="pareto",
      formats=("html", "jpeg"), mode="heatmap",
  )
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover
    gpd = None  # type: ignore

try:
    import pydeck as pdk
except ImportError:  # pragma: no cover
    pdk = None  # type: ignore


# ---------------------------------------------------------------------------
# Màu & icon (giống notebook)
# ---------------------------------------------------------------------------
_PARETO_PALETTE = [
    [33, 102, 172, 230],
    [67, 147, 195, 230],
    [146, 197, 222, 230],
    [209, 229, 240, 220],
    [253, 219, 199, 220],
    [244, 165, 130, 230],
    [214, 96, 77, 230],
    [178, 24, 43, 230],
]

_CANDIDATE_COLOR = [100, 140, 180, 90]
_DEMAND_DOT_COLOR = [49, 130, 189, 130]
_CLUSTER_COLOR = [46, 125, 50, 160]
_SELECTED_PIN_COLOR = [220, 50, 50]
_BEST_PIN_COLOR = [255, 140, 0]

_ICON_ATLAS = (
    "https://raw.githubusercontent.com/visgl/deck.gl-data/"
    "master/website/icon-atlas.png"
)
_ICON_MAPPING = {
    "marker": {"x": 0, "y": 0, "width": 128, "height": 128, "mask": True},
    "marker-warning": {"x": 128, "y": 0, "width": 128, "height": 128, "mask": True},
}


def _require_pydeck():
    if pdk is None:
        raise ImportError("pydeck chưa được cài — pip install pydeck")


def _require_geopandas():
    if gpd is None:
        raise ImportError("geopandas chưa được cài — pip install geopandas")


def _ensure_lon_lat(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Đảm bảo có cột lon/lat (từ geometry nếu thiếu)."""
    out = gdf.copy()
    if "lon" not in out.columns or "lat" not in out.columns:
        if out.crs is None:
            # giả định WGS84 nếu chưa set
            geom = out.geometry
        else:
            geom = out.to_crs(epsg=4326).geometry
        out["lon"] = geom.x.values
        out["lat"] = geom.y.values
    if "candidate_id" not in out.columns:
        out["candidate_id"] = np.arange(len(out), dtype=int)
    return out


def _norm_score(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=float)
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return [0.5] * len(arr)
    return ((arr - lo) / (hi - lo)).tolist()


def _score_color(t: float, palette: list[list[int]] = _PARETO_PALETTE) -> list[int]:
    t = float(np.clip(t, 0.0, 1.0))
    n = len(palette) - 1
    i = min(int(t * n), n - 1)
    frac = t * n - i
    c0, c1 = palette[i], palette[i + 1]
    return [int(c0[k] + frac * (c1[k] - c0[k])) for k in range(4)]


def _pick_tradeoff_key(row: dict, lambda_key: str, epsilon_key: str) -> float:
    if lambda_key in row and row[lambda_key] is not None:
        return float(row[lambda_key])
    if epsilon_key in row and row[epsilon_key] is not None:
        return float(row[epsilon_key])
    return 0.0


def _make_tooltip_html(
    candidate_id,
    label: str,
    trade_label: str,
    f1: float,
    f2: float,
    n_facilities: int,
    status: str,
    gap: float,
) -> str:
    gap_str = f"{gap:.1f}" if gap == gap else "n/a"
    return (
        f"{label}"
        f"candidate_id={candidate_id}<br>"
        f"{trade_label}<br>"
        f"f1 (covering)={f1:.2f}<br>"
        f"f2 (cost)={f2:.2f}<br>"
        f"n_facilities={n_facilities}<br>"
        f"status={status}<br>"
        f"gap={gap_str}%"
    )


def plot_pareto_map_pydeck(
    candidate_gdf: "gpd.GeoDataFrame",
    sweep_results: list[dict],
    demand_gdf: Optional["gpd.GeoDataFrame"] = None,
    mode: Literal["heatmap", "dot"] = "heatmap",
    lambda_key: str = "lambda",
    epsilon_key: str = "epsilon",
    f1_key: str = "f1_covering_profit",
    f2_key: str = "f2_cost",
    only_trusted: bool = True,
    show_all_candidates: bool = True,
    center: Optional[Tuple[float, float]] = None,
    zoom: float = 13.5,
    map_style: str = "light",
    demand_radius_px: int = 35,
    candidate_radius: int = 20,
    facility_radius: int = 55,
    best_radius: int = 90,
    pin_size: int = 48,
    best_pin_size: int = 64,
):
    """Trực quan hóa Pareto / ε-constraint front (giống Optimization_fixed.ipynb).

    mode
    ----
    heatmap : HeatmapLayer demand + scatter facility
    dot     : điểm cụm (xanh) + GPS pin (đỏ/cam) cho candidate được chọn

    Returns
    -------
    pydeck.Deck
    """
    _require_pydeck()
    _require_geopandas()

    candidate_gdf = _ensure_lon_lat(candidate_gdf)
    if demand_gdf is not None:
        demand_gdf = _ensure_lon_lat(demand_gdf)

    if center is None:
        center = (
            float(candidate_gdf["lat"].mean()),
            float(candidate_gdf["lon"].mean()),
        )

    filtered = [
        r for r in sweep_results
        if (not only_trusted) or (not r.get("flagged_non_monotonic", False))
    ]
    if not filtered:
        raise ValueError(
            "Không còn điểm nào sau khi lọc only_trusted=True — "
            "hãy tăng time_limit và chạy lại sweep."
        )

    raw_scores = [_pick_tradeoff_key(r, lambda_key, epsilon_key) for r in filtered]
    norm_scores = _norm_score(raw_scores)
    best = max(filtered, key=lambda r: r[f1_key])

    all_chosen_ids: set = set()
    for r in filtered:
        all_chosen_ids.update(r.get("chosen_candidates") or [])

    layers: list = []

    # --- candidate nền ---
    if show_all_candidates:
        cand_df = candidate_gdf[["lon", "lat", "candidate_id"]].copy()

        def _cand_color(cid):
            if cid in all_chosen_ids:
                return _CLUSTER_COLOR
            return _CANDIDATE_COLOR

        cand_df["fill_color"] = cand_df["candidate_id"].map(_cand_color)
        cand_df["radius"] = cand_df["candidate_id"].map(
            lambda cid: candidate_radius + 8 if cid in all_chosen_ids else candidate_radius
        )
        cand_df["tooltip_html"] = cand_df["candidate_id"].map(
            lambda cid: (
                f"candidate_id={cid}<br>"
                f"{'● đã xuất hiện trong nghiệm Pareto' if cid in all_chosen_ids else '○ candidate nền'}"
            )
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=cand_df,
                get_position="[lon, lat]",
                get_radius="radius",
                get_fill_color="fill_color",
                pickable=True,
                opacity=0.65,
                id="candidates_cluster",
            )
        )

    # --- demand ---
    if demand_gdf is not None and len(demand_gdf) > 0:
        weight_col = "p_i" if "p_i" in demand_gdf.columns else None
        dem = demand_gdf[["lon", "lat"] + ([weight_col] if weight_col else [])].copy()

        if mode == "heatmap" and weight_col:
            layers.append(
                pdk.Layer(
                    "HeatmapLayer",
                    data=dem,
                    get_position="[lon, lat]",
                    get_weight=weight_col,
                    radius_pixels=demand_radius_px,
                    intensity=1.0,
                    threshold=0.04,
                    opacity=0.55,
                    color_range=[
                        [1, 152, 189],
                        [73, 227, 206],
                        [216, 254, 181],
                        [254, 237, 177],
                        [254, 173, 84],
                        [209, 55, 78],
                    ],
                    id="demand_heatmap",
                )
            )
        else:
            if weight_col:
                w = dem[weight_col].astype(float)
                w_norm = (w - w.min()) / max(w.max() - w.min(), 1e-9)
                dem["radius"] = (12 + 28 * w_norm).astype(int)
                dem["fill_color"] = [
                    [int(49 + 60 * t), int(130 - 30 * t), int(189 - 80 * t), int(90 + 80 * t)]
                    for t in w_norm
                ]
                dem["tooltip_html"] = [f"demand<br>p_i={v:.2f}" for v in dem[weight_col]]
            else:
                dem["radius"] = 14
                dem["fill_color"] = [_DEMAND_DOT_COLOR] * len(dem)
                dem["tooltip_html"] = ["demand point"] * len(dem)

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=dem,
                    get_position="[lon, lat]",
                    get_radius="radius",
                    get_fill_color="fill_color",
                    pickable=True,
                    opacity=0.65,
                    id="demand_dots",
                )
            )

    # --- facilities được chọn ---
    for r, t in zip(filtered, norm_scores):
        score_raw = _pick_tradeoff_key(r, lambda_key, epsilon_key)
        color = _score_color(t)
        chosen_ids = set(r.get("chosen_candidates") or [])
        if not chosen_ids:
            continue

        chosen = candidate_gdf[candidate_gdf["candidate_id"].isin(chosen_ids)].copy()
        if chosen.empty:
            continue

        is_best = r is best
        n = len(chosen)
        label = "★ NGHIỆM TỐT NHẤT (max f1) ★<br>" if is_best else ""
        trade_label = (
            f"λ={score_raw:.3f}" if lambda_key in r else f"ε={score_raw:.2f}"
        )
        gap = r.get("optimality_gap_pct", float("nan"))
        status = r.get("status", "n/a")
        f1 = float(r[f1_key])
        f2 = float(r[f2_key])
        n_fac = int(r.get("n_facilities", n))

        chosen["tooltip_html"] = chosen["candidate_id"].map(
            lambda cid: _make_tooltip_html(
                candidate_id=cid,
                label=label,
                trade_label=trade_label,
                f1=f1,
                f2=f2,
                n_facilities=n_fac,
                status=status,
                gap=gap,
            )
        )

        if mode == "dot":
            chosen["icon"] = "marker"
            chosen["icon_size"] = best_pin_size if is_best else pin_size
            pin_rgb = _BEST_PIN_COLOR if is_best else _SELECTED_PIN_COLOR
            chosen["pin_color"] = [pin_rgb] * n
            layers.append(
                pdk.Layer(
                    "IconLayer",
                    data=chosen,
                    get_position="[lon, lat]",
                    get_icon="icon",
                    get_size="icon_size",
                    get_color="pin_color",
                    icon_atlas=_ICON_ATLAS,
                    icon_mapping=_ICON_MAPPING,
                    size_scale=1,
                    size_units="pixels",
                    pickable=True,
                    id=f"pin_{score_raw:.4f}",
                )
            )
        else:
            chosen["radius"] = best_radius if is_best else facility_radius
            chosen["fill_color"] = [color] * n
            chosen["line_color"] = ([[0, 0, 0, 255]] * n if is_best else [color] * n)
            chosen["line_width"] = 4 if is_best else 1.5
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=chosen,
                    get_position="[lon, lat]",
                    get_radius="radius",
                    get_fill_color="fill_color",
                    get_line_color="line_color",
                    get_line_width="line_width",
                    stroked=True,
                    filled=True,
                    pickable=True,
                    opacity=0.95,
                    id=f"sol_{score_raw:.4f}",
                )
            )

    tooltip = {
        "html": "{tooltip_html}",
        "style": {
            "backgroundColor": "rgba(30, 30, 30, 0.90)",
            "color": "white",
            "fontSize": "12px",
            "borderRadius": "6px",
            "padding": "8px 10px",
        },
    }

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=center[0],
            longitude=center[1],
            zoom=zoom,
            pitch=0,
            bearing=0,
        ),
        map_style=map_style,
        tooltip=tooltip,
    )


# ---------------------------------------------------------------------------
# Export HTML / JPEG
# ---------------------------------------------------------------------------
def export_deck_html(deck, path: Union[str, Path], notebook_display: bool = False) -> Path:
    """Ghi pydeck.Deck ra file HTML tương tác."""
    _require_pydeck()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deck.to_html(str(path), notebook_display=notebook_display)
    print(f"[OK] HTML → {path.resolve()}")
    return path


def plot_pareto_static_jpeg(
    candidate_gdf: "gpd.GeoDataFrame",
    sweep_results: list[dict],
    demand_gdf: Optional["gpd.GeoDataFrame"] = None,
    path: Union[str, Path] = "pareto_map.jpg",
    only_trusted: bool = True,
    f1_key: str = "f1_covering_profit",
    dpi: int = 150,
    figsize: Tuple[float, float] = (10, 10),
) -> Path:
    """Vẽ bản đồ tĩnh (matplotlib) và lưu JPEG — không cần browser.

    Lớp:
      - demand (xanh nhạt, alpha theo p_i nếu có)
      - candidate nền (xám)
      - facility từng nghiệm Pareto (palette)
      - nghiệm best f1 (cam, marker lớn hơn)
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    _require_geopandas()
    candidate_gdf = _ensure_lon_lat(candidate_gdf)
    if demand_gdf is not None:
        demand_gdf = _ensure_lon_lat(demand_gdf)

    filtered = [
        r for r in sweep_results
        if (not only_trusted) or (not r.get("flagged_non_monotonic", False))
    ]
    if not filtered:
        raise ValueError("Không còn điểm Pareto sau only_trusted filter.")

    best = max(filtered, key=lambda r: r[f1_key])
    all_chosen: set = set()
    for r in filtered:
        all_chosen.update(r.get("chosen_candidates") or [])

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    # demand
    if demand_gdf is not None and len(demand_gdf) > 0:
        if "p_i" in demand_gdf.columns:
            w = demand_gdf["p_i"].astype(float).to_numpy()
            w_n = (w - w.min()) / max(w.max() - w.min(), 1e-9)
            ax.scatter(
                demand_gdf["lon"], demand_gdf["lat"],
                c=w_n, cmap="Blues", s=8 + 40 * w_n,
                alpha=0.35, linewidths=0, zorder=1, label="demand",
            )
        else:
            ax.scatter(
                demand_gdf["lon"], demand_gdf["lat"],
                c="#3182bd", s=10, alpha=0.25, linewidths=0, zorder=1, label="demand",
            )

    # candidates
    ax.scatter(
        candidate_gdf["lon"], candidate_gdf["lat"],
        c="#9e9e9e", s=6, alpha=0.35, linewidths=0, zorder=2, label="candidate",
    )
    if all_chosen:
        sub = candidate_gdf[candidate_gdf["candidate_id"].isin(all_chosen)]
        ax.scatter(
            sub["lon"], sub["lat"],
            c="#2e7d32", s=28, alpha=0.7, linewidths=0.3, edgecolors="white",
            zorder=3, label="in Pareto set",
        )

    # each solution
    raw_scores = [_pick_tradeoff_key(r, "lambda", "epsilon") for r in filtered]
    norms = _norm_score(raw_scores)
    for r, t in zip(filtered, norms):
        ids = set(r.get("chosen_candidates") or [])
        if not ids:
            continue
        sub = candidate_gdf[candidate_gdf["candidate_id"].isin(ids)]
        if sub.empty:
            continue
        rgba = np.array(_score_color(t)[:3]) / 255.0
        is_best = r is best
        ax.scatter(
            sub["lon"], sub["lat"],
            c=[rgba],
            s=120 if is_best else 55,
            marker="*" if is_best else "o",
            edgecolors="black" if is_best else "white",
            linewidths=1.2 if is_best else 0.6,
            zorder=5 if is_best else 4,
            label=("best f1" if is_best else None),
        )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("MO-MCLP Pareto facilities")
    ax.set_aspect("equal", adjustable="datalim")
    handles, labels = ax.get_legend_handles_labels()
    # unique labels
    seen = set()
    uh, ul = [], []
    for h, lab in zip(handles, labels):
        if lab and lab not in seen:
            seen.add(lab)
            uh.append(h)
            ul.append(lab)
    ax.legend(uh, ul, loc="best", fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.25)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, format="jpeg", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] JPEG → {path.resolve()}")
    return path


def export_pareto_map(
    candidate_gdf: "gpd.GeoDataFrame",
    sweep_results: list[dict],
    demand_gdf: Optional["gpd.GeoDataFrame"] = None,
    out_dir: Union[str, Path] = "outputs/maps",
    stem: str = "pareto",
    formats: Sequence[str] = ("html", "jpeg"),
    mode: Literal["heatmap", "dot"] = "heatmap",
    only_trusted: bool = True,
    **plot_kwargs,
) -> dict:
    """Export bản đồ Pareto ra HTML và/hoặc JPEG.

    Parameters
    ----------
    formats : sequence of {"html", "jpeg"}
    mode : "heatmap" | "dot" — chỉ ảnh hưởng bản HTML (pydeck)
    **plot_kwargs : truyền tiếp vào plot_pareto_map_pydeck

    Returns
    -------
    dict[str, Path]  ví dụ {"html": Path(...), "jpeg": Path(...)}
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    formats_l = [f.lower().lstrip(".") for f in formats]
    result: dict = {}

    if "html" in formats_l:
        deck = plot_pareto_map_pydeck(
            candidate_gdf=candidate_gdf,
            sweep_results=sweep_results,
            demand_gdf=demand_gdf,
            mode=mode,
            only_trusted=only_trusted,
            **plot_kwargs,
        )
        html_path = out_dir / f"{stem}_{mode}.html"
        result["html"] = export_deck_html(deck, html_path)

    if "jpeg" in formats_l or "jpg" in formats_l:
        jpeg_path = out_dir / f"{stem}.jpg"
        result["jpeg"] = plot_pareto_static_jpeg(
            candidate_gdf=candidate_gdf,
            sweep_results=sweep_results,
            demand_gdf=demand_gdf,
            path=jpeg_path,
            only_trusted=only_trusted,
        )

    return result
