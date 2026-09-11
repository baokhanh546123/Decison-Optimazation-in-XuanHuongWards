from __future__ import annotations

import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

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
        "CPU_COUNT", "utm_epsg",
    )

    def __init__(
        self,
        data: Optional[MCLP_Data] = None,
        demand_set=None,
        candidate_set=None,
        roads_set: Optional[str] = None,
        ward_polygon_wgs84=None,
        n_points: int = 12,
        time_limit_s: int = 300,
        relative_gap: float = 0.05,
        n_parallel: int = 1,
        workers_per_solve: int = 8,
        use_hint: bool = True,
        non_monotonic_tol: float = 1e-5,
        re_solve_flagged: bool = True,
        re_solve_time_limit: int = 900,
        grid_spacing_m: float = 220.0,
        street_spacing_m: float = 80.0,
        max_radius_m: Optional[float] = None,
        SCALE: int = 10 ** 6,
        CPU_COUNT: Optional[int] = None,
        utm_epsg: int = 32648,
    ):
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
        self.CPU_COUNT = max(1,os.cpu_count()) if CPU_COUNT is None else CPU_COUNT
        self.utm_epsg = utm_epsg

        if self.n_parallel * self.workers_per_solve > self.CPU_COUNT:
            print(
                f"      [CẢNH BÁO] n_parallel({self.n_parallel}) x "
                f"workers_per_solve({self.workers_per_solve}) = "
                f"{self.n_parallel * self.workers_per_solve} > CPU_COUNT({self.CPU_COUNT}) "
                f"-> có thể oversubscribe, cân nhắc giảm 1 trong 2 tham số."
            )

    # ------------------------------------------------------------------ #
    # 1. Candidate set — chỉ gọi lại utils/ nguyên vẹn
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

    # ------------------------------------------------------------------ #
    # 2. Coverage matrix — sparse, không cấp phát dense O(n_i * n_j)
    # ------------------------------------------------------------------ #
    def build_coverage_matrix(self):
        if self.demand_set is None or self.candidate_set is None:
            raise ValueError("demand_set và candidate_set phải được gán trước khi build coverage matrix.")
        return build_coverage_matrix_sparse(
            self.demand_set, self.candidate_set,
            utm_epsg=self.utm_epsg, max_radius_m=self.max_radius_m,
        )

    # ------------------------------------------------------------------ #
    # 3. Base CP-SAT template — dùng coverage_lists (CSR) thay vì np.where dense
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
                mdl.Add(y[i] <= sum(x[j] for j in covering_js))

        if data.must_cover is not None:
            for i in data.must_cover:
                mdl.Add(y[i] == 1)

        if data.P_max is not None:
            mdl.Add(sum(x) <= data.P_max)

        if data.budget is not None:
            c_int = np.round(data.c * self.SCALE).astype(np.int64)
            budget_int = int(round(data.budget * self.SCALE))
            mdl.Add(sum(int(c_int[j]) * x[j] for j in range(n_j)) <= budget_int)

        return mdl, x, y

    # ------------------------------------------------------------------ #
    # 4. Epsilon-constraint sweep — song song theo batch + re-solve điểm xấu
    # ------------------------------------------------------------------ #
    def epsilon_constraint_sweep(self):
        data = self.data
        n_i, n_j = data.n_i, data.n_j

        print(
            f"[INFO] CPU={self.CPU_COUNT} | n_parallel={self.n_parallel} | "
            f"time_limit={self.time_limit_s}s | gap_target={self.relative_gap * 100:.1f}% | "
            f"SCALE={self.SCALE:,}"
        )

        base_mdl, _, _ = self.build_base_template()
        template_text = str(base_mdl.Proto())

        eps_min = float(data.c.min())
        eps_max = float(data.budget) if data.budget is not None else float(data.c.sum())
        epsilons = np.linspace(eps_min, eps_max, self.n_points)

        results: list = []
        hint_x = None
        ctx = mp.get_context("fork")

        with ProcessPoolExecutor(max_workers=self.n_parallel, mp_context=ctx) as ex:
            for batch_start in range(0, self.n_points, self.n_parallel):
                batch_eps = epsilons[batch_start: batch_start + self.n_parallel]
                tasks = [
                    EpsilonTask(
                        template_proto_text=template_text, n_i=n_i, n_j=n_j,
                        c=data.c, p=data.p, eps=float(eps),
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
                        print(f"  → ε={eps_val:.3f} FAILED (infeasible/no solution trong time_limit)")
                        continue
                    hint_x = r.pop("x_solution")
                    results.append(r)
                    print(
                        f"  → ε={r['epsilon']:.3f}  f1={r['f1_covering_profit']:.2f}  "
                        f"f2={r['f2_cost']:.3f}  n_fac={r['n_facilities']}  "
                        f"gap={r['optimality_gap_pct']:.1f}%"
                    )

        results.sort(key=lambda r: r["epsilon"])
        self._flag_non_monotonic(results)

        if self.re_solve_flagged:
            self._resolve_flagged_points(results, template_text, n_i, n_j)

        results.sort(key=lambda r: r["epsilon"])
        self._report_summary(results)
        return results

    def _flag_non_monotonic(self, results: list) -> None:
        """f1 không được giảm khi epsilon tăng (đơn điệu theo lý thuyết MCLP);
        điểm nào giảm so với max đã thấy trước đó bị gắn cờ."""
        running_max_f1 = -np.inf
        for r in results:
            r["flagged_non_monotonic"] = bool(
                r["f1_covering_profit"] < running_max_f1 - self.non_monotonic_tol
            )
            running_max_f1 = max(running_max_f1, r["f1_covering_profit"])

    def _resolve_flagged_points(self, results: list, template_text: str, n_i: int, n_j: int) -> None:
        """Chạy lại các điểm bị gắn cờ non-monotonic HOẶC có gap > 15% với time_limit
        dài hơn (re_solve_time_limit) và relative_gap chặt hơn (0.5%). Chỉ nhận nghiệm
        mới nếu f1 không TỆ HƠN nghiệm cũ — tránh việc re-solve với ràng buộc khác vô
        tình làm xấu kết quả đã có."""
        data = self.data
        flagged_idx = [
            idx for idx, r in enumerate(results)
            if r["flagged_non_monotonic"] or r["optimality_gap_pct"] > 15
        ]
        if not flagged_idx:
            return

        print(
            f"\n[RE-SOLVE] {len(flagged_idx)} điểm bị gắn cờ / gap cao — "
            f"chạy lại với time_limit={self.re_solve_time_limit}s, relative_gap=0.5%"
        )
        for idx in flagged_idx:
            eps = results[idx]["epsilon"]
            print(f"  → Re-solving ε={eps:.3f} ...", end=" ", flush=True)
            task = EpsilonTask(
                template_proto_text=template_text, n_i=n_i, n_j=n_j,
                c=data.c, p=data.p, eps=float(eps),
                time_limit_s=self.re_solve_time_limit,
                num_search_workers=self.workers_per_solve,
                relative_gap=0.005,
                hint_x=None, scale=self.SCALE,
            )
            r_new = solve_one_epsilon(task)
            if r_new is not None and r_new["f1_covering_profit"] >= results[idx]["f1_covering_profit"] - 1e-6:
                r_new.pop("x_solution", None)
                r_new["flagged_non_monotonic"] = False
                results[idx] = r_new
                print(f"CẢI THIỆN → f1={r_new['f1_covering_profit']:.2f} gap={r_new['optimality_gap_pct']:.1f}%")
            else:
                print("không cải thiện")

    def _report_summary(self, results: list) -> None:
        n_flagged = sum(r["flagged_non_monotonic"] for r in results)
        avg_gap = float(np.mean([r["optimality_gap_pct"] for r in results])) if results else float("nan")
        print(
            f"\n      [epsilon_constraint_sweep] {len(results)} điểm Pareto, "
            f"{n_flagged} điểm bị gắn cờ non-monotonic, gap trung bình={avg_gap:.1f}%"
        )
        if avg_gap > 20:
            print(
                f"      [CẢNH BÁO] gap trung bình > 20% -> tăng time_limit_s "
                f"(hiện {self.time_limit_s}s) hoặc giảm n_points/n_parallel để mỗi "
                f"solve có nhiều worker hơn, rồi chạy lại trước khi tin kết quả."
            )