from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parent
# các package nội bộ (api/, core/, model/, dataclass/...) import theo kiểu `from api.x import ...`
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
SRC_DIR = BACKEND_DIR.parent
ROOT_DIR = SRC_DIR.parent
FRONTEND_DIR = SRC_DIR / "frontend"
TEMPLE_DIR = FRONTEND_DIR / "temple"
ASSET_DIR = FRONTEND_DIR / "asset"
STATIC_DIR = FRONTEND_DIR / "static"
JS_DIR = FRONTEND_DIR / "js"
DATA_DIR = ROOT_DIR / "data"
CLEAN_GEOJSON = DATA_DIR / "Xuanhuongward" / "XuanHuongWarsFeaturesClean.geojson"
PRECOMPUTED = STATIC_DIR / "candidates.json"
PRECOMPUTED_ALT = STATIC_DIR / "candidates_xuanhuong.json"
RUNNER_HTML = TEMPLE_DIR / "runner.html"

try:
    from dataclass.taxonomy_config import DEFAULT_TAXONOMY_CONFIG
except ImportError:  # pragma: no cover
    from backend.dataclass.taxonomy_config import DEFAULT_TAXONOMY_CONFIG  # type: ignore

from api.jobs import JobManager  # noqa: E402
from api.runner_schemas import RunnerOptimizeRequest  # noqa: E402
from api import runner_maps, runner_service  # noqa: E402

TAX_CFG = DEFAULT_TAXONOMY_CONFIG
# Benders giải nhiều điểm ε song song trong 1 job -> chỉ cho 1 job chạy cùng lúc để không quá tải CPU
job_manager = JobManager(max_concurrent_solves=1)
UI_ALIAS = {"lodging": "accommodation", "health_care": "health_and_medicine"}

app = FastAPI(
    title="MCLP Decision Optimization API",
    description="Backend for Maximal Covering Location Problem — Xuan Huong Wards.",
    version="1.5.0",
)


def _weight(root: str) -> float:
    return float(TAX_CFG.taxonomy_root_weight.get(root, TAX_CFG.default_root_weight))


def _radius_m(root: str) -> float:
    return float(TAX_CFG.taxonomy_root_radius_m.get(root, TAX_CFG.default_radius_m))


def _ui_tax(root: str) -> str:
    return UI_ALIAS.get(root, root)


def _resolve_geojson() -> Path | None:
    if CLEAN_GEOJSON.is_file():
        return CLEAN_GEOJSON
    return None


def _precomputed_path() -> Path | None:
    if PRECOMPUTED.is_file():
        return PRECOMPUTED
    if PRECOMPUTED_ALT.is_file():
        return PRECOMPUTED_ALT
    return None


def _from_precomputed(per_tax: int, min_confidence: float) -> dict[str, Any] | None:
    path = _precomputed_path()
    if path is None:
        return None
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    by: dict[str, list] = {}
    for c in data.get("candidates") or []:
        conf = float(c.get("confidence") or 0)
        if conf < min_confidence:
            continue
        root = str(c.get("taxonomy_root") or c.get("taxonomy") or "")
        if not root or root == "nan":
            continue
        by.setdefault(root, []).append(c)
    cands: list[dict[str, Any]] = []
    for root, items in by.items():
        items.sort(key=lambda x: -float(x.get("confidence") or 0))
        for c in items[:per_tax]:
            c = dict(c)
            c["weight"] = _weight(root)
            c["radius_m"] = _radius_m(root)
            c["taxonomy"] = _ui_tax(root)
            cands.append(c)
    for i, c in enumerate(cands, 1):
        c["uid"] = f"C-{i:03d}"
    chips = sorted({c["taxonomy"] for c in cands})
    return {
        "source": str(path.name),
        "engine": "precomputed",
        "min_confidence": min_confidence,
        "taxonomy_root_unique": data.get("taxonomy_root_unique") or sorted(by.keys()),
        "chips": chips,
        "counts_full": data.get("counts_full") or {k: len(v) for k, v in by.items()},
        "candidates": cands,
    }


