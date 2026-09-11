from dataclass.taxonomy_config import TaxonomyConfig
from utils.parse_data import _parse_geometry , _parse_modes
import geopandas as gpd 
import pandas as pd 
import numpy as np 

config = TaxonomyConfig()
def load_places(path : str , min_confidence : float = None) -> gpd.GeoDataFrame:
  min_confidence = config.min_confidence if min_confidence is None else min_confidence
  if path.endswith('.parquet'):
    df = pd.read_parquet(path)
  elif path.endswith('.csv'):
    df = pd.read_csv(path)
  else:
    df = gpd.read_file(path)

  required_cols = {
        "id", "names", "basic_category", "taxonomy_primary", "taxonomy_root",
        "confidence", "geometry",
    }
  missing = required_cols - set(df.columns)
  if missing:
    raise ValueError(f"Thiếu cột bắt buộc trong dataset: {missing}")
  df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
  df = df[df["confidence"] >= min_confidence].copy()

  # --- parse geometry -> lon/lat (giữ nguyên nguyên tắc của bạn: điểm chính xác nếu là Point) ---
  df["_geom"] = df["geometry"].apply(_parse_geometry)
  df = df[df["_geom"].notna()].copy()
  df["lon"] = df["_geom"].apply(lambda g: g.x if g.geom_type == "Point" else g.centroid.x)
  df["lat"] = df["_geom"].apply(lambda g: g.y if g.geom_type == "Point" else g.centroid.y)

  # --- taxonomy_root: chuẩn hoá (Overture đôi khi để None/NaN cho basic_category lạ) ---
  df["taxonomy_root"] = df["taxonomy_root"].fillna(df["basic_category"]).astype(str)

  # --- demand weight p_i = w(taxonomy_root) * confidence ---
  df["p_i"] = df["taxonomy_root"].map(config.taxonomy_root_weight).fillna(config.default_root_weight) * df["confidence"]

  # --- bán kính phủ riêng theo ngành, dùng khi build a_ij ---
  df["coverage_radius_m"] = df["taxonomy_root"].map(config.taxonomy_root_radius_m).fillna(config.default_radius_m)

  gdf = gpd.GeoDataFrame(
      df.drop(columns=["_geom"]),
      geometry=gpd.points_from_xy(df["lon"], df["lat"]),
      crs="EPSG:4326",
  )
  gdf = gdf.reset_index(drop=True)
  gdf["demand_id"] = gdf.index  # index nội bộ dùng làm i trong I
  return gdf

def clean_roads(roads_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Bước 1: parse modes, loại rail/unknown/hạ tầng lỗi, gắn walkable_tier."""
    df = roads_gdf[roads_gdf["subtype"] == "road"].copy()

    df["allowed_modes_set"] = df["allowed_modes"].apply(_parse_modes)
    df["denied_modes_set"] = df["denied_modes"].apply(_parse_modes)

    df["is_excluded_infra"] = (
        (df["has_bridge"].fillna(False)).astype(bool)
        | (df["has_tunnel"].fillna(False)).astype(bool)
        | (df["is_under_construction"].fillna(False)).astype(bool)
    )

    df["is_candidate_eligible"] = (
        ~df["class"].isin(config.candidate_excluded_class)
        & (df["class"] != "unknown")
        & ~df["is_excluded_infra"]
    )

    df["walkable_tier"] = np.select(
        [~df["is_candidate_eligible"], df["class"].isin(config.candidate_low_priority_class)],
        ["excluded", "low_priority"],
        default="primary",
    )

    return df.reset_index(drop=True)

#if __name__ == '__main__':
#  s = load_places('/home/trank/python/DecisionOptimazation/data/Xuanhuongward/Xuan Huong Wards_featured.geojson')
#  print(s)