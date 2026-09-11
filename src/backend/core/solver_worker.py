from __future__ import annotations
from typing import NamedTuple, Optional, Sequence
from ortools.sat.python import cp_model
import numpy as np

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

def solve_one_epsilon(task: EpsilonTask) -> Optional[dict]:
    """Chạy trong process con. Nhận text proto (parse_text_format, không dùng
    SerializeToString — khớp với API OR-Tools 9.15.x đã verify trong dự án)."""
    mdl = cp_model.CpModel()
    mdl.Proto().parse_text_format(task.template_proto_text)

    x = [mdl.GetBoolVarFromProtoIndex(j) for j in range(task.n_j)]
    y = [mdl.GetBoolVarFromProtoIndex(task.n_j + i) for i in range(task.n_i)]

    scale = task.scale
    c_int = np.round(np.asarray(task.c) * scale).astype(np.int64)
    p_int = np.round(np.asarray(task.p) * scale).astype(np.int64)
    eps_int = int(round(task.eps * scale))

    mdl.Add(sum(int(c_int[j]) * x[j] for j in range(task.n_j)) <= eps_int)
    mdl.Maximize(sum(int(p_int[i]) * y[i] for i in range(task.n_i)))

    if task.hint_x is not None:
        for j in range(task.n_j):
            mdl.AddHint(x[j], int(task.hint_x[j]))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = task.time_limit_s
    solver.parameters.num_search_workers = task.num_search_workers
    solver.parameters.relative_gap_limit = task.relative_gap
    solver.parameters.cp_model_presolve = True
    solver.parameters.linearization_level = 2
    status = solver.Solve(mdl)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    x_sol = [solver.Value(x[j]) for j in range(task.n_j)]
    chosen = [j for j in range(task.n_j) if x_sol[j]]
    f1 = float(sum(task.p[i] for i in range(task.n_i) if solver.Value(y[i])))
    f2 = float(sum(task.c[j] for j in chosen))
    obj = solver.ObjectiveValue()
    bound = solver.BestObjectiveBound()
    gap_pct = abs(bound - obj) / max(abs(obj), 1e-9) * 100.0

    return {
        "epsilon": float(task.eps),
        "f1_covering_profit": f1,
        "f2_cost": f2,
        "n_facilities": len(chosen),
        "chosen_candidates": chosen,
        "status": solver.StatusName(status),
        "optimality_gap_pct": gap_pct,
        "solve_time_s": solver.WallTime(),
        "x_solution": x_sol,
    }