def _load_geopandas(path: Path, min_confidence: float):
    import geopandas as gpd
    import pandas as pd

    gdf = gpd.read_file(path)
    roots_all = sorted(
        [r for r in gdf["taxonomy_root"].dropna().astype(str).unique().tolist() if r and r != "nan"]
    )
    gdf = gdf.copy()
    if "confidence" in gdf.columns:
        gdf["confidence"] = pd.to_numeric(gdf["confidence"], errors="coerce").fillna(0.0)
        gdf = gdf[gdf["confidence"] >= min_confidence]
    gdf = gdf[gdf.geometry.notna()]

    def _xy(geom):
        if geom is None or geom.is_empty:
            return None, None
        if geom.geom_type == "Point":
            return float(geom.x), float(geom.y)
        p = geom.representative_point()
        return float(p.x), float(p.y)

    xy = gdf.geometry.apply(_xy)
    gdf["lng"] = [t[0] for t in xy]
    gdf["lat"] = [t[1] for t in xy]
    gdf = gdf[gdf["lng"].notna()]

    by_root: dict[str, list[dict[str, Any]]] = {}
    counts_full: dict[str, int] = {}
    for _, row in gdf.iterrows():
        root = str(row.get("taxonomy_root") or "")
        if not root or root == "nan":
            continue
        conf = float(row.get("confidence") or 0.0)
        name = row.get("names") or "Unnamed"
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()[:80] or "Unnamed"
        addr = row.get("address_freeform") or ""
        if not isinstance(addr, str):
            addr = ""
        item = {
            "id": str(row.get("id") or "")[:36],
            "name": name,
            "taxonomy": _ui_tax(root),
            "taxonomy_root": root,
            "confidence": round(conf, 4),
            "weight": _weight(root),
            "radius_m": _radius_m(root),
            "lng": float(row["lng"]),
            "lat": float(row["lat"]),
            "address": addr[:60],
            "primary": str(row.get("taxonomy_primary") or row.get("basic_category") or ""),
        }
        by_root.setdefault(root, []).append(item)
        counts_full[root] = counts_full.get(root, 0) + 1
    return by_root, counts_full, roots_all


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/temple/index.html", status_code=302)


@app.get("/run", include_in_schema=False)
async def run_runner() -> RedirectResponse:
    return RedirectResponse(url="/temple/runner.html", status_code=302)


@app.get("/health")
async def health() -> dict[str, Any]:
    path = _resolve_geojson()
    return {
        "status": "ok",
        "precomputed": _precomputed_path() is not None,
        "geojson_exists": path is not None,
        "routes": {
            "landing": "/",
            "runner": "/run",
            "candidates": "/api/candidates",
            "candidates_static": "/static/candidates.json",
            "optimize": "POST /api/optimize",
            "job": "GET /api/jobs/{job_id}",
            "map_html": "GET /api/runs/{run_id}/map.html?mode=heatmap|dot&point=k",
            "map_jpeg": "GET /api/runs/{run_id}/map.jpg?point=k",
        },
        "algorithm": "benders",
    }


@app.get("/api/candidates")
async def api_candidates(
    per_tax: int = Query(40, ge=1, le=200),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
) -> JSONResponse:
    """Prefer static precomputed JSON (~150KB); else geopandas on Clean GeoJSON.

    Returns ALL taxonomy_roots with weight/radius from taxonomy_config.
    """
    conf_cut = TAX_CFG.min_confidence if min_confidence is None else min_confidence

    fast = _from_precomputed(per_tax, conf_cut)
    if fast is not None:
        return JSONResponse(content=fast)

    path = _resolve_geojson()
    if path is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "No precomputed JSON and GeoJSON missing",
                "tried": [str(PRECOMPUTED), str(PRECOMPUTED_ALT), str(CLEAN_GEOJSON)],
            },
        )

    try:
        by_root, counts_full, roots_all = _load_geopandas(path, conf_cut)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})

    candidates: list[dict[str, Any]] = []
    for root, items in by_root.items():
        items.sort(key=lambda x: -x["confidence"])
        candidates.extend(items[:per_tax])
    for i, c in enumerate(candidates, 1):
        c["uid"] = f"C-{i:03d}"
    chips = sorted({c["taxonomy"] for c in candidates})

    return JSONResponse(
        content={
            "source": str(path),
            "engine": "geopandas",
            "min_confidence": conf_cut,
            "taxonomy_root_unique": roots_all,
            "chips": chips,
            "counts_full": counts_full,
            "candidates": candidates,
        }
    )


