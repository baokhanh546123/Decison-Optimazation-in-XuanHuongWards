"""Schema request cho trang runner — khớp với `window.getRunConfig()` ở runner_page.js.

Tách khỏi api/schemas.py (của repo thuật toán) để không sửa file gốc.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TaxonomyOverride(BaseModel):
    radius_m: float = Field(..., gt=0, le=5000, description="Bán kính phủ (m) của taxonomy_root")
    weight: float = Field(..., ge=0, le=5, description="Trọng số p_i của taxonomy_root")


class PerCandidate(BaseModel):
    demand: float = Field(0.0, ge=0, le=1, description="Ngưỡng demand-weight: candidate chỉ phủ demand có p_i ≥ demand × max(p)")
    conf: float = Field(0.0, ge=0, le=1, description="Confidence tối thiểu của chính candidate")


class RunnerOptimizeRequest(BaseModel):
    candidates: List[str] = Field(..., min_length=1, max_length=400, description="uid các candidate đã chọn (tập J)")
    taxonomy_root: Dict[str, TaxonomyOverride] = Field(default_factory=dict)
    per_candidate: Dict[str, PerCandidate] = Field(default_factory=dict)
    min_confidence: float = Field(0.3, ge=0, le=1, description="Confidence tối thiểu toàn cục (demand + candidate)")
    P_max: Optional[int] = Field(None, ge=1, le=50)
    n_points: int = Field(12, ge=2, le=60)
    lambda_: List[int] = Field(default_factory=lambda: [55, 45], alias="lambda")

    # --- tham số Benders ---
    benders_max_iters: int = Field(100, ge=1, le=1000)
    benders_master_time_limit_s: float = Field(3.0, gt=0, le=120)
    time_limit_s: int = Field(60, ge=5, le=1800, description="Ngân sách thời gian mỗi điểm ε")
    relative_gap: float = Field(0.01, gt=0, le=0.5)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def check_lambda(self):
        if len(self.lambda_) != 2 or any(v < 0 for v in self.lambda_) or sum(self.lambda_) <= 0:
            raise ValueError("lambda phải gồm 2 số ≥ 0, tổng > 0")
        return self
