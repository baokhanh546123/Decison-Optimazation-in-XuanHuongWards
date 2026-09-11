from __future__ import annotations

import os
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Sequence

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
        time_limit_s: int = 180,
        relative_gap: float = 0.02,
        n_parallel: int = 1,
        workers_per_solve: int = 8,
        use_hint: bool = True,
        non_monotonic_tol: float = 1e-5,
        re_solve_flagged: bool = True,
        re_solve_time_limit: int = 600,
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
        self.CPU_COUNT = max(1, os.cpu_count() or 1) if CPU_COUNT is None else CPU_COUNT
        self.utm_epsg = utm_epsg

        if self.n_parallel * self.workers_per_solve > self.CPU_COUNT:
            print(
                f"      [CẢNH BÁO] n_parallel({self.n_parallel}) x "
                f"workers_per_solve({self.workers_per_solve}) = "
                f"{self.n_parallel * self.workers_per_solve} > CPU_COUNT({self.CPU_COUNT}) "
                f"-> có thể oversubscribe, cân nhắc giảm 1 trong 2 tham số."
            )

    # ------------------------------------------------------------------ #
    # 1. Candidate set
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
    # 2. Coverage matrix
    # ------------------------------------------------------------------ #
    def build_coverage_matrix(self):
        if self.demand_set is None or self.candidate_set is None:
            raise ValueError("demand_set và candidate_set phải được gán trước khi build coverage matrix.")
        return build_coverage_matrix_sparse(
            self.demand_set, self.candidate_set,
            utm_epsg=self.utm_epsg, max_radius_m=self.max_radius_m,
        )

    # ------------------------------------------------------------------ #
    # 3. Base CP-SAT template — mạnh hơn với singleton cover
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
            covering_js = np.asarray(covering_js, dtype=np.int64)
            if covering_js.size == 0:
                mdl.Add(y[i] == 0)
            elif covering_js.size == 1:
                # Singleton: y_i <=> x_j (chặt hơn inequality thuần)
                j = int(covering_js[0])
                mdl.Add(y[i] <= x[j])
                mdl.Add(x[j] <= y[i])
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
    # 3b. Greedy constructive heuristic — warm-start
    # ------------------------------------------------------------------ #
    def _greedy_solution(self, eps: float) -> Optional[List[int]]:
        """Chọn lần lượt candidate mang lại p_i chưa phủ / chi phí cao nhất,
        dưới ngân sách eps và P_max. Trả về vector x nhị phân hoặc None."""
        data = self.data
        n_j = data.n_j
        p = data.p
        c = data.c
        P_max = data.P_max if data.P_max is not None else n_j

        covered = np.zeros(data.n_i, dtype=bool)
        chosen: List[int] = []
        remaining_budget = float(eps)

        cand_covers: List[List[int]] = [[] for _ in range(n_j)]
        for i, js in enumerate(data.coverage_lists):
            for j in js:
                cand_covers[int(j)].append(i)

        for _ in range(P_max):
            best_j = -1
            best_score = -1.0
            for j in range(n_j):
                if j in chosen or c[j] > remaining_budget + 1e-12:
                    continue
                gain = 0.0
                for i in cand_covers[j]:
                    if not covered[i]:
                        gain += float(p[i])
                if c[j] <= 1e-12:
                    score = gain * 1e6
                else:
                    score = gain / float(c[j])
                if score > best_score:
                    best_score = score
                    best_j = j
            if best_j < 0 or best_score <= 0:
                break
            chosen.append(best_j)
            remaining_budget -= float(c[best_j])
            for i in cand_covers[best_j]:
                covered[i] = True

        if not chosen:
            return None
        x = [0] * n_j
        for j in chosen:
            x[j] = 1
        return x

    # ------------------------------------------------------------------ #
    # 4. Epsilon range — thắt chặt theo P_max
    # ------------------------------------------------------------------ #
    def _compute_epsilon_range(self) -> tuple[float, float]:
        data = self.data
        c = data.c
        eps_min = float(np.min(c))

        if data.budget is not None:
            eps_max = float(data.budget)
        elif data.P_max is not None and data.P_max < data.n_j:
            top = np.sort(c)[-data.P_max:]
            eps_max = float(top.sum())
        else:
            eps_max = float(c.sum())

        eps_max = max(eps_max, eps_min)
        return eps_min, eps_max

    def _make_epsilons(self) -> np.ndarray:
        """Sinh điểm ε dày hơn ở vùng thấp-trung (khó chứng minh gap hơn)."""
        eps_min, eps_max = self._compute_epsilon_range()
        if self.n_points <= 2:
            return np.array([eps_min, eps_max], dtype=float)

        mid = eps_min + 0.55 * (eps_max - eps_min)
        n_low = max(2, int(round(self.n_points * 0.6)))
        n_high = self.n_points - n_low + 1
        low = np.linspace(eps_min, mid, n_low)
        high = np.linspace(mid, eps_max, n_high)[1:]
        eps = np.unique(np.concatenate([low, high]))
        if len(eps) > self.n_points:
            idx = np.linspace(0, len(eps) - 1, self.n_points).astype(int)
            eps = eps[idx]
        return eps.astype(float)

    # ------------------------------------------------------------------ #
    # 5. Epsilon-constraint sweep
    # ------------------------------------------------------------------ #
    def epsilon_constraint_sweep(self):
        data = self.data
        n_i, n_j = data.n_i, data.n_j

        eps_min, eps_max = self._compute_epsilon_range()
        print(
            f"[INFO] CPU={self.CPU_COUNT} | n_parallel={self.n_parallel} | "
            f"time_limit={self.time_limit_s}s | gap_target={self.relative_gap * 100:.1f}% | "
            f"SCALE={self.SCALE:,}"
        )
        print(
            f"[INFO] ε range = [{eps_min:.4f}, {eps_max:.4f}]  "
            f"(P_max={data.P_max}, tight upper từ top-P_max costs)"
        )

        base_mdl, _, _ = self.build_base_template()
        template_text = str(base_mdl.Proto())

        epsilons = self._make_epsilons()
        print(f"[INFO] Số điểm ε thực tế: {len(epsilons)}")

        results: list = []
        hint_x = self._greedy_solution(float(epsilons[-1])) if self.use_hint else None
        if hint_x is not None:
            print(f"[OK] Greedy warm-start: {sum(hint_x)} facilities")

        ctx = mp.get_context("fork")

        with ProcessPoolExecutor(max_workers=self.n_parallel, mp_context=ctx) as ex:
            for batch_start in range(0, len(epsilons), self.n_parallel):
                batch_eps = epsilons[batch_start: batch_start + self.n_parallel]
                tasks = []
                for eps in batch_eps:
                    local_hint = None
                    if hint_x is not None and self.use_hint:
                        cost_so_far = 0.0
                        filtered = [0] * n_j
                        order = [j for j in range(n_j) if hint_x[j]]
                        for j in order:
                            if cost_so_far + data.c[j] <= eps + 1e-9:
                                filtered[j] = 1
                                cost_so_far += float(data.c[j])
                        local_hint = filtered

                    tasks.append(
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
                            hint_x=local_hint,
                            scale=self.SCALE,
                        )
                    )

                for eps_val, r in zip(batch_eps, ex.map(solve_one_epsilon, tasks)):
                    if r is None:
                        print(f"  → ε={eps_val:.4f} FAILED (infeasible / no solution trong time_limit)")
                        continue
                    new_x = r.pop("x_solution")
                    # Luôn cập nhật hint theo nghiệm mới nhất để lan truyền tốt trên Pareto
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

    def _flag_non_monotonic(self, results: list) -> None:
        """f1 không được giảm khi epsilon tăng (đơn điệu theo lý thuyết MCLP)."""
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
        """Re-solve điểm non-monotonic hoặc gap > 8% với time dài hơn + gap chặt hơn."""
        data = self.data
        gap_threshold = 8.0
        flagged_idx = [
            idx for idx, r in enumerate(results)
            if r["flagged_non_monotonic"] or r["optimality_gap_pct"] > gap_threshold
        ]
        if not flagged_idx:
            return

        print(
            f"\n[RE-SOLVE] {len(flagged_idx)} điểm (non-monotonic hoặc gap > {gap_threshold}%) — "
            f"time_limit={self.re_solve_time_limit}s, relative_gap=0.5%"
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
                relative_gap=0.005,
                hint_x=local_hint,
                scale=self.SCALE,
            )
            r_new = solve_one_epsilon(task)
            if r_new is not None and r_new["f1_covering_profit"] >= results[idx]["f1_covering_profit"] - 1e-6:
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
            f"{n_flagged} điểm non-monotonic, "
            f"gap trung bình={avg_gap:.2f}%, gap max={max_gap:.2f}%"
        )
        if avg_gap > 10:
            print(
                f"      [CẢNH BÁO] gap trung bình > 10% → tăng time_limit_s "
                f"(hiện {self.time_limit_s}s) hoặc workers_per_solve, "
                f"giảm n_points, rồi chạy lại."
            )
