from __future__ import annotations 
import os 
from contextlib import asynccontextmanager
from typing import List , Dict , Optional
from api.jobs import JobManager
from api.schemas import * 
from api.state import PipelineState
from model.optimization import Optimization 
from utils.candidate_grid import *
from utils.load_data import load_places , clean_roads
from pathlib import Path 
import geopandas as gpd
import pandas as pd 


root = Path(__file__).parent.parent.parent.absolute()
data = root / 'data'

wards_df = gpd.read_file(f"{data}/bounary/boundary.geojson")
wards_polygon = wards_df['geometry'][2]

demand_gdf = load_places(f'{data}/Xuanhuongward/Xuan Huong Wards_featured.geojson')
#print('Demand Set')
#print(demand_gdf)

candidate_gdf, candidate_cost = build_candidate_set(
    roads='/home/trank/python/DecisionOptimazation/data/Xuanhuongward/Xuan Huong Wards_roads.geojson',
    ward_polygon_wgs84=wards_polygon,
    grid_spacing_m=220,
    street_spacing_m=80,
)
from dataclass.MCLP import MCLP_Data
data = MCLP_Data.from_geodata(
    demand_gdf, candidate_gdf,
    candidate_cost=candidate_cost,
    P_max=3,
)
print(f"\n[OK] Coverage matrix a_ij shape: {data.a.shape}, "
      f"trung bình mỗi POI được phủ bởi {data.a.sum(axis=1).mean():.1f} candidate")

opt = Optimization(data = data , demand_set = demand_gdf , 
candidate_set = candidate_gdf , roads_set = '/home/trank/python/DecisionOptimazation/data/Xuanhuongward/Xuan Huong Wards_roads.geojson',
ward_polygon_wgs84=wards_polygon,workers_per_solve=4)
result = opt.epsilon_constraint_sweep()
for r in result:
    print(f"epsilon={r['epsilon']:.2f}  f1(covering)={r['f1_covering_profit']:.3f}  "
          f"f2(cost)={r['f2_cost']:.3f}  n_facilities={r['n_facilities']}  "
          f"gap={r['optimality_gap_pct']:.1f}%  flagged={r['flagged_non_monotonic']}")
