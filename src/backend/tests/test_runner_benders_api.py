"""Test tích hợp Benders <-> runner.html: service + endpoint /api/optimize.

Chạy từ src/backend:  PYTHONPATH=. pytest tests/test_runner_benders_api.py -q
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import runner_service as rs
from api.runner_schemas import RunnerOptimizeRequest
from main import app


def _toy():
    """4 candidate, demand nằm sát từng candidate -> nghiệm tối ưu tính tay được."""
    lookup = {f"C-{i}": {"uid": f"C-{i}", "name": f"cand{i}", "confidence": 0.9,
                         "lng": 108.44 + i * 0.01, "lat": 11.93} for i in range(1, 5)}
    demand = pd.DataFrame({
        "lon": [108.45, 108.46, 108.47, 108.48, 108.45],
        "lat": [11.93] * 5,
        "taxonomy_root": ["food_and_drink"] * 5,
        "confidence": [1.0] * 5,
    })
    return lookup, demand


def test_build_problem_shapes_and_filters():
    lookup, demand = _toy()
    lookup["C-4"]["confidence"] = 0.4
    req = RunnerOptimizeRequest(candidates=["C-1", "C-2", "C-3", "C-4", "C-1"], min_confidence=0.5, P_max=2,
                                taxonomy_root={"food_and_drink": {"radius_m": 200, "weight": 2.0}})
    mclp, sel, meta = rs.build_problem(req, lookup=lookup, demand=demand, cost=np.array([1.0, 2.0, 1.0]))
    assert [c["uid"] for c in sel] == ["C-1", "C-2", "C-3"]          # C-4 rớt confidence, C-1 trùng bị bỏ
    assert meta["dropped_by_confidence"] == ["C-4"]
    assert mclp.a.shape == (5, 3) and mclp.P_max == 2
    assert np.allclose(mclp.p, 2.0)                                    # weight override × confidence
    assert mclp.a.nnz > 0


def test_unknown_uid_and_empty_selection():
    lookup, demand = _toy()
    with pytest.raises(rs.RunnerInputError):
        rs.build_problem(RunnerOptimizeRequest(candidates=["X"]), lookup=lookup, demand=demand)
    lookup["C-1"]["confidence"] = 0.1
    with pytest.raises(rs.RunnerInputError):
        rs.build_problem(RunnerOptimizeRequest(candidates=["C-1"], min_confidence=0.9), lookup=lookup, demand=demand)


def test_demand_threshold_masks_coverage():
    lookup, demand = _toy()
    demand.loc[0, "confidence"] = 0.35                                 # p thấp nhưng vẫn ≥ min_confidence của demand (0.3)
    base = RunnerOptimizeRequest(candidates=["C-1", "C-2"], P_max=1)
    m0, _, _ = rs.build_problem(base, lookup=lookup, demand=demand, cost=np.ones(2))
    thr = RunnerOptimizeRequest(candidates=["C-1", "C-2"], P_max=1, per_candidate={"C-1": {"demand": 0.5, "conf": 0}})
    m1, _, _ = rs.build_problem(thr, lookup=lookup, demand=demand, cost=np.ones(2))
    assert m0.a[:, 0].sum() == 2 and m1.a[:, 0].sum() == 1               # demand p=0.35 < 0.5×max(p) bị loại khỏi C-1
    assert m1.a[:, 1].sum() == m0.a[:, 1].sum()                        # candidate khác không bị ảnh hưởng


def test_run_benders_toy_is_exact():
    lookup, demand = _toy()
    req = RunnerOptimizeRequest(candidates=list(lookup), P_max=2, n_points=5, time_limit_s=10,
                                benders_max_iters=50, benders_master_time_limit_s=2,
                                taxonomy_root={"food_and_drink": {"radius_m": 800, "weight": 1.0}})
    out = rs.run_benders(req, lookup=lookup, demand=demand, cost=np.array([1.0, 1.0, 2.0, 2.0]))
    pts = out["points"]
    assert pts and out["algorithm"] == "benders"
    f1 = [q["f1_covering_profit"] for q in pts]
    assert f1 == sorted(f1)                                            # f1 không giảm khi ε tăng
    assert sum(q["is_recommended"] for q in pts) == 1
    assert all(len(q["chosen_uids"]) == q["n_facilities"] for q in pts)
    assert max(f1) <= out["meta"]["total_profit"] + 1e-6


def test_api_flow_end_to_end():
    client = TestClient(app)
    assert client.get("/health").json()["algorithm"] == "benders"
    assert client.post("/api/optimize", json={"candidates": ["NOPE"]}).status_code == 422
    assert client.get("/api/jobs/doesnotexist").status_code == 404

    uids = list(rs.candidate_lookup())[:10]
    body = {"candidates": uids, "min_confidence": 0.5, "P_max": 3, "n_points": 4, "time_limit_s": 10,
            "benders_max_iters": 30, "benders_master_time_limit_s": 2, "lambda": [70, 30],
            "taxonomy_root": {"food_and_drink": {"radius_m": 250, "weight": 1.0}}}
    with client:
        r = client.post("/api/optimize", json=body)
        assert r.status_code == 202
        jid = r.json()["job_id"]
        for _ in range(240):
            j = client.get(f"/api/jobs/{jid}").json()
            if j["state"] in ("done", "failed"):
                break
            time.sleep(0.5)
    assert j["state"] == "done", j.get("error")
    assert j["result"]["points"] and j["result"]["recommended_index"] is not None


def test_map_endpoints_use_visualize_package():
    """Section 2 của runner: bản đồ pydeck (html) + ảnh tĩnh (jpeg) dựng bằng package visualize."""
    pytest.importorskip("pydeck")
    pytest.importorskip("matplotlib")
    client = TestClient(app)
    uids = list(rs.candidate_lookup())[:8]
    body = {"candidates": uids, "min_confidence": 0.5, "P_max": 3, "n_points": 4, "time_limit_s": 10,
            "benders_max_iters": 30, "benders_master_time_limit_s": 2}
    with client:
        jid = client.post("/api/optimize", json=body).json()["job_id"]
        for _ in range(240):
            j = client.get(f"/api/jobs/{jid}").json()
            if j["state"] in ("done", "failed"):
                break
            time.sleep(0.5)
        assert j["state"] == "done", j.get("error")
        rid = j["result"]["run_id"]
        n_pts = len(j["result"]["points"])

        r = client.get(f"/api/runs/{rid}/map.html", params={"mode": "heatmap"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert "deck-container" in r.text and "HeatmapLayer" in r.text
        r = client.get(f"/api/runs/{rid}/map.html", params={"mode": "dot", "point": 0})
        assert r.status_code == 200 and "IconLayer" in r.text
        r = client.get(f"/api/runs/{rid}/map.jpg")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
        r = client.get(f"/api/runs/{rid}/map.jpg", params={"point": n_pts - 1})
        assert r.status_code == 200

        assert client.get(f"/api/runs/{rid}/map.html", params={"mode": "bogus"}).status_code == 422
        assert client.get(f"/api/runs/{rid}/map.jpg", params={"point": n_pts + 5}).status_code == 422
        assert client.get("/api/runs/khongco/map.jpg").status_code == 404
