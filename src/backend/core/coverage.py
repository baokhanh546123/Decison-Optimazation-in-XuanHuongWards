from __future__ import annotations
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy import sparse
from typing import Optional, Sequence
from dataclass.config import configs 
import numpy as np

config = configs()
WGS84 , UTM48N = config.WGS84 , config.UTM48N

def build_coverage_matrix_sparse(
    demand_gdf,
    candidate_gdf,
    max_radius_m: Optional[float] = None,
) -> sparse.csr_matrix:
    to_utm = Transformer.from_crs(WGS84, f"EPSG:{UTM48N}", always_xy=True)
    dx, dy = to_utm.transform(demand_gdf["lon"].to_numpy(), demand_gdf["lat"].to_numpy())
    cx, cy = to_utm.transform(candidate_gdf["lon"].to_numpy(), candidate_gdf["lat"].to_numpy())

    demand_xy = np.column_stack((dx, dy))
    candidate_xy = np.column_stack((cx, cy))

    n_i, n_j = len(demand_gdf), len(candidate_gdf)
    radii = demand_gdf["coverage_radius_m"].to_numpy(dtype=float)
    r_query = float(max_radius_m) if max_radius_m is not None else float(radii.max())

    tree = cKDTree(candidate_xy)
    neighbors = tree.query_ball_point(demand_xy, r_query)

    rows: list[int] = []
    cols: list[int] = []
    for i, cand_idx in enumerate(neighbors):
        if not cand_idx:
            continue
        cand_idx = np.asarray(cand_idx, dtype=np.int64)
        d = np.linalg.norm(candidate_xy[cand_idx] - demand_xy[i], axis=1)
        keep = cand_idx[d <= radii[i]]
        if keep.size:
            rows.extend([i] * keep.size)
            cols.extend(keep.tolist())

    data = np.ones(len(rows), dtype=np.int8)
    a_sparse = sparse.csr_matrix((data, (rows, cols)), shape=(n_i, n_j))
    a_sparse.sum_duplicates()
    return a_sparse


def coverage_distance_for(
    demand_gdf,
    candidate_gdf,
    chosen_candidate_idx: Sequence[int],
) -> np.ndarray:
    """
    Khoảng cách demand -> CHỈ các candidate đã chọn (vd sau khi solver trả nghiệm),
    dùng để vẽ bán kính phục vụ / phân tích khoảng cách mà không phải giữ dist_ij
    (n_i, n_j) dense trong suốt vòng đời chương trình.
    Trả về mảng shape (n_i, len(chosen_candidate_idx)).
    """
    to_utm = Transformer.from_crs(WGS84, f"EPSG:{UTM48N}", always_xy=True)
    dx, dy = to_utm.transform(demand_gdf["lon"].to_numpy(), demand_gdf["lat"].to_numpy())
    chosen = candidate_gdf.iloc[list(chosen_candidate_idx)]
    cx, cy = to_utm.transform(chosen["lon"].to_numpy(), chosen["lat"].to_numpy())

    demand_xy = np.column_stack((dx, dy))
    chosen_xy = np.column_stack((cx, cy))
    return np.linalg.norm(demand_xy[:, None, :] - chosen_xy[None, :, :], axis=2)