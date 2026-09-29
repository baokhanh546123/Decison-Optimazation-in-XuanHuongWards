"""Cầu nối giữa trang runner.html và thuật toán Benders (model/benders_solver.py).

Luồng:
    RunnerOptimizeRequest (từ window.getRunConfig())
        -> build_problem():  demand = POI trong XuanHuongWarsFeaturesClean.geojson
                             candidate J = các candidate người dùng đã chọn
                             a_ij, p_i, c_j (cost theo class đường gần nhất)
        -> Optimization(eps_mode="benders").epsilon_constraint_sweep()
        -> format_results(): gắn uid/tên candidate, điểm khuyến nghị theo λ

Không import FastAPI ở đây để có thể test độc lập.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import sparse

from api.runner_schemas import RunnerOptimizeRequest
from core.coverage import build_coverage_matrix_sparse
from core.taxonomy_apply import apply_road_cost
from dataclass.MCLP import MCLP_Data
from dataclass.taxonomy_config import DEFAULT_TAXONOMY_CONFIG, TaxonomyConfig

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parents[1]
DATA_DIR = ROOT_DIR / "data" / "Xuanhuongward"
STATIC_DIR = BACKEND_DIR.parent / "frontend" / "static"

CLEAN_GEOJSON = DATA_DIR / "XuanHuongWarsFeaturesClean.geojson"
FEATURED_GEOJSON = DATA_DIR / "Xuan Huong Wards_featured.geojson"
ROADS_GEOJSON = DATA_DIR / "Xuan Huong Wards_roads.geojson"
# cùng thứ tự ưu tiên với candidates_loader.js
CANDIDATE_JSONS = (STATIC_DIR / "candidates.json", STATIC_DIR / "candidates_xuanhuong.json")

UTM_EPSG = 32648


class RunnerInputError(ValueError):
    """Lỗi do dữ liệu người dùng gửi lên (HTTP 422), không phải lỗi server."""


# --------------------------------------------------------------------------- #
# Loader có cache
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def candidate_lookup() -> Dict[str, dict]:
    """uid -> record, đọc đúng file mà candidates_loader.js đọc (uid trong file, hoặc C-001.. theo thứ tự)."""
    for path in CANDIDATE_JSONS:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            out: Dict[str, dict] = {}
            for i, c in enumerate(data.get("candidates") or [], 1):
                out[str(c.get("uid") or f"C-{i:03d}")] = c
            return out
    return {}


@lru_cache(maxsize=1)
def demand_frame() -> pd.DataFrame:
    """POI demand: lon, lat, taxonomy_root, confidence (chưa áp trọng số/bán kính)."""
    import geopandas as gpd

    path = CLEAN_GEOJSON if CLEAN_GEOJSON.is_file() else FEATURED_GEOJSON
    if not path.is_file():
        raise FileNotFoundError(f"Không thấy dữ liệu demand: {CLEAN_GEOJSON}")
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    pts = gdf.geometry.representative_point()
    df = pd.DataFrame({
        "lon": pts.x.to_numpy(dtype=np.float64),
        "lat": pts.y.to_numpy(dtype=np.float64),
        "taxonomy_root": gdf["taxonomy_root"].fillna(gdf.get("basic_category")).astype(str).to_numpy(),
        "confidence": pd.to_numeric(gdf["confidence"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64),
    })
    return df.reset_index(drop=True)


@lru_cache(maxsize=1)
def roads_utm():
    """Đường (class, avg_width_m) đã chiếu UTM — dùng để suy ra chi phí c_j."""
    import geopandas as gpd

    if not ROADS_GEOJSON.is_file():
        return None
    r = gpd.read_file(ROADS_GEOJSON)
    keep = [c for c in ("class", "avg_width_m") if c in r.columns]
    r = r[keep + ["geometry"]]
    r = r[r.geometry.notna() & ~r.geometry.is_empty]
    return r.to_crs(epsg=UTM_EPSG)


# --------------------------------------------------------------------------- #
# Dựng bài toán
# --------------------------------------------------------------------------- #
def _candidate_cost(cand: pd.DataFrame, cfg: TaxonomyConfig) -> np.ndarray:
    """c_j theo class đường gần nhất (cùng công thức apply_road_cost của repo thuật toán).

    Không có dữ liệu đường -> cost đều = 1 (Pareto sẽ suy biến theo số cơ sở).
    """
    roads = roads_utm()
    if roads is None or len(roads) == 0:
        return np.ones(len(cand), dtype=np.float64)
    import geopandas as gpd

    pts = gpd.GeoDataFrame(
        {"_j": np.arange(len(cand))},
        geometry=gpd.points_from_xy(cand["lon"], cand["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=UTM_EPSG)
    joined = gpd.sjoin_nearest(pts, roads, how="left")
    joined = joined[~joined.index.duplicated(keep="first")].sort_index()
    raw = pd.DataFrame({
        "class": joined["class"].to_numpy() if "class" in joined else None,
        "avg_width_m": joined["avg_width_m"].to_numpy() if "avg_width_m" in joined else np.nan,
    })
    return apply_road_cost(raw, cfg).astype(np.float64)


def build_problem(
    req: RunnerOptimizeRequest,
    lookup: Dict[str, dict] | None = None,
    demand: pd.DataFrame | None = None,
    cfg: TaxonomyConfig = DEFAULT_TAXONOMY_CONFIG,
    cost: np.ndarray | None = None,
) -> Tuple[MCLP_Data, List[dict], dict]:
    """Trả (MCLP_Data, danh sách candidate giữ lại theo đúng thứ tự cột J, meta)."""
    lookup = candidate_lookup() if lookup is None else lookup
    unknown = [u for u in req.candidates if u not in lookup]
    if unknown:
        raise RunnerInputError(f"Candidate không tồn tại: {', '.join(unknown[:5])}")

    # --- tập J: bỏ trùng, lọc theo confidence toàn cục + confidence riêng từng candidate ---
    seen, selected, dropped = set(), [], []
    for uid in req.candidates:
        if uid in seen:
            continue
        seen.add(uid)
        rec = dict(lookup[uid], uid=uid)
        own = req.per_candidate.get(uid)
        thr = max(req.min_confidence, own.conf if own else 0.0)
        if float(rec.get("confidence") or 0.0) + 1e-9 < thr:
            dropped.append(uid)
            continue
        selected.append(rec)
    if not selected:
        raise RunnerInputError(
            f"Không candidate nào đạt confidence tối thiểu (≥ {req.min_confidence:.2f}). Hạ ngưỡng ở Bước 2/3."
        )

    # --- demand: p_i = weight(root) × confidence, bán kính theo root (UI override > config) ---
    demand = demand_frame() if demand is None else demand
    d = demand[demand["confidence"] >= cfg.min_confidence].reset_index(drop=True)
    if d.empty:
        raise RunnerInputError("Không có demand nào sau khi lọc confidence.")
    w_map = dict(cfg.taxonomy_root_weight)
    r_map = dict(cfg.taxonomy_root_radius_m)
    for root, ov in req.taxonomy_root.items():
        w_map[root] = ov.weight
        r_map[root] = ov.radius_m
    root = d["taxonomy_root"]
    p = (root.map(w_map).fillna(cfg.default_root_weight).to_numpy(dtype=np.float64)
         * d["confidence"].to_numpy(dtype=np.float64))
    radius = root.map(r_map).fillna(cfg.default_radius_m).to_numpy(dtype=np.float64)
    d = d.assign(coverage_radius_m=radius)

    cand = pd.DataFrame({
        "lon": [float(c["lng"]) for c in selected],
        "lat": [float(c["lat"]) for c in selected],
    })

    a = build_coverage_matrix_sparse(d, cand, utm_epsg=UTM_EPSG)

    # --- ngưỡng demand-weight riêng từng candidate: j chỉ phủ demand có p_i ≥ thr_j × max(p) ---
    thr = np.array([(req.per_candidate.get(c["uid"]).demand if req.per_candidate.get(c["uid"]) else 0.0)
                    for c in selected], dtype=np.float64)
    if np.any(thr > 0) and p.size:
        ok = p[:, None] >= (thr[None, :] * float(p.max()) - 1e-12)
        a = sparse.csr_matrix(a.multiply(sparse.csr_matrix(ok.astype(np.int8))), dtype=np.int8)
        a.eliminate_zeros()

    c = _candidate_cost(cand, cfg) if cost is None else np.asarray(cost, dtype=np.float64)
    if c.shape[0] != len(selected):
        raise RunnerInputError("Độ dài cost không khớp số candidate.")

    p_max = None if req.P_max is None else min(int(req.P_max), len(selected))
    mclp = MCLP_Data(p=p, a=a, c=c, P_max=p_max)
    meta = {
        "n_demand": int(mclp.n_i),
        "n_candidates": int(mclp.n_j),
        "n_candidates_requested": len(req.candidates),
        "dropped_by_confidence": dropped,
        "total_profit": float(p.sum()),
        "coverable_profit": float(p[np.asarray(a.sum(axis=1)).ravel() > 0].sum()),
        "P_max": p_max,
    }
    return mclp, selected, meta


# --------------------------------------------------------------------------- #
# Chạy Benders
# --------------------------------------------------------------------------- #
def _parallelism() -> Tuple[int, int]:
    cpu = max(1, os.cpu_count() or 1)
    n_parallel = min(4, cpu)
    return n_parallel, max(1, cpu // n_parallel)


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def format_results(results: List[dict], selected: List[dict], meta: dict, lam: List[int]) -> dict:
    """Chuẩn hoá kết quả sweep -> JSON an toàn + điểm khuyến nghị theo (λ1, λ2)."""
    total = meta.get("total_profit") or 0.0
    points: List[dict] = []
    for r in results:
        chosen = [int(j) for j in r.get("chosen_candidates", [])]
        f1 = _finite(r.get("f1_covering_profit")) or 0.0
        points.append({
            "epsilon": _finite(r.get("epsilon")),
            "f1_covering_profit": f1,
            "f2_cost": _finite(r.get("f2_cost")) or 0.0,
            "coverage_pct": (100.0 * f1 / total) if total > 0 else None,
            "n_facilities": int(r.get("n_facilities", len(chosen))),
            "chosen_candidates": chosen,
            "chosen_uids": [selected[j]["uid"] for j in chosen if 0 <= j < len(selected)],
            "chosen_names": [selected[j].get("name", "") for j in chosen if 0 <= j < len(selected)],
            "status": str(r.get("status", "")),
            "optimality_gap_pct": _finite(r.get("optimality_gap_pct")),
            "solve_time_s": _finite(r.get("solve_time_s")),
            "n_benders_iters": r.get("n_benders_iters"),
            "flagged_non_monotonic": bool(r.get("flagged_non_monotonic", False)),
            "is_recommended": False,
        })

    # ε khác nhau có thể cho cùng (f1, f2) -> giữ điểm ε nhỏ nhất để front không bị chấm trùng
    n_raw = len(points)
    uniq: Dict[Tuple[float, float], dict] = {}
    for q in sorted(points, key=lambda q: q["epsilon"] if q["epsilon"] is not None else 0.0):
        uniq.setdefault((round(q["f1_covering_profit"], 6), round(q["f2_cost"], 6)), q)
    points = list(uniq.values())

    rec_idx = None
    if points:
        pool = [i for i, q in enumerate(points) if not q["flagged_non_monotonic"]] or list(range(len(points)))
        f1max = max(points[i]["f1_covering_profit"] for i in pool) or 1.0
        f2max = max(points[i]["f2_cost"] for i in pool) or 1.0
        l1, l2 = lam[0] / float(sum(lam)), lam[1] / float(sum(lam))
        rec_idx = max(pool, key=lambda i: l1 * points[i]["f1_covering_profit"] / f1max
                      - l2 * points[i]["f2_cost"] / f2max)
        points[rec_idx]["is_recommended"] = True

    gaps = [q["optimality_gap_pct"] for q in points if q["optimality_gap_pct"] is not None]
    return {
        "algorithm": "benders",
        "points": points,
        "recommended_index": rec_idx,
        "summary": {
            "n_points": len(points),
            "n_raw_points": n_raw,
            "mean_gap_pct": (sum(gaps) / len(gaps)) if gaps else None,
            "n_flagged": sum(1 for q in points if q["flagged_non_monotonic"]),
            "n_converged": sum(1 for q in points if q["status"] == "BENDERS_CONVERGED"),
        },
        "meta": meta,
    }


def run_benders(req: RunnerOptimizeRequest, **build_kwargs) -> dict:
    """Hàm blocking — chạy trong thread (JobManager dùng asyncio.to_thread)."""
    from model.optimization import Optimization

    mclp, selected, meta = build_problem(req, **build_kwargs)
    cand_df = pd.DataFrame({"lon": [c["lng"] for c in selected], "lat": [c["lat"] for c in selected]})
    n_parallel, workers = _parallelism()
    opt = Optimization(
        data=mclp,
        candidate_set=cand_df,
        n_points=req.n_points,
        time_limit_s=req.time_limit_s,
        relative_gap=req.relative_gap,
        n_parallel=n_parallel,
        workers_per_solve=workers,
        use_hint=True,
        early_stop=True,
        re_solve_flagged=True,
        re_solve_time_limit=req.time_limit_s * 2,
        utm_epsg=UTM_EPSG,
        eps_mode="benders",
        benders_max_iters=req.benders_max_iters,
        benders_master_time_limit_s=req.benders_master_time_limit_s,
    )
    results = opt.epsilon_constraint_sweep()
    out = format_results(results, selected, meta, req.lambda_)
    out["meta"].update({"n_parallel": n_parallel, "workers_per_solve": workers,
                        "benders_max_iters": req.benders_max_iters})
    return out
