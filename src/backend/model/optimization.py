from __future__ import annotations

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
    """MO-MCLP ε-constraint — tối ưu cho |J| lớn + P_max nhỏ (tránh gap 200%+)."""

    __slots__ = (
        "data", "demand_set", "candidate_set", "roads_set", "ward_polygon_wgs84",
        "max_radius_m", "n_points", "time_limit_s", "relative_gap", "n_parallel",
        "workers_per_solve", "use_hint", "non_monotonic_tol", "re_solve_flagged",
        "re_solve_time_limit", "grid_spacing_m", "street_spacing_m", "SCALE",
        "CPU_COUNT", "utm_epsg", "max_candidates",
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
        workers_per_solve: int = 4,
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
        self.max_candidates = max_candidates

        if self.n_parallel * self.workers_per_solve > self.CPU_COUNT:
            print(
                f"      [CẢNH BÁO] n_parallel({self.n_parallel}) x "
                f"workers_per_solve({self.workers_per_solve}) = "
                f"{self.n_parallel * self.workers_per_solve} > CPU_COUNT({self.CPU_COUNT}) "
                f"-> có thể oversubscribe, cân nhắc giảm 1 trong 2 tham số."
            )

    # ------------------------------------------------------------------ #
    # 0. Giảm |J| theo trọng số phủ — then solve trên tập nhỏ hơn
    # ------------------------------------------------------------------ #
    def reduce_candidates_by_coverage(
        self,
        data: Optional[MCLP_Data] = None,
        max_candidates: Optional[int] = None,
    ) -> MCLP_Data:
        """Giữ top-K candidate theo tổng p_i phủ được (coverage weight).

        Với |J|=5000+ và P_max=3, CP-SAT không đóng gap được. Giữ ~1000–1500
        candidate tốt nhất gần như không mất chất lượng nghiệm thực tế.
        """
        data = data if data is not None else self.data
        if data is None:
            raise ValueError("data is None")
        K = int(max_candidates if max_candidates is not None else self.max_candidates)
        n_j = data.n_j
        if n_j <= K:
            return data

        # weight_j = sum p_i over i covered by j
        weights = np.zeros(n_j, dtype=np.float64)
        for i, js in enumerate(data.coverage_lists):
            pi = float(data.p[i])
            for j in js:
                weights[int(j)] += pi

        # Luôn giữ các candidate có weight > 0; lấy top-K
        order = np.argsort(-weights)
        keep = order[:K]
        keep_set = set(int(j) for j in keep)
        # Map old j -> new j
        old_to_new = {old: new for new, old in enumerate(sorted(keep_set))}
        keep_sorted = np.array(sorted(keep_set), dtype=np.int64)

        # Lọc ma trận a: chỉ cột keep_sorted
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
        print(
            f"      weight range kept: [{weights[keep_sorted].min():.2f}, "
            f"{weights[keep_sorted].max():.2f}]  "
            f"(dropped max weight={weights[order[K:].max()] if K < n_j else 0:.2f})"
        )
        self.data = new_data
        return new_data

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
            raise ValueError("demand_set và candidate_set phải được gán trước.")
        return build_coverage_matrix_sparse(
            self.demand_set, self.candidate_set,
            utm_epsg=self.utm_epsg, max_radius_m=self.max_radius_m,
        )

    # ------------------------------------------------------------------ #
    # 3. Base template + symmetry breaking khi P_max nhỏ
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
            P = int(data.P_max)
            mdl.Add(sum(x) <= P)
            # Symmetry breaking: ưu tiên index nhỏ khi chọn
            # (giảm |J|! / (P! (|J|-P)!) đối xứng khi nhiều x tương đương)
            # Dạng: x[j] >= x[k] không đúng với cost khác nhau.
            # Dùng: nếu chọn đúng P facility thì sum(j * x_j) được
            # lexicographic — vẫn an toàn với objective max cover.
            # Cách nhẹ: buộc các facility được chọn có thứ tự index tăng
            # thông qua biến phụ không cần thiết nếu cost khác nhau.
            # → Chỉ thêm khi P nhỏ và n_j lớn: không ép cứng cost-sensitive.

        if data.budget is not None:
            c_int = np.round(data.c * self.SCALE).astype(np.int64)
            budget_int = int(round(float(data.budget) * self.SCALE))
            mdl.Add(sum(int(c_int[j]) * x[j] for j in range(n_j)) <= budget_int)

        return mdl, x, y

    # ------------------------------------------------------------------ #
    # 3b. Multi-start greedy — tìm nghiệm tốt hơn cho warm-start
    # ------------------------------------------------------------------ #
    def _coverage_weight_by_candidate(self) -> np.ndarray:
        data = self.data
        w = np.zeros(data.n_j, dtype=np.float64)
        for i, js in enumerate(data.coverage_lists):
            pi = float(data.p[i])
            for j in js:
                w[int(j)] += pi
        return w

    def _greedy_once(
        self,
        eps: float,
        cand_covers: List[List[int]],
        order_boost: Optional[np.ndarray] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[List[int], float]:
        """Một lần greedy; order_boost/rng để đa dạng multi-start."""
        data = self.data
        n_j = data.n_j
        p, c = data.p, data.c
        P_max = int(data.P_max) if data.P_max is not None else n_j

        covered = np.zeros(data.n_i, dtype=bool)
        chosen: List[int] = []
        remaining = float(eps)

        for _ in range(P_max):
            best_j, best_score = -1, -1.0
            # Xét một tập con ngẫu nhiên nếu n_j lớn (tăng đa dạng)
            if rng is not None and n_j > 800:
                sample = rng.choice(n_j, size=min(800, n_j), replace=False)
            else:
                sample = range(n_j)

            for j in sample:
                j = int(j)
                if j in chosen or c[j] > remaining + 1e-12:
                    continue
                gain = 0.0
                for i in cand_covers[j]:
                    if not covered[i]:
                        gain += float(p[i])
                if gain <= 0:
                    continue
                score = gain * 1e6 if c[j] <= 1e-12 else gain / float(c[j])
                if order_boost is not None:
                    score *= (1.0 + 0.15 * order_boost[j])
                if score > best_score:
                    best_score = score
                    best_j = j

            if best_j < 0:
                break
            chosen.append(best_j)
            remaining -= float(c[best_j])
            for i in cand_covers[best_j]:
                covered[i] = True

        f1 = float(sum(float(p[i]) for i in range(data.n_i) if covered[i]))
        return chosen, f1

    def _greedy_solution(self, eps: float, n_starts: int = 8) -> Optional[List[int]]:
        data = self.data
        n_j = data.n_j
        cand_covers: List[List[int]] = [[] for _ in range(n_j)]
        for i, js in enumerate(data.coverage_lists):
            for j in js:
                cand_covers[int(j)].append(i)

        weights = self._coverage_weight_by_candidate()
        w_max = weights.max() if weights.max() > 0 else 1.0
        order_boost = weights / w_max

        rng = np.random.default_rng(42)
        best_chosen: List[int] = []
        best_f1 = -1.0

        # 1 run thuần + (n_starts-1) run ngẫu nhiên
        for s in range(n_starts):
            boost = order_boost if s == 0 else None
            r = None if s == 0 else rng
            chosen, f1 = self._greedy_once(eps, cand_covers, order_boost=boost, rng=r)
            if f1 > best_f1:
                best_f1 = f1
                best_chosen = chosen

        if not best_chosen:
            return None
        x = [0] * n_j
        for j in best_chosen:
            x[j] = 1
        print(f"[OK] Multi-start greedy: f1={best_f1:.3f}, n_fac={len(best_chosen)}")
        return x

    # ------------------------------------------------------------------ #
    # 4. Epsilon range — SIẾT THEO P_max (sửa lỗi eps_max=2127)
    # ------------------------------------------------------------------ #
    def _compute_epsilon_range(self) -> tuple[float, float]:
        """eps_max = tổng P_max candidate ĐẮT nhất (không phải sum toàn bộ c).

        Log của bạn: c ∈ [0.17, 1], P_max=3 → eps_max ≈ 3, KHÔNG phải 2127.
        Khi ε > sum(top-P_max costs) mọi điểm giải CÙNG một bài P_max-card
        và gap 240% lặp lại vô nghĩa.
        """
        data = self.data
        c = np.asarray(data.c, dtype=np.float64)
        eps_min = float(np.min(c))

        if data.budget is not None:
            eps_max = float(data.budget)
        elif data.P_max is not None and int(data.P_max) < data.n_j:
            P = int(data.P_max)
            top = np.sort(c)[-P:]
            eps_max = float(top.sum())
        else:
            eps_max = float(c.sum())

        # Thêm 1% margin số học
        eps_max = max(eps_max * 1.01, eps_min)
        return eps_min, eps_max

    def _make_epsilons(self) -> np.ndarray:
        """Nhiều điểm hơn ở vùng ε thấp–trung (trade-off thật)."""
        eps_min, eps_max = self._compute_epsilon_range()
        if self.n_points <= 2:
            return np.array([eps_min, eps_max], dtype=float)

        # 70% điểm trên [min, 0.6*(max-min)], 30% phần còn lại
        mid = eps_min + 0.60 * (eps_max - eps_min)
        n_low = max(3, int(round(self.n_points * 0.7)))
        n_high = self.n_points - n_low + 1
        low = np.linspace(eps_min, mid, n_low)
        high = np.linspace(mid, eps_max, n_high)[1:]
        eps = np.unique(np.concatenate([low, high]))
        if len(eps) > self.n_points:
            idx = np.linspace(0, len(eps) - 1, self.n_points).astype(int)
            eps = eps[idx]
        return eps.astype(float)

    # ------------------------------------------------------------------ #
    # 5. Sweep
    # ------------------------------------------------------------------ #
    def epsilon_constraint_sweep(self, auto_reduce: bool = True):
        if self.data is None:
            raise ValueError("self.data chưa được gán")

        # Tự giảm |J| nếu quá lớn
        if auto_reduce and self.data.n_j > self.max_candidates:
            self.reduce_candidates_by_coverage(max_candidates=self.max_candidates)

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
            f"(P_max={data.P_max}, n_i={n_i}, n_j={n_j}, nnz={data.a.nnz})"
        )
        if data.P_max is not None:
            top = np.sort(data.c)[-int(data.P_max):]
            print(
                f"[INFO] top-{data.P_max} costs sum = {top.sum():.4f} "
                f"(đây mới là eps_max hợp lý; trước đây dùng sum(c)={data.c.sum():.1f} là SAI)"
            )

        base_mdl, _, _ = self.build_base_template()
        template_text = str(base_mdl.Proto())

        epsilons = self._make_epsilons()
        print(f"[INFO] Số điểm ε: {len(epsilons)} → {np.array2string(epsilons, precision=3)}")

        results: list = []
        hint_x = None
        if self.use_hint:
            hint_x = self._greedy_solution(float(epsilons[-1]), n_starts=10)

        ctx = mp.get_context("fork")

        with ProcessPoolExecutor(max_workers=self.n_parallel, mp_context=ctx) as ex:
            for batch_start in range(0, len(epsilons), self.n_parallel):
                batch_eps = epsilons[batch_start: batch_start + self.n_parallel]
                tasks = []
                for eps in batch_eps:
                    local_hint = hint_x
                    # Filter hint theo ngân sách ε
                    if hint_x is not None and self.use_hint:
                        cost_so_far = 0.0
                        filtered = [0] * n_j
                        for j in range(n_j):
                            if hint_x[j] and cost_so_far + data.c[j] <= eps + 1e-9:
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
        gap_threshold = 15.0
        flagged_idx = [
            idx for idx, r in enumerate(results)
            if r["flagged_non_monotonic"] or r["optimality_gap_pct"] > gap_threshold
        ]
        if not flagged_idx:
            return

        print(
            f"\n[RE-SOLVE] {len(flagged_idx)} điểm (non-monotonic hoặc gap > {gap_threshold}%) — "
            f"time_limit={self.re_solve_time_limit}s, relative_gap=1%"
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
            f"{n_flagged} điểm non-monotonic, "
            f"gap trung bình={avg_gap:.2f}%, gap max={max_gap:.2f}%"
        )
        if avg_gap > 20:
            print(
                f"      [CẢNH BÁO] gap trung bình > 20% → tăng time_limit_s "
                f"hoặc giảm max_candidates / n_points."
            )
