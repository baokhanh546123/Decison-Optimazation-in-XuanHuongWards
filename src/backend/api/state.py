from __future__ import annotations

import asyncio
import dataclasses
import time
from typing import Optional

import numpy as np
import pandas as pd

from dataclass.MCLP import MCLP_Data
from dataclass.taxonomy_config import TaxonomyConfig, DEFAULT_TAXONOMY_CONFIG
from core.coverage import build_coverage_matrix_sparse
from core.taxonomy_apply import apply_demand_weights, apply_road_cost, road_eligibility_mask


class PipelineState:
    def __init__(self, demand_raw: pd.DataFrame, candidate_raw: pd.DataFrame,
                 utm_epsg: int = 32648, max_radius_m: Optional[float] = None):
        # --- Tầng RAW (đắt, load 1 lần) ---
        self.demand_raw = demand_raw
        self.candidate_raw_full = candidate_raw   # toàn bộ candidate, trước khi lọc eligibility
        self.utm_epsg = utm_epsg
        self.max_radius_m = max_radius_m

        # --- Config hiện hành ---
        self.config: TaxonomyConfig = DEFAULT_TAXONOMY_CONFIG
        self.config_version: int = 0

        # --- Cờ dirty theo tầng ---
        self.weight_dirty = True
        self.radius_dirty = True
        self.road_cost_dirty = True
        self.road_eligibility_dirty = True

        # --- Cache DERIVED ---
        self._candidate_idx: Optional[np.ndarray] = None   # index (trên candidate_raw_full) đang eligible
        self._p: Optional[np.ndarray] = None
        self._coverage_radius_m: Optional[np.ndarray] = None
        self._c: Optional[np.ndarray] = None
        self._a = None
        self.mclp_data: Optional[MCLP_Data] = None

        self.lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Cập nhật config — chỉ bật đúng cờ dirty cần thiết, KHÔNG recompute ngay
    # (recompute lười — chỉ chạy khi thực sự cần, lúc gọi /optimize)
    # ------------------------------------------------------------------ #
    def update_taxonomy(self, root: str, weight: Optional[float], radius_m: Optional[float]) -> None:
        new_weight_map = dict(self.config.taxonomy_root_weight)
        new_radius_map = dict(self.config.taxonomy_root_radius_m)
        if weight is not None:
            new_weight_map[root] = weight
            self.weight_dirty = True
        if radius_m is not None:
            new_radius_map[root] = radius_m
            self.radius_dirty = True
        self.config = dataclasses.replace(
            self.config,
            taxonomy_root_weight=new_weight_map,
            taxonomy_root_radius_m=new_radius_map,
        )
        self.config_version += 1

    def update_road_class(self, class_name: str, cost_rank: Optional[float],
                           excluded: Optional[bool], low_priority: Optional[bool]) -> None:
        new_cost_rank = dict(self.config.class_cost_rank)
        new_excluded = set(self.config.candidate_excluded_class)
        new_low_priority = set(self.config.candidate_low_priority_class)

        if cost_rank is not None:
            new_cost_rank[class_name] = cost_rank
            self.road_cost_dirty = True
        if excluded is not None:
            (new_excluded.add if excluded else new_excluded.discard)(class_name)
            self.road_eligibility_dirty = True
        if low_priority is not None:
            (new_low_priority.add if low_priority else new_low_priority.discard)(class_name)
            # low_priority không đổi tập eligible (chỉ đổi walkable_tier — không dùng trong
            # optimize path hiện tại) nên KHÔNG bật road_eligibility_dirty ở đây.

        self.config = dataclasses.replace(
            self.config,
            class_cost_rank=new_cost_rank,
            candidate_excluded_class=frozenset(new_excluded),
            candidate_low_priority_class=frozenset(new_low_priority),
        )
        self.config_version += 1

    # ------------------------------------------------------------------ #
    # Recompute tối thiểu — gọi bên trong self.lock (xem api/jobs.py)
    # ------------------------------------------------------------------ #
    def ensure_ready(self, P_max: Optional[int], budget: Optional[float],
                      must_cover: Optional[np.ndarray] = None) -> MCLP_Data:
        rebuilt_matrix = False

        if self.road_eligibility_dirty or self._candidate_idx is None:
            mask = road_eligibility_mask(self.candidate_raw_full, self.config)
            self._candidate_idx = np.nonzero(mask)[0]
            self.road_eligibility_dirty = False
            self.radius_dirty = True       # subset đổi -> matrix phải rebuild
            self.road_cost_dirty = True    # subset đổi -> cost phải rebuild

        candidate_raw = self.candidate_raw_full.iloc[self._candidate_idx].reset_index(drop=True)

        if self.weight_dirty or self._p is None or self.radius_dirty or self._coverage_radius_m is None:
            p, coverage_radius_m = apply_demand_weights(self.demand_raw, self.config)
            self._p = p
            self._coverage_radius_m = coverage_radius_m
            self.weight_dirty = False

        demand_for_matrix = self.demand_raw.assign(coverage_radius_m=self._coverage_radius_m)

        if self.radius_dirty or self._a is None:
            self._a = build_coverage_matrix_sparse(
                demand_for_matrix, candidate_raw,
                utm_epsg=self.utm_epsg, max_radius_m=self.max_radius_m,
            )
            self.radius_dirty = False
            rebuilt_matrix = True

        if self.road_cost_dirty or self._c is None:
            self._c = apply_road_cost(candidate_raw, self.config)
            self.road_cost_dirty = False

        need_new_mclp = (
            self.mclp_data is None
            or rebuilt_matrix
            or self.mclp_data.P_max != P_max
            or self.mclp_data.budget != budget
        )
        if need_new_mclp:
            self.mclp_data = MCLP_Data(
                p=self._p, a=self._a, c=self._c,
                P_max=P_max, budget=budget, must_cover=must_cover,
            )
        else:
            # Chỉ p hoặc c đổi, ma trận a giữ nguyên -> patch tại chỗ, không tạo lại
            # sparse matrix / không mất cache coverage_lists đã build trên MCLP_Data.
            self.mclp_data.p = self._p.astype(np.float32)
            self.mclp_data.c = self._c.astype(np.float32)

        return self.mclp_data

    def snapshot(self) -> dict:
        return {
            "config_version": self.config_version,
            "n_demand_raw": len(self.demand_raw),
            "n_candidate_raw": len(self.candidate_raw_full),
            "n_candidate_eligible": None if self._candidate_idx is None else len(self._candidate_idx),
            "dirty": {
                "weight": self.weight_dirty,
                "radius": self.radius_dirty,
                "road_cost": self.road_cost_dirty,
                "road_eligibility": self.road_eligibility_dirty,
            },
            "mclp_ready": self.mclp_data is not None,
        }