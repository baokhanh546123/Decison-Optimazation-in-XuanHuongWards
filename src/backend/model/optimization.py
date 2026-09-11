from __future__ import annotations

"""
================================================================================
optimization.py — Multi-Objective Maximal Covering Location Problem (MO-MCLP)
                 ε-constraint solver (OR-Tools CP-SAT)
================================================================================

Bối cảnh Decision Intelligence
------------------------------
Bài toán định vị cơ sở (facility location) cần cân bằng hai mục tiêu mâu thuẫn:
  f1  max covering profit   Σ p_i y_i     (phủ nhu cầu / lợi nhuận)
  f2  min cost              Σ c_j x_j     (chi phí mở cơ sở)

Phương pháp ε-constraint giữ f1 làm objective, biến f2 thành ràng buộc ngân sách:
  max  Σ p_i y_i
  s.t. Σ c_j x_j  ≤  ε
       y_i ≤ Σ_j a_ij x_j
       Σ x_j ≤ P_max   (nếu có)
       x_j, y_i ∈ {0,1}

Quét ε trên [ε_min, ε_max] sinh tập nghiệm Pareto phục vụ ra quyết định.

Hai chế độ (eps_mode)
---------------------
┌────────────┬────────────────────────────────────────────────────────────────┐
│ notebook   │ Bám Optimization_fixed.ipynb — dùng để thử nghiệm / đối chiếu. │
│            │ • KHÔNG giảm tập candidate |J| (auto_reduce=False)              │
│            │ • ε_max = Σ c_j  (hoặc budget nếu có)                           │
│            │ • ε lấy đều bằng np.linspace                                    │
│            │ • Greedy warm-start 1 lần                                      │
│            │ • Default song song: n_parallel=4, workers_per_solve=2         │
│            │ ⚠ Với |J| ≈ 5000 và P_max nhỏ, gap có thể rất cao — dự kiến.  │
├────────────┼────────────────────────────────────────────────────────────────┤
│ tight      │ Hướng production — siết miền ε và (tuỳ chọn) giảm |J|.         │
│            │ • ε_max = tổng P_max candidate đắt nhất (trade-off thật)       │
│            │ • auto_reduce=True: giữ top-K candidate theo coverage weight   │
│            │ • Phù hợp máy ít CPU khi cần gap ổn định hơn                   │
└────────────┴────────────────────────────────────────────────────────────────┘

Cách gọi nhanh
--------------
  # Mode notebook (thử nghiệm, không reduction) — khuyến nghị đối chiếu ipynb
  opt = Optimization(data=data, ..., eps_mode="notebook")
  results = opt.epsilon_constraint_sweep_notebook()
  # hoặc: results = opt.epsilon_constraint_sweep(auto_reduce=False)

  # Mode tight (production)
  opt = Optimization(data=data, ..., eps_mode="tight", max_candidates=1200)
  results = opt.epsilon_constraint_sweep(auto_reduce=True)

Ma trận phủ dùng CSR sparse (tiết kiệm RAM); công thức ràng buộc phủ giữ nguyên
dạng notebook: y_i ≤ Σ_{j: a_ij=1} x_j.
"""

import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Sequence, Tuple

import numpy as np
from ortools.sat.python import cp_model

from dataclass.MCLP import MCLP_Data
from utils.load_data import clean_roads
from utils.candidate_grid import *
from core.coverage import build_coverage_matrix_sparse
from core.solver_worker import EpsilonTask, solve_one_epsilon


