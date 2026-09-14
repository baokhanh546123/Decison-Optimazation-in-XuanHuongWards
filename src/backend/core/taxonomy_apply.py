from __future__ import annotations
from dataclass.taxonomy_config import TaxonomyConfig
import numpy as np
import pandas as pd

def apply_demand_weights(demand_raw: pd.DataFrame, config: TaxonomyConfig) -> tuple[np.ndarray, np.ndarray]:
    """demand_raw cần cột 'taxonomy_root', 'confidence'.
    Trả về (p_i float32, coverage_radius_m float64) — đúng công thức load_places() gốc:
        p_i = weight(taxonomy_root) * confidence
        coverage_radius_m = radius(taxonomy_root)
    """
    root = demand_raw["taxonomy_root"]
    weight = root.map(config.taxonomy_root_weight).fillna(config.default_root_weight)
    p_i = (weight.to_numpy(dtype=np.float64) * demand_raw["confidence"].to_numpy(dtype=np.float64)).astype(np.float32)
    radius = root.map(config.taxonomy_root_radius_m).fillna(config.default_radius_m)
    coverage_radius_m = radius.to_numpy(dtype=np.float64)
    return p_i, coverage_radius_m


def road_eligibility_mask(candidate_raw: pd.DataFrame, config: TaxonomyConfig) -> np.ndarray:
    """Đúng điều kiện is_candidate_eligible trong clean_roads() gốc, áp lại
    trên candidate_raw['class'] đã cache — dùng khi CANDIDATE_EXCLUDED_CLASS
    đổi mà không muốn chạy lại clean_roads()/generate_street_candidates()."""
    if "class" not in candidate_raw.columns:
        return np.ones(len(candidate_raw), dtype=bool)
    return ~candidate_raw["class"].isin(config.candidate_excluded_class).to_numpy()


def apply_road_cost(candidate_raw: pd.DataFrame, config: TaxonomyConfig) -> np.ndarray:
    """candidate_raw cần cột 'class' (thiếu -> cost đều = 1) và tuỳ chọn
    'avg_width_m'. Giữ đúng công thức derive_candidate_cost() gốc:
        cost = rank(class) + width_norm ; chuẩn hoá theo max.
    """
    if "class" not in candidate_raw.columns:
        return np.ones(len(candidate_raw), dtype=np.float32)

    rank = candidate_raw["class"].map(config.class_cost_rank).fillna(1.0).to_numpy(dtype=float)

    width = pd.to_numeric(candidate_raw.get("avg_width_m"), errors="coerce").to_numpy(dtype=float)
    fallback = np.nanmedian(width) if not np.all(np.isnan(width)) else 0.0
    width = np.where(np.isnan(width), fallback, width)
    span = width.max() - width.min()
    width_norm = (width - width.min()) / span if span > 1e-9 else np.zeros_like(width)

    cost = rank + width_norm
    max_cost = cost.max()
    if max_cost <= 1e-12:
        return np.ones(len(candidate_raw), dtype=np.float32)
    return (cost / max_cost).astype(np.float32)