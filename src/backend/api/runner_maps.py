"""Biểu đồ cho trang runner — dựng bằng package `visualize` (visualize/visualize_plot.py).

Mỗi lần chạy Benders xong, `runner_service.run_benders` gọi `register_run(...)` để lưu lại:
    - candidate_gdf : các candidate trong tập J (candidate_id = chỉ số cột J, khớp chosen_candidates)
    - demand_gdf    : POI demand kèm p_i
    - points        : các điểm Pareto (đã khử trùng)
Sau đó front-end xin ảnh/bản đồ qua:
    GET /api/runs/{run_id}/map.html?mode=heatmap|dot[&point=k]   (pydeck, tương tác)
    GET /api/runs/{run_id}/map.jpg[?point=k]                      (matplotlib, ảnh tĩnh)

`point` bỏ trống = vẽ toàn bộ Pareto; `point=k` = chỉ vẽ điểm thứ k (0-based) trong danh sách points.
Ngữ cảnh giữ tối đa MAX_RUNS lần chạy gần nhất (RAM + thư mục tạm), cũ hơn bị xoá.
"""
from __future__ import annotations

import copy
import shutil
import tempfile
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

MAX_RUNS = 6
ROOT_TMP = Path(tempfile.gettempdir()) / "mclp_runner_maps"

_lock = threading.RLock()          # bảo vệ _runs / _files
_plot_lock = threading.Lock()      # matplotlib.pyplot không thread-safe
_runs: "OrderedDict[str, RunContext]" = OrderedDict()
_files: Dict[Tuple[str, str, str, int], Path] = {}


class MapUnavailable(RuntimeError):
    """Thiếu thư viện vẽ (pydeck / matplotlib) trên server."""


class MapInputError(ValueError):
    """Tham số mode/point sai (HTTP 422)."""


@dataclass
class RunContext:
    candidate_gdf: object
    demand_gdf: object
    points: List[dict]


def _candidate_gdf(selected: List[dict]):
    import geopandas as gpd

    df = pd.DataFrame({
        "candidate_id": np.arange(len(selected), dtype=int),
        "lon": [float(c["lng"]) for c in selected],
        "lat": [float(c["lat"]) for c in selected],
        "uid": [c["uid"] for c in selected],
        "name": [c.get("name", "") for c in selected],
    })
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")


def register_run(selected: List[dict], demand_df: pd.DataFrame, points: List[dict]) -> str:
    """Lưu ngữ cảnh vẽ; trả run_id."""
    import geopandas as gpd

    dem = demand_df[["lon", "lat", "p_i"]].reset_index(drop=True)
    demand_gdf = gpd.GeoDataFrame(dem, geometry=gpd.points_from_xy(dem["lon"], dem["lat"]), crs="EPSG:4326")
    run_id = uuid.uuid4().hex[:12]
    ctx = RunContext(_candidate_gdf(selected), demand_gdf, copy.deepcopy(points))
    with _lock:
        _runs[run_id] = ctx
        while len(_runs) > MAX_RUNS:
            old, _ = _runs.popitem(last=False)
            _drop_files(old)
    return run_id


def _drop_files(run_id: str) -> None:
    for k in [k for k in _files if k[0] == run_id]:
        _files.pop(k, None)
    shutil.rmtree(ROOT_TMP / run_id, ignore_errors=True)


def has_run(run_id: str) -> bool:
    with _lock:
        return run_id in _runs


def _results_for(ctx: RunContext, point: Optional[int]) -> List[dict]:
    if point is None:
        return ctx.points
    if point < 0 or point >= len(ctx.points):
        raise MapInputError(f"point phải trong [0, {len(ctx.points) - 1}]")
    return [ctx.points[point]]


def render(run_id: str, kind: str, mode: str = "heatmap", point: Optional[int] = None) -> Path:
    """Dựng file bản đồ (có cache). kind: 'html' | 'jpeg'. Ném KeyError nếu run_id không tồn tại."""
    if kind not in ("html", "jpeg"):
        raise MapInputError("kind phải là html hoặc jpeg")
    if kind == "html" and mode not in ("heatmap", "dot"):
        raise MapInputError("mode phải là heatmap hoặc dot")
    if kind == "jpeg":
        mode = "-"

    with _lock:
        ctx = _runs.get(run_id)
        if ctx is None:
            raise KeyError(run_id)
        _runs.move_to_end(run_id)
        key = (run_id, kind, mode, -1 if point is None else int(point))
        cached = _files.get(key)
        if cached is not None and cached.is_file():
            return cached

    results = _results_for(ctx, point)
    if not results:
        raise MapInputError("Lần chạy này không có điểm Pareto nào để vẽ.")

    out_dir = ROOT_TMP / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{kind}_{mode}_{'all' if point is None else point}"

    try:
        from visualize import plot_pareto_map_pydeck, plot_pareto_static_jpeg
        from visualize.visualize_plot import export_deck_html
    except ImportError as exc:  # pragma: no cover
        raise MapUnavailable(str(exc)) from exc

    try:
        if kind == "html":
            deck = plot_pareto_map_pydeck(
                candidate_gdf=ctx.candidate_gdf, sweep_results=results, demand_gdf=ctx.demand_gdf,
                mode=mode, only_trusted=False, zoom=13.5,
            )
            path = export_deck_html(deck, out_dir / f"{stem}.html")
        else:
            with _plot_lock:
                path = plot_pareto_static_jpeg(
                    candidate_gdf=ctx.candidate_gdf, sweep_results=results, demand_gdf=ctx.demand_gdf,
                    path=out_dir / f"{stem}.jpg", only_trusted=False, dpi=110, figsize=(9, 9),
                )
    except ImportError as exc:
        raise MapUnavailable(str(exc)) from exc

    with _lock:
        if run_id in _runs:
            _files[key] = Path(path)
    return Path(path)
