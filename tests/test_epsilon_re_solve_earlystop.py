"""
Test cơ chế early-stop + re-solve của MO-MCLP ε-constraint.

So với notebook (Optimization_fixed.ipynb):
  - Notebook: early-stop CHỈ ở tầng CP-SAT (relative_gap_limit + time_limit).
    Không có re-solve sau sweep; chỉ gắn flagged_non_monotonic + cảnh báo gap.
  - GitHub Optimization:
      (1) per-solve early-stop  = relative_gap  (giống notebook)
      (2) sweep early-stop      = f1 plateau (early_stop / patience) — bổ sung
      (3) re_solve_flagged      = re-solve điểm non-monotonic / gap cao — bổ sung

Chạy:
  cd src && python -m pytest ../tests/test_epsilon_re_solve_earlystop.py -v
  # hoặc từ root (cần PYTHONPATH=src):
  PYTHONPATH=src pytest tests/test_epsilon_re_solve_earlystop.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from scipy import sparse

# --- path: repo/src trên sys.path ---
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# backend package layout: dataclass / model / core under src/backend or src
BACKEND = SRC / "backend"
if BACKEND.is_dir() and str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dataclass.MCLP import MCLP_Data  # noqa: E402
from model.optimization import Optimization  # noqa: E402
from core.solver_worker import EpsilonTask, _configure_solver  # noqa: E402
from ortools.sat.python import cp_model  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: bài MCLP nhỏ (deterministic)
# ---------------------------------------------------------------------------
@pytest.fixture
def tiny_mclp() -> MCLP_Data:
    """3 demand, 4 candidate, P_max=2 — đủ nhỏ để CP-SAT giải tức thì."""
    # a: demand i covered by candidates
    # i0 <- j0,j1
    # i1 <- j1,j2
    # i2 <- j2,j3
    rows = [0, 0, 1, 1, 2, 2]
    cols = [0, 1, 1, 2, 2, 3]
    data = np.ones(len(rows), dtype=np.int8)
    a = sparse.csr_matrix((data, (rows, cols)), shape=(3, 4))
    p = np.array([5.0, 3.0, 4.0], dtype=np.float64)
    c = np.array([1.0, 1.5, 1.2, 2.0], dtype=np.float64)
    return MCLP_Data(p=p, a=a, c=c, P_max=2)


class _InlineExecutor:
    """Executor giả chạy tuần tự trong cùng process (không fork subprocess thật).

    Lý do cần: unittest.mock.patch("model.optimization.solve_one_epsilon", ...)
    tạo ra một MagicMock. Khi sweep thật chạy qua ProcessPoolExecutor, OR-Tools/
    concurrent.futures phải pickle callable đó để gửi sang worker process —
    MagicMock không pickle được ổn định giữa các process
    (PicklingError: "Can't pickle <class 'unittest.mock.MagicMock'>: it's not
    the same object as unittest.mock.MagicMock"). Logic cần test ở đây
    (plateau counting / early-stop) là code điều khiển luồng thuần Python phía
    process cha, không phải bản thân CP-SAT solve, nên chạy tuần tự trong cùng
    process là đủ và tránh được lỗi pickling không liên quan tới thứ đang test.
    """
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def map(self, fn, iterable):
        return [fn(item) for item in iterable]


def _fake_result(eps: float, f1: float, gap: float = 1.0, n_j: int = 4) -> dict:
    return {
        "epsilon": float(eps),
        "f1_covering_profit": float(f1),
        "f2_cost": 1.0,
        "n_facilities": 1,
        "chosen_candidates": [0],
        "status": "OPTIMAL",
        "optimality_gap_pct": float(gap),
        "solve_time_s": 0.01,
        "x_solution": [1, 0, 0, 0][:n_j] + [0] * max(0, n_j - 4),
    }


# ---------------------------------------------------------------------------
# 1) Per-solve early-stop (giống notebook): relative_gap_limit
# ---------------------------------------------------------------------------
def test_configure_solver_sets_relative_gap_and_time_limit():
    """Notebook early-stop = CP-SAT relative_gap_limit + max_time_in_seconds."""
    solver = cp_model.CpSolver()
    _configure_solver(solver, time_limit_s=12.5, num_search_workers=2, relative_gap=0.03)
    assert solver.parameters.max_time_in_seconds == pytest.approx(12.5)
    assert solver.parameters.num_search_workers == 2
    assert solver.parameters.relative_gap_limit == pytest.approx(0.03)


def test_epsilon_task_carries_relative_gap(tiny_mclp):
    task = EpsilonTask(
        template_proto_text="",
        n_i=tiny_mclp.n_i,
        n_j=tiny_mclp.n_j,
        c=tiny_mclp.c,
        p=tiny_mclp.p,
        eps=1.0,
        time_limit_s=30,
        num_search_workers=1,
        relative_gap=0.05,
        hint_x=None,
        scale=10**6,
    )
    assert task.relative_gap == 0.05


# ---------------------------------------------------------------------------
# 2) Sweep-level early-stop (f1 plateau)
# ---------------------------------------------------------------------------
def test_sweep_early_stop_on_f1_plateau(tiny_mclp):
    """Khi f1 không tăng qua early_stop_patience điểm → dừng, ít hơn n_points."""
    opt = Optimization(
        data=tiny_mclp,
        n_points=8,
        time_limit_s=5,
        relative_gap=0.05,
        n_parallel=1,
        workers_per_solve=1,
        use_hint=False,
        re_solve_flagged=False,
        early_stop=True,
        early_stop_patience=2,
        early_stop_tol=1e-6,
        eps_mode="tight",
    )

    # f1 tăng 1 lần rồi plateau → early-stop sau patience=2
    sequence = [
        _fake_result(0.5, 5.0),
        _fake_result(1.0, 8.0),   # improve
        _fake_result(1.5, 8.0),   # plateau 1
        _fake_result(2.0, 8.0),   # plateau 2 → stop
        _fake_result(2.5, 8.0),
        _fake_result(3.0, 8.0),
        _fake_result(3.5, 8.0),
        _fake_result(4.0, 8.0),
    ]
    it = iter(sequence)

    def fake_solve(task):
        return next(it)

    with patch("model.optimization.solve_one_epsilon", side_effect=fake_solve), \
         patch("model.optimization.ProcessPoolExecutor", _InlineExecutor):
        results = opt.epsilon_constraint_sweep(auto_reduce=False)

    # Không giải hết 8 điểm
    assert len(results) < 8
    assert len(results) >= 3  # ít nhất đến khi plateau đủ patience
    f1s = [r["f1_covering_profit"] for r in results]
    assert max(f1s) == pytest.approx(8.0)


def test_sweep_no_early_stop_when_disabled(tiny_mclp):
    opt = Optimization(
        data=tiny_mclp,
        n_points=5,
        time_limit_s=5,
        n_parallel=1,
        workers_per_solve=1,
        use_hint=False,
        re_solve_flagged=False,
        early_stop=False,
        eps_mode="tight",
    )
    seq = [_fake_result(float(i), 3.0) for i in range(5)]
    it = iter(seq)

    with patch("model.optimization.solve_one_epsilon", side_effect=lambda t: next(it)), \
         patch("model.optimization.ProcessPoolExecutor", _InlineExecutor):
        results = opt.epsilon_constraint_sweep(auto_reduce=False)

    assert len(results) == 5


# ---------------------------------------------------------------------------
# 3) flagged_non_monotonic (có trong notebook phần cuối sweep)
# ---------------------------------------------------------------------------
def test_flag_non_monotonic_marks_drop_in_f1(tiny_mclp):
    opt = Optimization(data=tiny_mclp, re_solve_flagged=False, early_stop=False)
    results = [
        {"epsilon": 1.0, "f1_covering_profit": 10.0, "optimality_gap_pct": 1.0},
        {"epsilon": 2.0, "f1_covering_profit": 12.0, "optimality_gap_pct": 1.0},
        {"epsilon": 3.0, "f1_covering_profit": 11.0, "optimality_gap_pct": 1.0},  # drop
        {"epsilon": 4.0, "f1_covering_profit": 13.0, "optimality_gap_pct": 1.0},
    ]
    opt._flag_non_monotonic(results)
    assert results[0]["flagged_non_monotonic"] is False
    assert results[1]["flagged_non_monotonic"] is False
    assert results[2]["flagged_non_monotonic"] is True
    assert results[3]["flagged_non_monotonic"] is False


# ---------------------------------------------------------------------------
# 4) re_solve_flagged (GitHub bổ sung — notebook không có)
# ---------------------------------------------------------------------------
def test_re_solve_improves_high_gap_point(tiny_mclp):
    opt = Optimization(
        data=tiny_mclp,
        re_solve_flagged=True,
        re_solve_gap_threshold=20.0,
        re_solve_time_limit=10,
        workers_per_solve=1,
        early_stop=False,
    )
    results = [
        {
            "epsilon": 1.0,
            "f1_covering_profit": 5.0,
            "f2_cost": 1.0,
            "n_facilities": 1,
            "chosen_candidates": [0],
            "status": "FEASIBLE",
            "optimality_gap_pct": 50.0,  # > threshold
            "solve_time_s": 1.0,
            "flagged_non_monotonic": False,
        }
    ]

    improved = {
        "epsilon": 1.0,
        "f1_covering_profit": 8.0,
        "f2_cost": 1.0,
        "n_facilities": 1,
        "chosen_candidates": [0],
        "status": "OPTIMAL",
        "optimality_gap_pct": 2.0,
        "solve_time_s": 0.5,
        "x_solution": [1, 0, 0, 0],
    }

    with patch("model.optimization.solve_one_epsilon", return_value=improved):
        opt._resolve_flagged_points(
            results, template_text="dummy", n_i=3, n_j=4, best_hint=[1, 0, 0, 0]
        )

    assert results[0]["f1_covering_profit"] == pytest.approx(8.0)
    assert results[0]["optimality_gap_pct"] == pytest.approx(2.0)
    assert results[0]["flagged_non_monotonic"] is False


def test_re_solve_skips_when_no_flagged(tiny_mclp):
    opt = Optimization(data=tiny_mclp, re_solve_gap_threshold=20.0)
    results = [
        {
            "epsilon": 1.0,
            "f1_covering_profit": 5.0,
            "optimality_gap_pct": 1.0,
            "flagged_non_monotonic": False,
            "chosen_candidates": [0],
        }
    ]
    with patch("model.optimization.solve_one_epsilon") as mock_solve:
        opt._resolve_flagged_points(results, "dummy", 3, 4, None)
        mock_solve.assert_not_called()


# ---------------------------------------------------------------------------
# 5) Integration nhỏ: solve thật 1 điểm ε (optional, cần ortools)
# ---------------------------------------------------------------------------
def test_real_solve_one_epsilon_tiny(tiny_mclp):
    """Smoke: build template + solve 1 ε trên instance nhỏ."""
    opt = Optimization(
        data=tiny_mclp,
        n_points=3,
        time_limit_s=10,
        relative_gap=0.01,
        n_parallel=1,
        workers_per_solve=1,
        use_hint=True,
        re_solve_flagged=True,
        early_stop=True,
        early_stop_patience=3,
        eps_mode="tight",
    )
    results = opt.epsilon_constraint_sweep(auto_reduce=False)
    assert len(results) >= 1
    for r in results:
        assert "f1_covering_profit" in r
        assert "optimality_gap_pct" in r
        assert "flagged_non_monotonic" in r
        assert r["n_facilities"] <= 2