class Optimization:
    __slots__ = (
        "data", "demand_set", "candidate_set", "roads_set", "ward_polygon_wgs84",
        "max_radius_m", "n_points", "time_limit_s", "relative_gap", "n_parallel",
        "workers_per_solve", "use_hint", "non_monotonic_tol", "re_solve_flagged",
        "re_solve_time_limit", "grid_spacing_m", "street_spacing_m", "SCALE",
        "CPU_COUNT", "utm_epsg", "max_candidates", "eps_mode",
    )

    def __init__(
        self,
        data: Optional[MCLP_Data] = None,
        demand_set=None,
        candidate_set=None,
        roads_set: Optional[str] = None,
        ward_polygon_wgs84=None,
        n_points: int = 15,
        time_limit_s: int = 300,
        relative_gap: float = 0.05,
        n_parallel: int = 4,
        workers_per_solve: int = 2,
        use_hint: bool = True,
        non_monotonic_tol: float = 1e-6,
        re_solve_flagged: bool = True,
        re_solve_time_limit: int = 600,
        grid_spacing_m: float = 220.0,
        street_spacing_m: float = 80.0,
        max_radius_m: Optional[float] = None,
        SCALE: int = 10 ** 6,
        CPU_COUNT: Optional[int] = None,
        utm_epsg: int = 32648,
        max_candidates: int = 1200,
        eps_mode: str = "notebook",
    ):
        """
        Parameters
        ----------
        data, demand_set, candidate_set, roads_set, ward_polygon_wgs84
            Dữ liệu MO-MCLP đã lắp từ GeoDataFrame / MCLP_Data.
        n_points : int
            Số điểm ε trên Pareto front.
        time_limit_s, relative_gap, n_parallel, workers_per_solve
            Tham số CP-SAT và song song.
        eps_mode : {"notebook", "tight"}
            notebook — ε_max = sum(c), không bắt buộc giảm |J| (đối chiếu ipynb).
            tight    — ε_max = sum(top P_max costs); kết hợp auto_reduce khi cần.
        max_candidates : int
            Chỉ dùng khi auto_reduce=True (mode tight / production).
        """
        self.data = data
        self.demand_set = demand_set
        self.candidate_set = candidate_set
        self.roads_set = roads_set
        self.ward_polygon_wgs84 = ward_polygon_wgs84
        self.max_radius_m = max_radius_m
        self.SCALE = int(SCALE)
        self.n_points = n_points
        self.time_limit_s = time_limit_s
        self.relative_gap = relative_gap
        self.n_parallel = n_parallel
        self.workers_per_solve = workers_per_solve
        self.use_hint = use_hint
        self.non_monotonic_tol = non_monotonic_tol
        self.re_solve_flagged = re_solve_flagged
        self.re_solve_time_limit = re_solve_time_limit
        self.grid_spacing_m = grid_spacing_m
        self.street_spacing_m = street_spacing_m
        self.CPU_COUNT = max(1, os.cpu_count() or 1) if CPU_COUNT is None else CPU_COUNT
        self.utm_epsg = utm_epsg
        self.max_candidates = max_candidates
        self.eps_mode = eps_mode if eps_mode in ("notebook", "tight") else "notebook"

        if self.n_parallel * self.workers_per_solve > self.CPU_COUNT:
            print(
                f"      [CẢNH BÁO] n_parallel({self.n_parallel}) x "
                f"workers_per_solve({self.workers_per_solve}) = "
                f"{self.n_parallel * self.workers_per_solve} > CPU_COUNT({self.CPU_COUNT})"
            )

    # ------------------------------------------------------------------ #
    # Candidate reduction (TẮT mặc định trong bản thử nghiệm notebook)
    # ------------------------------------------------------------------ #
    def reduce_candidates_by_coverage(
        self,
        data: Optional[MCLP_Data] = None,
        max_candidates: Optional[int] = None,
    ) -> MCLP_Data:
        data = data if data is not None else self.data
        if data is None:
            raise ValueError("data is None")
        K = int(max_candidates if max_candidates is not None else self.max_candidates)
        n_j = data.n_j
        if n_j <= K:
            return data

        weights = np.zeros(n_j, dtype=np.float64)
        for i, js in enumerate(data.coverage_lists):
            pi = float(data.p[i])
            for j in js:
                weights[int(j)] += pi

        order = np.argsort(-weights)
        keep_sorted = np.sort(order[:K].astype(np.int64))

        a_new = data.a[:, keep_sorted].tocsr()
        c_new = data.c[keep_sorted]
        new_data = MCLP_Data(
            p=data.p.copy(),
            a=a_new,
            c=c_new,
            P_max=data.P_max,
            budget=data.budget,
            must_cover=data.must_cover.copy() if data.must_cover is not None else None,
        )
        print(
            f"[OK] Candidate reduction: |J| {n_j} → {new_data.n_j} "
            f"(top by coverage weight, max_candidates={K})"
        )
        self.data = new_data
        return new_data

    # ------------------------------------------------------------------ #
    # Build candidate / coverage
    # ------------------------------------------------------------------ #
    def build_candidate_set(self):
        grid_candidate = generate_candidate_grid(
            self.ward_polygon_wgs84, self.grid_spacing_m, self.utm_epsg
        )
        if not self.roads_set:
            self.candidate_set = grid_candidate
            return grid_candidate, np.ones(len(grid_candidate))

        print(f"\n[OK] Grid candidate: {len(grid_candidate)} vị trí (spacing {self.grid_spacing_m}m)")

        import geopandas as gpd
        roads_raw = gpd.read_file(self.roads_set)
        roads_clean = clean_roads(roads_raw)
        n_eligible = int(roads_clean["is_candidate_eligible"].sum())
        print(f"[OK] Roads: {len(roads_raw)} segment, {n_eligible} eligible sau clean_roads()")

        street_cand = generate_street_candidates(
            roads_clean, self.ward_polygon_wgs84, spacing_m=self.street_spacing_m,
            utm_epsg=self.utm_epsg, start_id=len(grid_candidate),
        )
        print(f"[OK] Street candidate: {len(street_cand)} vị trí (spacing {self.street_spacing_m}m)")

        merged = merge_candidate_sets(grid_candidate, street_cand, utm_epsg=self.utm_epsg)
        cost = derive_candidate_cost(merged)
        print(f"[OK] Candidate set J sau merge + dedup: {len(merged)}")

        self.candidate_set = merged
        return merged, cost

    def build_coverage_matrix(self):
        if self.demand_set is None or self.candidate_set is None:
            raise ValueError("demand_set và candidate_set phải được gán trước.")
        return build_coverage_matrix_sparse(
            self.demand_set, self.candidate_set,
            utm_epsg=self.utm_epsg, max_radius_m=self.max_radius_m,
        )

    # ------------------------------------------------------------------ #
    # Base model — giống ipynb: y_i <= sum x_j
    # ------------------------------------------------------------------ #
    def build_base_template(self):
        if self.data is None:
            raise ValueError("self.data (MCLP_Data) chưa được gán.")

        mdl = cp_model.CpModel()
        data = self.data
        n_i, n_j = data.n_i, data.n_j

        x = [mdl.NewBoolVar(f"x_{j}") for j in range(n_j)]
        y = [mdl.NewBoolVar(f"y_{i}") for i in range(n_i)]

        for i, covering_js in enumerate(data.coverage_lists):
            if covering_js.size == 0:
                mdl.Add(y[i] == 0)
            else:
                mdl.Add(y[i] <= sum(x[int(j)] for j in covering_js))

        if data.must_cover is not None:
            for i in data.must_cover:
                mdl.Add(y[int(i)] == 1)

        if data.P_max is not None:
            mdl.Add(sum(x) <= int(data.P_max)

        if data.budget is not None:
            c_int = np.round(data.c * self.SCALE).astype(np.int64)
            budget_int = int(round(float(data.budget) * self.SCALE))
            mdl.Add(sum(int(c_int[j]) * x[j] for j in range(n_j)) <= budget_int)

        return mdl, x, y

    # ------------------------------------------------------------------ #
    # Greedy hint — notebook: 1 pass
    # ------------------------------------------------------------------ #
    def _greedy_solution_simple(self, eps: float) -> Optional[List[int]]:
        """Greedy 1 lần — giống tinh thần warm-start đơn giản của notebook."""
        data = self.data
        n_j = data.n_j
        p, c = data.p, data.c
        P_max = int(data.P_max) if data.P_max is not None else n_j

        cand_covers: List[List[int]] = [[] for _ in range(n_j)]
        for i, js in enumerate(data.coverage_lists):
            for j in js:
                cand_covers[int(j)].append(i)

        covered = np.zeros(data.n_i, dtype=bool)
        chosen: List[int] = []
        remaining = float(eps)

        for _ in range(P_max):
            best_j, best_score = -1, -1.0
            for j in range(n_j):
                if j in chosen or c[j] > remaining + 1e-12:
                    continue
                gain = sum(float(p[i]) for i in cand_covers[j] if not covered[i])
                if gain <= 0:
                    continue
                score = gain * 1e6 if c[j] <= 1e-12 else gain / float(c[j])
                if score > best_score:
                    best_score = score
                    best_j = j
            if best_j < 0:
                break
            chosen.append(best_j)
            remaining -= float(c[best_j])
            for i in cand_covers[best_j]:
                covered[i] = True

        if not chosen:
            return None
        x = [0] * n_j
        for j in chosen:
            x[j] = 1
        f1 = float(sum(float(p[i]) for i in range(data.n_i) if covered[i]))
        print(f"[OK] Greedy warm-start (notebook-style): f1={f1:.3f}, n_fac={len(chosen)}")
        return x

    # ------------------------------------------------------------------ #
    # Epsilon range
    # ------------------------------------------------------------------ #
    def _compute_epsilon_range(self) -> tuple[float, float]:
        data = self.data
        c = np.asarray(data.c, dtype=np.float64)
        eps_min = float(np.min(c))

        if data.budget is not None:
            eps_max = float(data.budget)
        elif self.eps_mode == "tight" and data.P_max is not None and int(data.P_max) < data.n_j:
            P = int(data.P_max)
            eps_max = float(np.sort(c)[-P:].sum()) * 1.01
        else:
            # notebook mode: sum(c) — giống ipynb
            eps_max = float(np.sum(c))

        eps_max = max(eps_max, eps_min)
        return eps_min, eps_max

    def _make_epsilons(self) -> np.ndarray:
        eps_min, eps_max = self._compute_epsilon_range()
        return np.linspace(eps_min, eps_max, self.n_points).astype(float)

    # ------------------------------------------------------------------ #
    # Sweep chính
    # ------------------------------------------------------------------ #
    def epsilon_constraint_sweep(self, auto_reduce: bool = False):
        """Chạy ε-constraint.

        auto_reduce=False (mặc định bản thử nghiệm) — giữ nguyên |J| như ipynb.
        auto_reduce=True  — gọi reduce_candidates_by_coverage trước khi solve.
        """
        if self.data is None:
            raise ValueError("self.data chưa được gán")

        if auto_reduce and self.data.n_j > self.max_candidates:
            self.reduce_candidates_by_coverage(max_candidates=self.max_candidates)
        else:
            print(
                f"[EXPERIMENT] Không giảm candidate — |J|={self.data.n_j} "
                f"(giống notebook, auto_reduce=False)"
            )

        data = self.data
        n_i, n_j = data.n_i, data.n_j

        eps_min, eps_max = self._compute_epsilon_range()
        print(
            f"[INFO] mode={self.eps_mode} | CPU={self.CPU_COUNT} | "
            f"n_parallel={self.n_parallel} | time_limit={self.time_limit_s}s | "
            f"gap_target={self.relative_gap * 100:.1f}% | SCALE={self.SCALE:,}"
        )
        print(
            f"[INFO] ε range = [{eps_min:.4f}, {eps_max:.4f}]  "
            f"(P_max={data.P_max}, n_i={n_i}, n_j={n_j}, nnz={data.a.nnz})"
        )
        if data.P_max is not None:
            top = np.sort(data.c)[-int(data.P_max):]
            print(
                f"[INFO] top-{data.P_max} costs sum = {top.sum():.4f} | "
                f"sum(c) = {data.c.sum():.4f}"
            )

        base_mdl, _, _ = self.build_base_template()
        template_text = str(base_mdl.Proto())

        epsilons = self._make_epsilons()
        print(f"[INFO] Số điểm ε: {len(epsilons)}")

        results: list = []
        hint_x = None
        if self.use_hint:
            hint_x = self._greedy_solution_simple(float(epsilons[-1]))

        ctx = mp.get_context("fork")

        with ProcessPoolExecutor(max_workers=self.n_parallel, mp_context=ctx) as ex:
            for batch_start in range(0, len(epsilons), self.n_parallel):
                batch_eps = epsilons[batch_start: batch_start + self.n_parallel]
                tasks = [
                    EpsilonTask(
                        template_proto_text=template_text,
                        n_i=n_i,
                        n_j=n_j,
                        c=data.c,
                        p=data.p,
                        eps=float(eps),
                        time_limit_s=self.time_limit_s,
                        num_search_workers=self.workers_per_solve,
                        relative_gap=self.relative_gap,
                        hint_x=hint_x if self.use_hint else None,
                        scale=self.SCALE,
                    )
                    for eps in batch_eps
                ]

                for eps_val, r in zip(batch_eps, ex.map(solve_one_epsilon, tasks)):
                    if r is None:
                        print(
                            f"  → ε={eps_val:.4f} FAILED "
                            f"(infeasible / no solution trong time_limit)"
                        )
                        continue
                    new_x = r.pop("x_solution")
                    if self.use_hint:
                        hint_x = new_x
                    results.append(r)
                    print(
                        f"  → ε={r['epsilon']:.4f}  f1={r['f1_covering_profit']:.3f}  "
                        f"f2={r['f2_cost']:.4f}  n_fac={r['n_facilities']}  "
                        f"gap={r['optimality_gap_pct']:.2f}%  t={r['solve_time_s']:.1f}s"
                    )

        results.sort(key=lambda r: r["epsilon"])
        self._flag_non_monotonic(results)

        if self.re_solve_flagged:
            self._resolve_flagged_points(results, template_text, n_i, n_j, hint_x)

        results.sort(key=lambda r: r["epsilon"])
        self._report_summary(results)
        return results

    def epsilon_constraint_sweep_notebook(self):
        """API rõ ràng: chạy đúng kiểu Optimization_fixed.ipynb.

        - Không giảm |J|
        - eps_mode = notebook (ε_max = sum c)
        - n_parallel / workers giữ theo __init__ (mặc định 4 x 2 như ipynb)
        """
        prev = self.eps_mode
        self.eps_mode = "notebook"
        try:
            return self.epsilon_constraint_sweep(auto_reduce=False)
        finally:
            self.eps_mode = prev

    def _flag_non_monotonic(self, results: list) -> None:
        running_max_f1 = -np.inf
        for r in results:
            r["flagged_non_monotonic"] = bool(
                r["f1_covering_profit"] < running_max_f1 - self.non_monotonic_tol
            )
            running_max_f1 = max(running_max_f1, r["f1_covering_profit"])

    def _resolve_flagged_points(
        self,
        results: list,
        template_text: str,
        n_i: int,
        n_j: int,
        best_hint: Optional[Sequence[int]] = None,
    ) -> None:
        data = self.data
        gap_threshold = 20.0
        flagged_idx = [
            idx for idx, r in enumerate(results)
            if r["flagged_non_monotonic"] or r["optimality_gap_pct"] > gap_threshold
        ]
        if not flagged_idx:
            return

        print(
            f"\n[RE-SOLVE] {len(flagged_idx)} điểm (non-monotonic hoặc gap > {gap_threshold}%) — "
            f"time_limit={self.re_solve_time_limit}s"
        )

        for idx in flagged_idx:
            eps = results[idx]["epsilon"]
            print(f"  → Re-solving ε={eps:.4f} ...", end=" ", flush=True)

            current_chosen = results[idx].get("chosen_candidates", [])
            local_hint = [0] * n_j
            for j in current_chosen:
                if 0 <= j < n_j:
                    local_hint[j] = 1
            if sum(local_hint) == 0 and best_hint is not None:
                local_hint = list(best_hint)

            task = EpsilonTask(
                template_proto_text=template_text,
                n_i=n_i,
                n_j=n_j,
                c=data.c,
                p=data.p,
                eps=float(eps),
                time_limit_s=self.re_solve_time_limit,
                num_search_workers=self.workers_per_solve,
                relative_gap=0.01,
                hint_x=local_hint,
                scale=self.SCALE,
            )
            r_new = solve_one_epsilon(task)
            if (
                r_new is not None
                and r_new["f1_covering_profit"] >= results[idx]["f1_covering_profit"] - 1e-6
            ):
                r_new.pop("x_solution", None)
                r_new["flagged_non_monotonic"] = False
                results[idx] = r_new
                print(
                    f"CẢI THIỆN → f1={r_new['f1_covering_profit']:.3f} "
                    f"gap={r_new['optimality_gap_pct']:.2f}%"
                )
            else:
                print("không cải thiện")

    def _report_summary(self, results: list) -> None:
        if not results:
            print("\n      [epsilon_constraint_sweep] Không có nghiệm nào.")
            return
        n_flagged = sum(1 for r in results if r["flagged_non_monotonic"])
        gaps = [r["optimality_gap_pct"] for r in results]
        avg_gap = float(np.mean(gaps))
        max_gap = float(np.max(gaps))
        print(
            f"\n      [epsilon_constraint_sweep] {len(results)} điểm Pareto, "
            f"{n_flagged} non-monotonic, gap TB={avg_gap:.2f}%, gap max={max_gap:.2f}%"
        )
        if avg_gap > 20:
            print(
                f"      [CẢNH BÁO] gap TB > 20% — với |J| lớn không reduction đây là dự kiến. "
                f"Thử eps_mode='tight' + auto_reduce=True để so sánh."
            )
