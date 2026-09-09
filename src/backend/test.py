from pathlib import Path
import os 

# backend/main.py → parents[1] = project root (mclp-project/)
ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLE_DIR = FRONTEND_DIR / "temple"
ASSET_DIR = FRONTEND_DIR / "asset"
STATIC_DIR = FRONTEND_DIR / "static"
JS_DIR = FRONTEND_DIR / "js"

print(ROOT_DIR)
if os.path.exists(FRONTEND_DIR):
    print(f"Frontend {FRONTEND_DIR}")

if os.path.exists(TEMPLE_DIR):
    print(f"Temple {TEMPLE_DIR}")

if os.path.exists(ASSET_DIR):
    print(f"Asset {ASSET_DIR}")

if os.path.exists(STATIC_DIR):
    print(f"Static {STATIC_DIR}")
