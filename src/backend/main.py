from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

# backend/main.py → parents[1] = project root (mclp-project/)
ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLE_DIR = FRONTEND_DIR / "temple"
ASSET_DIR = FRONTEND_DIR / "asset"
STATIC_DIR = FRONTEND_DIR / "static"
JS_DIR = FRONTEND_DIR / "js"

app = FastAPI(
    title="MCLP Scrollytelling API",
    description="Backend for Maximal Covering Location Problem scrollytelling demo.",
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Redirect homepage to the scrollytelling page."""
    return RedirectResponse(url="/temple/index.html", status_code=302)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "frontend": str(FRONTEND_DIR),
        "index_exists": (TEMPLE_DIR / "index.html").is_file(),
    }


# Static mounts (more specific prefixes)
if ASSET_DIR.is_dir():
    app.mount("/asset", StaticFiles(directory=str(ASSET_DIR)), name="asset")

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if JS_DIR.is_dir():
    app.mount("/js", StaticFiles(directory=str(JS_DIR)), name="js")

if TEMPLE_DIR.is_dir():
    app.mount("/temple", StaticFiles(directory=str(TEMPLE_DIR), html=True), name="temple")


if __name__ == "__main__":
    import uvicorn
    import random

    port_random = random.randint(3000 , 9999)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port_random,
        reload=True,
        reload_dirs=[str(ROOT_DIR / "backend"), str(FRONTEND_DIR)],
    )