def _job_payload(rec) -> dict[str, Any]:
    end = rec.finished_at or time.time()
    elapsed = (end - rec.started_at) if rec.started_at else 0.0
    err = None
    if rec.error:
        err = rec.error.strip().splitlines()[0][:400]
    return {
        "job_id": rec.job_id,
        "state": rec.state,  # queued | running | done | failed
        "created_at": rec.created_at,
        "started_at": rec.started_at,
        "finished_at": rec.finished_at,
        "elapsed_s": round(elapsed, 2),
        "error": err,
        "result": rec.results if rec.state == "done" else None,
    }


@app.post("/api/optimize", status_code=202)
async def api_optimize(req: RunnerOptimizeRequest) -> dict[str, Any]:
    """Chạy ε-constraint sweep bằng Benders Decomposition cho các candidate đã chọn ở runner.html.

    Trả về job_id ngay; client poll GET /api/jobs/{job_id}.
    """
    lookup = runner_service.candidate_lookup()
    unknown = [u for u in req.candidates if u not in lookup]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Candidate không tồn tại: {', '.join(unknown[:5])}")
    job_id = await job_manager.submit(0, lambda: runner_service.run_benders(req))
    return {"job_id": job_id, "state": "queued"}


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    rec = await job_manager.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    return _job_payload(rec)


@app.get("/api/jobs")
async def api_jobs(limit: int = Query(10, ge=1, le=50)) -> list[dict[str, Any]]:
    return [{**_job_payload(r), "result": None} for r in await job_manager.list_recent(limit)]



def _render_map(run_id: str, kind: str, mode: str, point: int | None) -> FileResponse:
    """Dựng bản đồ bằng package visualize (blocking -> endpoint khai báo `def` để chạy trong threadpool)."""
    try:
        path = runner_maps.render(run_id, kind, mode=mode, point=point)
    except KeyError:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần chạy (server đã khởi động lại hoặc đã bị dọn cache). Hãy chạy tối ưu lại.")
    except runner_maps.MapInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except runner_maps.MapUnavailable as exc:
        raise HTTPException(status_code=501, detail=f"Thiếu thư viện vẽ trên server: {exc}. Chạy: pip install pydeck matplotlib")
    media = "text/html; charset=utf-8" if kind == "html" else "image/jpeg"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store"})


@app.get("/api/runs/{run_id}/map.html", include_in_schema=False)
def api_run_map_html(run_id: str, mode: str = Query("heatmap"), point: int | None = Query(None, ge=0)) -> FileResponse:
    return _render_map(run_id, "html", mode, point)


@app.get("/api/runs/{run_id}/map.jpg", include_in_schema=False)
def api_run_map_jpg(run_id: str, point: int | None = Query(None, ge=0)) -> FileResponse:
    return _render_map(run_id, "jpeg", "-", point)


if ASSET_DIR.is_dir():
    app.mount("/asset", StaticFiles(directory=str(ASSET_DIR)), name="asset")
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if JS_DIR.is_dir():
    app.mount("/js", StaticFiles(directory=str(JS_DIR)), name="js")
if TEMPLE_DIR.is_dir():
    app.mount("/temple", StaticFiles(directory=str(TEMPLE_DIR), html=True), name="temple")


if __name__ == "__main__":
    import random
    import uvicorn

    port_random = random.randint(3000, 9999)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port_random,
        reload=True,
        reload_dirs=[str(BACKEND_DIR), str(FRONTEND_DIR)],
    )
