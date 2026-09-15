from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

import os

class TaxonomyEntry(BaseModel):
    root: str
    weight: float
    radius_m: float


class TaxonomyUpdateRequest(BaseModel):
    weight: Optional[float] = Field(None, ge=0, le=5, description="p_i weight cho taxonomy_root này")
    radius_m: Optional[float] = Field(None, gt=0, le=5000, description="Bán kính phủ (m)")

    @model_validator(mode="after")
    def at_least_one(self):
        if self.weight is None and self.radius_m is None:
            raise ValueError("Cần ít nhất 1 trong 2: weight hoặc radius_m")
        return self


class RoadClassEntry(BaseModel):
    class_name: str
    cost_rank: float
    excluded: bool
    low_priority: bool


class RoadClassUpdateRequest(BaseModel):
    cost_rank: Optional[float] = Field(None, ge=0)
    excluded: Optional[bool] = None
    low_priority: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if self.cost_rank is None and self.excluded is None and self.low_priority is None:
            raise ValueError("Cần ít nhất 1 trong: cost_rank, excluded, low_priority")
        return self

_CPU_COUNT = os.cpu_count() or 1

class OptimizeRequest(BaseModel):
    P_max: Optional[int] = Field(None, ge=1, le=50)
    budget: Optional[float] = Field(None, gt=0)
    n_points: int = Field(12, ge=2, le=60)
    time_limit_s: int = Field(120, ge=5, le=1800)
    relative_gap: float = Field(0.05, gt=0, le=0.5)
    n_parallel: int = Field(2, ge=1, le=8)
    workers_per_solve: int = Field(2, ge=1, le=8)
    use_hint: bool = True
    re_solve_flagged: bool = True
    re_solve_time_limit: int = Field(300, ge=5, le=3600)
    max_radius_m: Optional[float] = None
    SCALE: int = Field(10 ** 6, ge=10 ** 4, le=10 ** 9)

    @model_validator(mode="after")
    def cap_cpu_usage(self):
        if self.n_parallel * self.workers_per_solve > _CPU_COUNT:
            raise ValueError(
                f"n_parallel({self.n_parallel}) x workers_per_solve({self.workers_per_solve}) "
                f"= {self.n_parallel * self.workers_per_solve} vượt CPU_COUNT({_CPU_COUNT}) của "
                f"server — giảm 1 trong 2 tham số."
            )
        return self


class ParetoPoint(BaseModel):
    epsilon: float
    f1_covering_profit: float
    f2_cost: float
    n_facilities: int
    chosen_candidates: List[int]
    status: str
    optimality_gap_pct: float
    solve_time_s: float
    flagged_non_monotonic: bool


class JobStatus(BaseModel):
    job_id: str
    state: str  # queued | running | done | failed
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    config_version: int
    error: Optional[str] = None
    results: Optional[List[ParetoPoint]] = None