from dataclass.config import configs
from pyproj import Transformer
from scipy.spatial import cKDTree
import geopandas as gpd
import pandas as pd 

def generate_candidate_grid(
    ward_polygon_wgs84,
    spacing_m: float = 220.0,
) -> gpd.GeoDataFrame:
    config = configs()
    WGS84 , UTM48N = config.WGS84 , config.UTM48N
    to_utm = Transformer.from_crs(WGS84, UTM48N, always_xy=True)
    to_wgs = Transformer.from_crs(UTM48N, config.WGS84, always_xy=True)

    poly_utm = gpd.GeoSeries([ward_polygon_wgs84], crs=WGS84).to_crs(epsg=UTM48N).iloc[0]
    minx, miny, maxx, maxy = poly_utm.bounds

    xs = np.arange(minx, maxx, spacing_m)
    ys = np.arange(miny, maxy, spacing_m)
    xx, yy = np.meshgrid(xs, ys)
    pts_utm = np.column_stack([xx.ravel(), yy.ravel()])

    mask = np.array([poly_utm.contains(Point(x, y)) for x, y in pts_utm])
    pts_utm = pts_utm[mask]

    lon, lat = to_wgs.transform(pts_utm[:, 0], pts_utm[:, 1])
    cand = gpd.GeoDataFrame(
        {"candidate_id": np.arange(len(lon))},
        geometry=gpd.points_from_xy(lon, lat),
        crs=WGS84,
    )
    cand["lon"], cand["lat"] = lon, lat
    return cand

def _dedup_points(pts_df: pd.DataFrame, min_dist_m: float) -> pd.DataFrame:
    if len(pts_df) <= 1:
        return pts_df.reset_index(drop=True)
    xy = pts_df[["x", "y"]].to_numpy()
    tree = cKDTree(xy)
    pairs = tree.query_pairs(r=min_dist_m)
    to_drop = {max(i, j) for i, j in pairs}
    return pts_df.drop(index=list(to_drop)).reset_index(drop=True)


def _extract_linestrings(geom) -> list:
    """Trích LineString thuần từ kết quả intersection (có thể là LineString,
    MultiLineString, hoặc GeometryCollection lẫn Point/LineString khi cắt ở góc
    ranh giới poly). Bỏ qua Point/Polygon lẫn vào do sai số hình học."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        parts = []
        for sub in geom.geoms:
            parts.extend(_extract_linestrings(sub))
        return parts
    return []


def _sample_line(line, spacing_m: float) -> list:
    length = line.length
    if length == 0:
        return [line.interpolate(0)]
    n_points = max(int(length // spacing_m), 1)
    steps = np.linspace(0, length, n_points + 1)
    return [line.interpolate(d) for d in steps]

def generate_street_candidates(
    roads_gdf: gpd.GeoDataFrame,
    ward_polygon_wgs84,
    spacing_m: float = 80.0,
    utm_epsg: int = 32648,
    start_id: int = 0,
) -> gpd.GeoDataFrame:
    """Bước 4: sinh candidate dọc street eligible, clip theo ward, dedup theo khoảng cách."""
    eligible = roads_gdf[roads_gdf["is_candidate_eligible"]].copy()
    empty_cols = ["candidate_id", "lon", "lat", "roads_name", "class", "walkable_tier", "avg_width_m"]
    if eligible.empty:
        return gpd.GeoDataFrame(columns=empty_cols, geometry=[], crs="EPSG:4326")

    poly_utm = gpd.GeoSeries([ward_polygon_wgs84], crs="EPSG:4326").to_crs(epsg=utm_epsg).iloc[0]
    lines_utm = eligible.to_crs(epsg=utm_epsg)

    # Lọc trước bằng intersects() — tránh chạy intersection() (đắt hơn) trên các
    # segment hoàn toàn nằm ngoài ranh giới, và tránh tạo geometry rỗng thừa.
    lines_utm = lines_utm[lines_utm.geometry.intersects(poly_utm)].copy()
    if lines_utm.empty:
        return gpd.GeoDataFrame(columns=empty_cols, geometry=[], crs="EPSG:4326")

    lines_utm["geometry"] = lines_utm.geometry.intersection(poly_utm)
    lines_utm = lines_utm[~lines_utm.geometry.is_empty]

    rows = []
    for _, row in lines_utm.iterrows():
        for part in _extract_linestrings(row.geometry):
            for pt in _sample_line(part, spacing_m):
                rows.append({
                    "roads_name": row.get("roads_name"),
                    "class": row.get("class"),
                    "walkable_tier": row.get("walkable_tier"),
                    "avg_width_m": row.get("avg_width_m"),
                    "x": pt.x, "y": pt.y,
                })

    if not rows:
        return gpd.GeoDataFrame(columns=empty_cols, geometry=[], crs="EPSG:4326")

    pts_df = pd.DataFrame(rows)
    pts_df = _dedup_points(pts_df, min_dist_m=spacing_m * 0.4)

    to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    lon, lat = to_wgs.transform(pts_df["x"].values, pts_df["y"].values)
    pts_df["lon"], pts_df["lat"] = lon, lat
    pts_df["candidate_id"] = np.arange(start_id, start_id + len(pts_df))

    cand = gpd.GeoDataFrame(
        pts_df.drop(columns=["x", "y"]),
        geometry=gpd.points_from_xy(lon, lat),
        crs="EPSG:4326",
    )
    return cand.reset_index(drop=True)

def merge_candidate_sets(
    grid_cand: gpd.GeoDataFrame,
    street_cand: gpd.GeoDataFrame,
    utm_epsg: int = 32648,
    min_dist_m: float = 30.0,
) -> gpd.GeoDataFrame:
    """Union grid candidate (cũ) với street candidate (mới), dedup theo khoảng cách, reindex id."""
    combined = pd.concat([grid_cand, street_cand], ignore_index=True, sort=False)

    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    x, y = to_utm.transform(combined["lon"].values, combined["lat"].values)
    tree = cKDTree(np.column_stack([x, y]))
    pairs = tree.query_pairs(r=min_dist_m)
    to_drop = {max(i, j) for i, j in pairs}

    combined = combined.drop(index=list(to_drop)).reset_index(drop=True)
    combined["candidate_id"] = np.arange(len(combined))
    return gpd.GeoDataFrame(
        combined, geometry=gpd.points_from_xy(combined["lon"], combined["lat"]), crs="EPSG:4326"
    )

def derive_candidate_cost(candidate_gdf: gpd.GeoDataFrame) -> np.ndarray:
    """Bước 5: cost proxy c_j từ class hierarchy + độ rộng đường, thay np.ones() placeholder."""
    if "class" not in candidate_gdf.columns:
        return np.ones(len(candidate_gdf))

    rank = candidate_gdf["class"].map(CLASS_COST_RANK).fillna(1.0).to_numpy(dtype=float)

    width = pd.to_numeric(candidate_gdf.get("avg_width_m"), errors="coerce").to_numpy(dtype=float)
    fallback = np.nanmedian(width) if not np.all(np.isnan(width)) else 0.0
    width = np.where(np.isnan(width), fallback, width)
    span = width.max() - width.min()
    width_norm = (width - width.min()) / span if span > 1e-9 else np.zeros_like(width)

    cost = rank + width_norm
    return cost / cost.max()