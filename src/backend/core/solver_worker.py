from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

import numpy as np
from ortools.sat.python import cp_model


class EpsilonTask(NamedTuple):
    template_proto_text: str
    n_i: int
    n_j: int
    c: np.ndarray
    p: np.ndarray
    eps: float
    time_limit_s: float
    num_search_workers: int
    relative_gap: float
    hint_x: Optional[Sequence[int]]
    scale: int


def _configure_solver(
    solver: cp_model.CpSolver,
    time_limit_s: float,
    num_search_workers: int,
    relative_gap: float,
) -> None:
    """Bộ tham số CP-SAT hướng tới gap nhỏ trên bài binary covering."""
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = int(num_search_workers)
    solver.parameters.relative_gap_limit = float(relative_gap)

    # Presolve + LP relaxation mạnh
    solver.parameters.cp_model_presolve = True
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_probing_level = 2
    solver.parameters.symmetry_level = 2

    # Ưu tiên chứng minh bound hơn tìm nghiệm mới khi đã có solution tốt
    solver.parameters.optimize_with_core = True
    solver.parameters.use_optional_variables = False

    # Giảm nhiễu log
    solver.parameters.log_search_progress = False


def solve_one_epsilon(task: EpsilonTask) -> Optional[dict]:
    """Chạy trong process con.

    Nhận text proto (parse_text_format — tương thích OR-Tools 9.x đã verify).
    Trả về dict kết quả hoặc None nếu không tìm được nghiệm khả thi.
    """
    mdl = cp_model.CpModel()
    mdl.Proto().parse_text_format(task.template_proto_text)

    x = [mdl.GetBoolVarFromProtoIndex(j) for j in range(task.n_j)]
    y = [mdl.GetBoolVarFromProtoIndex(task.n_j + i) for i in range(task.n_i)]

    scale = task.scale
    c_arr = np.asarray(task.c, dtype=np.float64)
    p_arr = np.asarray(task.p, dtype=np.float64)

    c_int = np.round(c_arr * scale).astype(np.int64)
    p_int = np.round(p_arr * scale).astype(np.int64)
    eps_int = int(round(float(task.eps) * scale))

    # Ràng buộc ngân sách ε
    mdl.Add(sum(int(c_int[j]) * x[j] for j in range(task.n_j)) <= eps_int)

    # Mục tiêu: max covering profit
    mdl.Maximize(sum(int(p_int[i]) * y[i] for i in range(task.n_i)))

    # Warm-start hint (nếu có)
    if task.hint_x is not None and len(task.hint_x) == task.n_j:
        for j in range(task.n_j):
            mdl.AddHint(x[j], int(task.hint_x[j]))

    solver = cp_model.CpSolver()
    _configure_solver(
        solver,
        time_limit_s=task.time_limit_s,
        num_search_workers=task.num_search_workers,
        relative_gap=task.relative_gap,
    )

    status = solver.Solve(mdl)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    x_sol = [int(solver.Value(x[j])) for j in range(task.n_j)]
    chosen = [j for j in range(task.n_j) if x_sol[j]]
    f1 = float(sum(p_arr[i] for i in range(task.n_i) if solver.Value(y[i])))
    f2 = float(sum(c_arr[j] for j in chosen))

    obj = float(solver.ObjectiveValue())
    bound = float(solver.BestObjectiveBound())
    # Gap tương đối chuẩn MIP: |bound - obj| / max(|obj|, 1)
    denom = max(abs(obj), 1.0)
    gap_pct = abs(bound - obj) / denom * 100.0

    return {
        "epsilon": float(task.eps),
        "f1_covering_profit": f1,
        "f2_cost": f2,
        "n_facilities": len(chosen),
        "chosen_candidates": chosen,
        "status": solver.StatusName(status),
        "optimality_gap_pct": gap_pct,
        "solve_time_s": float(solver.WallTime()),
        "x_solution": x_sol,
    }
