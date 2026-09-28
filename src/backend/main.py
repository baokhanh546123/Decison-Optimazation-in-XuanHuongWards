from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# backend/main.py → parents[1] = src/; parents[2] = project root
BACKEND_DIR = Path(__file__).resolve().parent
SRC_DIR = BACKEND_DIR.parent
ROOT_DIR = SRC_DIR.parent
FRONTEND_DIR = SRC_DIR / "frontend"
TEMPLE_DIR = FRONTEND_DIR / "temple"
ASSET_DIR = FRONTEND_DIR / "asset"
STATIC_DIR = FRONTEND_DIR / "static"
JS_DIR = FRONTEND_DIR / "js"
DATA_DIR = ROOT_DIR / "data"
CLEAN_GEOJSON = DATA_DIR / "Xuanhuongward" / "XuanHuongWarsFeaturesClean.geojson"
FEATURED_GEOJSON = DATA_DIR / "Xuanhuongward" / "Xuan Huong Wards_featured.geojson"
RUNNER_HTML = TEMPLE_DIR / "runner.html"

# taxonomy_config = source of truth for p_i weights + coverage radius (pre-solve)
try:
    from dataclass.taxonomy_config import DEFAULT_TAXONOMY_CONFIG
except ImportError:  # pragma: no cover
    from backend.dataclass.taxonomy_config import DEFAULT_TAXONOMY_CONFIG  # type: ignore

TAX_CFG = DEFAULT_TAXONOMY_CONFIG

# UI chip aliases only (optional display names) — NOT a filter whitelist
UI_ALIAS = {
    "lodging": "accommodation",
    "health_care": "health_and_medicine",
}

app = FastAPI(
    title="MCLP Decision Optimization API",
    description="Backend for Maximal Covering Location Problem — Xuan Huong Wards.",
    version="1.4.0",
)


def _resolve_geojson() -> Path | None:
    if CLEAN_GEOJSON.is_file():
        return CLEAN_GEOJSON
    if FEATURED_GEOJSON.is_file():
        return FEATURED_GEOJSON
    return None


def _weight(root: str) -> float:
    return float(TAX_CFG.taxonomy_root_weight.get(root, TAX_CFG.default_root_weight))


def _radius_m(root: str) -> float:
    return float(TAX_CFG.taxonomy_root_radius_m.get(root, TAX_CFG.default_radius_m))


def _ui_tax(root: str) -> str:
    """Keep original root; only alias lodging/health_care for the 3 main chips."""
    return UI_ALIAS.get(root, root)


def _load_geopandas(path: Path, min_confidence: float):
    import geopandas as gpd
    import pandas as pd

    gdf = gpd.read_file(path)
    if "taxonomy_root" not in gdf.columns:
        raise ValueError("GeoJSON missing taxonomy_root")

    roots_all = sorted(gdf["taxonomy_root"].dropna().astype(str).unique().tolist())

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
        if not root:
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


def _load_json(path: Path, min_confidence: float):
    with path.open(encoding="utf-8") as f:
        fc = json.load(f)

    by_root: dict[str, list[dict[str, Any]]] = {}
    counts_full: dict[str, int] = {}
    roots_set: set[str] = set()

    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        root = props.get("taxonomy_root")
        if not root:
            continue
        root = str(root)
        roots_set.add(root)
        try:
            conf = float(props.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        lng = lat = None
        if geom.get("type") == "Point" and len(coords) >= 2:
            lng, lat = coords[0], coords[1]
        name = props.get("names") or "Unnamed"
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()[:80] or "Unnamed"
        addr = props.get("address_freeform") or ""
        if not isinstance(addr, str):
            addr = ""
        item = {
            "id": str(props.get("id") or "")[:36],
            "name": name,
            "taxonomy": _ui_tax(root),
            "taxonomy_root": root,
            "confidence": round(conf, 4),
            "weight": _weight(root),
            "radius_m": _radius_m(root),
            "lng": lng,
            "lat": lat,
            "address": addr[:60],
            "primary": props.get("taxonomy_primary") or props.get("basic_category") or "",
        }
        by_root.setdefault(root, []).append(item)
        counts_full[root] = counts_full.get(root, 0) + 1

    return by_root, counts_full, sorted(roots_set)


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
        "geojson_exists": path is not None,
        "geojson_path": str(path) if path else None,
        "routes": {"landing": "/", "runner": "/run", "candidates": "/api/candidates"},
    }


@app.get("/api/candidates")
async def api_candidates(
    per_tax: int = Query(40, ge=1, le=200, description="Max candidates per taxonomy_root"),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Override taxonomy_config.min_confidence"
    ),
) -> JSONResponse:
    """Load places from Clean GeoJSON; attach weight/radius from taxonomy_config.

    Does NOT filter to a 3-item whitelist — every taxonomy_root in the file is returned
    (top-N by confidence per root). Weights update p_i before the solver runs.
    """
    path = _resolve_geojson()
    if path is None:
        return JSONResponse(
            status_code=404,
            content={"error": "GeoJSON not found", "tried": [str(CLEAN_GEOJSON), str(FEATURED_GEOJSON)]},
        )

    conf_cut = TAX_CFG.min_confidence if min_confidence is None else min_confidence

    try:
        try:
            by_root, counts_full, roots_all = _load_geopandas(path, conf_cut)
            engine = "geopandas"
        except ImportError:
            by_root, counts_full, roots_all = _load_json(path, conf_cut)
            engine = "json"
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc), "path": str(path)})

    candidates: list[dict[str, Any]] = []
    for root, items in by_root.items():
        items.sort(key=lambda x: -x["confidence"])
        candidates.extend(items[:per_tax])

    for i, c in enumerate(candidates, 1):
        c["uid"] = f"C-{i:03d}"

    return JSONResponse(
        content={
            "source": str(path.relative_to(ROOT_DIR)) if str(path).startswith(str(ROOT_DIR)) else str(path),
            "engine": engine,
            "min_confidence": conf_cut,
            "taxonomy_root_unique": roots_all,
            "taxonomy_weights": dict(TAX_CFG.taxonomy_root_weight),
            "taxonomy_radius_m": dict(TAX_CFG.taxonomy_root_radius_m),
            "counts_full": counts_full,
            "candidates": candidates,
        }
    )


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
