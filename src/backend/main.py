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
# Real places dataset (cleaned) — same file as Colab notebook
CLEAN_GEOJSON = DATA_DIR / "Xuanhuongward" / "XuanHuongWarsFeaturesClean.geojson"
FEATURED_GEOJSON = DATA_DIR / "Xuanhuongward" / "Xuan Huong Wards_featured.geojson"
RUNNER_HTML = TEMPLE_DIR / "runner.html"

# GeoJSON taxonomy_root → UI filter chips in runner.html
TAXONOMY_MAP = {
    "food_and_drink": "food_and_drink",
    "lodging": "accommodation",
    "accommodation": "accommodation",
    "health_care": "health_and_medicine",
    "health_and_medicine": "health_and_medicine",
}

app = FastAPI(
    title="MCLP Decision Optimization API",
    description="Backend for Maximal Covering Location Problem — Xuan Huong Wards.",
    version="1.3.0",
)


def _resolve_geojson() -> Path | None:
    """Prefer cleaned places file; fall back to featured."""
    if CLEAN_GEOJSON.is_file():
        return CLEAN_GEOJSON
    if FEATURED_GEOJSON.is_file():
        return FEATURED_GEOJSON
    return None


def _load_candidates_geopandas(path: Path, min_confidence: float):
    """Read places with geopandas (real project data)."""
    import geopandas as gpd
    import pandas as pd

    gdf = gpd.read_file(path)
    if "taxonomy_root" not in gdf.columns:
        raise ValueError("GeoJSON missing taxonomy_root column")

    roots_all = sorted(gdf["taxonomy_root"].dropna().astype(str).unique().tolist())

    if "confidence" in gdf.columns:
        gdf = gdf.copy()
        gdf["confidence"] = pd.to_numeric(gdf["confidence"], errors="coerce").fillna(0.0)
        gdf = gdf[gdf["confidence"] >= min_confidence]

    # lon/lat from geometry (Point → x/y; others → representative_point)
    gdf = gdf[gdf.geometry.notna()].copy()

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

    by_tax: dict[str, list[dict[str, Any]]] = {
        "food_and_drink": [],
        "accommodation": [],
        "health_and_medicine": [],
    }
    counts_full: dict[str, int] = {k: 0 for k in by_tax}

    for _, row in gdf.iterrows():
        root = str(row.get("taxonomy_root") or "")
        if root not in TAXONOMY_MAP:
            continue
        ui_tax = TAXONOMY_MAP[root]
        counts_full[ui_tax] = counts_full.get(ui_tax, 0) + 1
        conf = float(row.get("confidence") or 0.0)
        name = row.get("names") or "Unnamed"
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()[:80] or "Unnamed"
        addr = row.get("address_freeform") or ""
        if not isinstance(addr, str):
            addr = ""
        by_tax[ui_tax].append(
            {
                "id": str(row.get("id") or "")[:36],
                "name": name,
                "taxonomy": ui_tax,
                "taxonomy_root": root,
                "confidence": round(conf, 4),
                "lng": float(row["lng"]),
                "lat": float(row["lat"]),
                "address": addr[:60],
                "primary": str(row.get("taxonomy_primary") or row.get("basic_category") or ""),
            }
        )

    return by_tax, counts_full, roots_all


def _load_candidates_json(path: Path, min_confidence: float):
    """Fallback without geopandas — pure JSON FeatureCollection."""
    with path.open(encoding="utf-8") as f:
        fc = json.load(f)

    roots_set: set[str] = set()
    by_tax: dict[str, list[dict[str, Any]]] = {
        "food_and_drink": [],
        "accommodation": [],
        "health_and_medicine": [],
    }
    counts_full: dict[str, int] = {k: 0 for k in by_tax}

    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        root = props.get("taxonomy_root")
        if root:
            roots_set.add(str(root))
        if root not in TAXONOMY_MAP:
            continue
        ui_tax = TAXONOMY_MAP[root]
        try:
            conf = float(props.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            continue
        counts_full[ui_tax] = counts_full.get(ui_tax, 0) + 1
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        if geom.get("type") == "Point":
            lng, lat = coords[0], coords[1]
        else:
            lng = lat = None
        name = props.get("names") or "Unnamed"
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()[:80] or "Unnamed"
        addr = props.get("address_freeform") or ""
        if not isinstance(addr, str):
            addr = ""
        by_tax[ui_tax].append(
            {
                "id": str(props.get("id") or "")[:36],
                "name": name,
                "taxonomy": ui_tax,
                "taxonomy_root": root,
                "confidence": round(conf, 4),
                "lng": lng,
                "lat": lat,
                "address": addr[:60],
                "primary": props.get("taxonomy_primary") or props.get("basic_category") or "",
            }
        )

    return by_tax, counts_full, sorted(roots_set)


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
        "frontend": str(FRONTEND_DIR),
        "index_exists": (TEMPLE_DIR / "index.html").is_file(),
        "runner_exists": RUNNER_HTML.is_file(),
        "geojson_exists": path is not None,
        "geojson_path": str(path) if path else None,
        "routes": {"landing": "/", "runner": "/run", "candidates": "/api/candidates"},
    }


@app.get("/api/candidates")
async def api_candidates(
    per_tax: int = Query(40, ge=1, le=200, description="Max candidates per UI taxonomy chip"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
) -> JSONResponse:
    """Fill runner candidate grid from real GeoJSON via geopandas.

    Source (preferred):
      data/Xuanhuongward/XuanHuongWarsFeaturesClean.geojson
    taxonomy_root unique: food_and_drink, lodging, health_care, shopping, …
    UI maps: lodging→accommodation, health_care→health_and_medicine.
    """
    path = _resolve_geojson()
    if path is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "GeoJSON not found",
                "tried": [str(CLEAN_GEOJSON), str(FEATURED_GEOJSON)],
            },
        )

    try:
        try:
            by_tax, counts_full, roots_all = _load_candidates_geopandas(path, min_confidence)
            engine = "geopandas"
        except ImportError:
            by_tax, counts_full, roots_all = _load_candidates_json(path, min_confidence)
            engine = "json"
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "path": str(path)},
        )

    candidates: list[dict[str, Any]] = []
    for tax, items in by_tax.items():
        items.sort(key=lambda x: -x["confidence"])
        candidates.extend(items[:per_tax])

    for i, c in enumerate(candidates, 1):
        c["uid"] = f"C-{i:03d}"

    return JSONResponse(
        content={
            "source": str(path.relative_to(ROOT_DIR)) if str(path).startswith(str(ROOT_DIR)) else str(path),
            "engine": engine,
            "taxonomy_map": TAXONOMY_MAP,
            "taxonomy_root_unique": roots_all,
            "counts_full": counts_full,
            "candidates": candidates,
        }
    )


# Static mounts
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
