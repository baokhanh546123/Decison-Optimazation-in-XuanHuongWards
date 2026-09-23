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
FEATURED_GEOJSON = DATA_DIR / "Xuanhuongward" / "Xuan Huong Wards_featured.geojson"

# UI taxonomy chips ← GeoJSON taxonomy_root
TAXONOMY_MAP = {
    "food_and_drink": "food_and_drink",
    "lodging": "accommodation",
    "health_care": "health_and_medicine",
}

app = FastAPI(
    title="MCLP Scrollytelling API",
    description="Backend for Maximal Covering Location Problem — Xuan Huong Wards.",
    version="1.1.0",
)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/temple/index.html", status_code=302)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "frontend": str(FRONTEND_DIR),
        "index_exists": (TEMPLE_DIR / "index.html").is_file(),
        "geojson_exists": FEATURED_GEOJSON.is_file(),
        "geojson_path": str(FEATURED_GEOJSON),
    }


@app.get("/api/candidates")
async def api_candidates(
    per_tax: int = Query(40, ge=1, le=200, description="Max candidates per taxonomy_root"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
) -> JSONResponse:
    """Load featured GeoJSON and fill candidates by taxonomy_root for the UI grid."""
    if not FEATURED_GEOJSON.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": "GeoJSON not found", "path": str(FEATURED_GEOJSON)},
        )

    with FEATURED_GEOJSON.open(encoding="utf-8") as f:
        fc = json.load(f)

    by_tax: dict[str, list[dict[str, Any]]] = {
        "food_and_drink": [],
        "accommodation": [],
        "health_and_medicine": [],
    }

    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        root = props.get("taxonomy_root")
        if root not in TAXONOMY_MAP:
            continue
        ui_tax = TAXONOMY_MAP[root]
        try:
            conf = float(props.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
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
                "lng": coords[0],
                "lat": coords[1],
                "address": addr[:60],
                "primary": props.get("taxonomy_primary") or props.get("basic_category") or "",
            }
        )

    candidates: list[dict[str, Any]] = []
    for tax, items in by_tax.items():
        items.sort(key=lambda x: -x["confidence"])
        candidates.extend(items[:per_tax])

    for i, c in enumerate(candidates, 1):
        c["uid"] = f"C-{i:03d}"

    return JSONResponse(
        content={
            "source": "data/Xuanhuongward/Xuan Huong Wards_featured.geojson",
            "taxonomy_map": TAXONOMY_MAP,
            "counts_full": {k: len(v) for k, v in by_tax.items()},
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
