from __future__ import annotations 
import os 
from contextlib import asynccontextmanager
from typing import List , Dict , Optional
from api.jobs import JobManager
from api.schemas import * 
from api.state import PipelineState
from model.optimization import Optimization 
from utils.candidate_grid import * 
from utils.load_data import *
from pathlib import Path 
import geopandas as gpd
import pandas as pd 

def build_candidate(spacing_m : int = 220 , roads : Any = None):
    grid_candidate = generate_candidate_grid(wards_polygon , spacing_m )
    if not roads:
        return grid_candidate , np.ones(len(grid_candidate))
    print(f"\n[OK] Grid candidate: {len(grid_candidate)} vị trí (spacing {grid_spacing_m}m)")
    roads_raw = gpd.read_file(roads)
    roads_clean = clean_roads(roads_raw)
    n_eligible = int(roads_clean["is_candidate_eligible"].sum())
    print(f"[OK] Roads: {len(roads_raw)} segment, {n_eligible} eligible sau clean_roads()")

    street_cand = generate_street_candidates(
        roads_clean, ward_polygon_wgs84, spacing_m=street_spacing_m, utm_epsg=utm_epsg,
        start_id=len(grid_candidate),
    )
    print(f"[OK] Street candidate: {len(street_cand)} vị trí (spacing {street_spacing_m}m)")

    merged = merge_candidate_sets(grid_candidate, street_cand, utm_epsg=utm_epsg)
    cost = derive_candidate_cost(merged)
    print(f"[OK] Candidate set J sau merge + dedup: {len(merged)}")
    return merged, cost

root = Path(__file__).parent.parent.parent.absolute()
data = root / 'data'

wards_df = gpd.read_file(f"{data}/bounary/boundary.geojson")
wards_polygon = wards_df['geometry'][2]

demand_gdf = load_places(f'{data}/Xuanhuongward/Xuan Huong Wards_featured.geojson')
print('Demand Set')
print(demand_gdf)

candidate_gpd , candidate_cost = build_candidate(roads = f'{data}/Xuanhuongward/Xuan Huong Wards_roads_v2.geojson')

