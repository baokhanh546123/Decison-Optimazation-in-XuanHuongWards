"""
test.py — End-to-end smoke pipeline cho MO-MCLP (Xuân Hương ward).

Luồng:
  1. Load boundary + demand + roads (path tương đối từ repo root)
  2. Sinh candidate set (grid + street)
  3. Build MCLP_Data (sparse coverage)
  4. ε-constraint sweep (early_stop + re_solve)
  5. (Tuỳ chọn) export bản đồ Pareto HTML / JPEG

Chạy từ repo root:
  PYTHONPATH=src/backend python src/backend/test.py
  PYTHONPATH=src/backend python src/backend/test.py --mode tight --export-map
  PYTHONPATH=src/backend python src/backend/test.py --n-points 8 --time-limit 120
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd

from dataclass.MCLP import MCLP_Data
from model.optimization import Optimization
from utils.candidate_grid import build_candidate_set
from utils.load_data import load_places


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent.parent
DATA_DIR = REPO_ROOT / "data"

BOUNDARY_PATH = DATA_DIR / "bounary" / "boundary.geojson"
DEMAND_PATH = DATA_DIR / "Xuanhuongward" / "Xuan Huong Wards_featured.geojson"
ROADS_PATH = DATA_DIR / "Xuanhuongward" / "Xuan Huong Wards_roads.geojson"
OUTPUT_MAP_DIR = REPO_ROOT / "outputs" / "maps"


def _check_data_files() -> None:
    missing = [p for p in (BOUNDARY_PATH, DEMAND_PATH, ROADS_PATH) if not p.exists()]
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(
            f"Thiếu file dữ liệu (chạy từ repo có thư mục data/):\n{lines}\n"
            f"REPO_ROOT={REPO_ROOT}"
        )


def load_ward_polygon(boundary_path: Path = BOUNDARY_PATH, index: int = 2):
    """Đọc boundary GeoJSON và lấy polygon ward theo index (mặc định 2 = Xuân Hương)."""
    wards_df = gpd.read_file(boundary_path)
    if index < 0 or index >= len(wards_df):
        raise IndexError(
            f"boundary index={index} ngoài phạm vi [0, {len(wards_df) - 1}]"
        )
    return wards_df.geometry.iloc[index]


def build_pipeline(
    *,
    p_max: int = 3,
    grid_spacing_m: float = 220.0,
    street_spacing_m: float = 80.0,
    ward_index: int = 2,
):
    """Load data → candidate → MCLP_Data."""
    _check_data_files()

    print(f"[INFO] REPO_ROOT = {REPO_ROOT}")
    print(f"[INFO] DATA_DIR  = {DATA_DIR}")

    wards_polygon = load_ward_polygon(BOUNDARY_PATH, index=ward_index)
    print(f"[OK] Ward polygon (boundary index={ward_index})")

    demand_gdf = load_places(str(DEMAND_PATH))
    print(f"[OK] Demand POIs: {len(demand_gdf)}")

    roads_path = str(ROADS_PATH)
    candidate_gdf, candidate_cost = build_candidate_set(
        roads=roads_path,
        ward_polygon_wgs84=wards_polygon,
        grid_spacing_m=grid_spacing_m,
        street_spacing_m=street_spacing_m,
    )

    mclp = MCLP_Data.from_geodata(
        demand_gdf,
        candidate_gdf,
        candidate_cost=candidate_cost,
        P_max=p_max,
    )
    avg_cover = float(mclp.a.sum(axis=1).mean())
    print(
        f"\n[OK] Coverage matrix a_ij shape: {mclp.a.shape}, "
        f"trung bình mỗi POI được phủ bởi {avg_cover:.1f} candidate, "
        f"nnz={mclp.a.nnz}"
    )
    return demand_gdf, candidate_gdf, roads_path, wards_polygon, mclp


def run_sweep(
    mclp: MCLP_Data,
    demand_gdf,
    candidate_gdf,
    roads_path: str,
    wards_polygon,
    *,
    mode: str = "notebook",
    n_points: int = 12,
    time_limit_s: int = 300,
    relative_gap: float = 0.05,
    n_parallel: int = 1,
    workers_per_solve: int = 4,
    early_stop: bool = True,
    re_solve_flagged: bool = True,
    auto_reduce: bool = False,
    max_candidates: int = 1200,
    re_solve_time_limit : int = 600
):
    """Chạy ε-constraint sweep và in bảng kết quả."""
    opt = Optimization(
        data=mclp,
        demand_set=demand_gdf,
        candidate_set=candidate_gdf,
        roads_set=roads_path,
        ward_polygon_wgs84=wards_polygon,
        n_points=n_points,
        time_limit_s=time_limit_s,
        relative_gap=relative_gap,
        n_parallel=n_parallel,
        workers_per_solve=workers_per_solve,
        use_hint=True,
        early_stop=early_stop,
        early_stop_patience=2,
        re_solve_flagged=re_solve_flagged,
        re_solve_time_limit=re_solve_time_limit,
        re_solve_gap_threshold=20.0,
        max_candidates=max_candidates,
        eps_mode=mode,
    )

    print(
        f"\n[RUN] ε-sweep  mode={mode}  n_points={n_points}  "
        f"time_limit={time_limit_s}s  early_stop={early_stop}  "
        f"re_solve={re_solve_flagged}  auto_reduce={auto_reduce}"
    )
    results = opt.epsilon_constraint_sweep(auto_reduce=auto_reduce)

    print("\n" + "=" * 78)
    print(
        f"{'ε':>10}  {'f1':>10}  {'f2':>8}  {'n_fac':>5}  "
        f"{'gap%':>7}  {'flag':>5}  status"
    )
    print("-" * 78)
    for r in results:
        print(
            f"{r['epsilon']:10.4f}  "
            f"{r['f1_covering_profit']:10.3f}  "
            f"{r['f2_cost']:8.4f}  "
            f"{r['n_facilities']:5d}  "
            f"{r['optimality_gap_pct']:7.2f}  "
            f"{str(r.get('flagged_non_monotonic', False))!s:>5}  "
            f"{r.get('status', '')}"
        )
    print("=" * 78)
    return results


def export_maps(
    candidate_gdf,
    results: list,
    demand_gdf,
    *,
    map_mode: str = "dot",
    only_trusted: bool = False,
):
    """Export Pareto map HTML + JPEG vào outputs/maps/."""
    try:
        from visualize.visualize_plot import export_pareto_map
    except ImportError as exc:
        print(f"[WARN] Không import được visualize ({exc}) — bỏ qua export map.")
        return {}

    paths = export_pareto_map(
        candidate_gdf=candidate_gdf,
        sweep_results=results,
        demand_gdf=demand_gdf,
        out_dir=OUTPUT_MAP_DIR,
        stem="xuanhuong_pareto",
        formats=("html", "jpeg"),
        mode=map_mode,  # type: ignore[arg-type]
        only_trusted=only_trusted,
    )
    for kind, path in paths.items():
        print(f"[OK] Map {kind}: {path}")
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MO-MCLP end-to-end test pipeline (Xuân Hương)",
    )
    p.add_argument(
        "--mode", choices=("notebook", "tight"), default="notebook",
        help="eps_mode: notebook=Σc (đối chiếu ipynb); tight=top-P_max costs",
    )
    p.add_argument("--p-max", type=int, default=3)
    p.add_argument("--n-points", type=int, default=12)
    p.add_argument("--time-limit", type=int, default=300, dest="time_limit_s")
    p.add_argument("--relative-gap", type=float, default=0.05)
    p.add_argument("--n-parallel", type=int, default=1)
    p.add_argument("--workers", type=int, default=4, dest="workers_per_solve")
    p.add_argument("--grid-spacing", type=float, default=220.0)
    p.add_argument("--street-spacing", type=float, default=80.0)
    p.add_argument("--ward-index", type=int, default=2)
    p.add_argument(
        "--auto-reduce", action="store_true",
        help="Giảm |J| theo coverage weight (max_candidates)",
    )
    p.add_argument("--re_solve-time-limit" , type = int , default=120)
    p.add_argument("--max-candidates", type=int, default=1200)
    p.add_argument(
        "--no-early-stop", action="store_true",
        help="Tắt sweep early-stop khi f1 bão hòa",
    )
    p.add_argument(
        "--no-re-solve", action="store_true",
        help="Tắt re-solve điểm non-monotonic / gap cao",
    )
    p.add_argument(
        "--export-map", action="store_true",
        help="Export Pareto map HTML + JPEG vào outputs/maps/",
    )
    p.add_argument(
        "--map-mode", choices=("heatmap", "dot"), default="dot",
    )
    p.add_argument(
        "--only-trusted",
        action="store_true",
        help="Khi export map, chỉ vẽ điểm không flagged_non_monotonic",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    demand_gdf, candidate_gdf, roads_path, wards_polygon, mclp = build_pipeline(
        p_max=args.p_max,
        grid_spacing_m=args.grid_spacing,
        street_spacing_m=args.street_spacing,
        ward_index=args.ward_index,
    )

    results = run_sweep(
        mclp,
        demand_gdf,
        candidate_gdf,
        roads_path,
        wards_polygon,
        mode=args.mode,
        n_points=args.n_points,
        time_limit_s=args.time_limit_s,
        relative_gap=args.relative_gap,
        n_parallel=args.n_parallel,
        workers_per_solve=args.workers_per_solve,
        early_stop=not args.no_early_stop,
        re_solve_flagged=not args.no_re_solve,
        re_solve_time_limit=args.re_solve_time_limit,
        auto_reduce=args.auto_reduce,
        max_candidates=args.max_candidates,
    )

    if not results:
        print("[WARN] Không có nghiệm Pareto nào.")
        return 1

    if args.export_map:
        export_maps(
            candidate_gdf,
            results,
            demand_gdf,
            map_mode=args.map_mode,
            only_trusted=args.only_trusted,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())