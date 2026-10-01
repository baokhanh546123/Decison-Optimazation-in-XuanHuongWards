from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import numpy as np
from scipy import sparse

if TYPE_CHECKING:
    import geopandas as gpd


@dataclass(slots=True)
class MCLP_Data:
    p: np.ndarray                              # (n_i,) demand weight p_i
    a: sparse.csr_matrix                       # (n_i, n_j) sparse coverage matrix, 0/1
    c: np.ndarray                               # (n_j,) candidate cost c_j
    P_max: Optional[int] = None                  # số cơ sở tối đa
    budget: Optional[float] = None               # ngân sách tối đa (Σ c_j x_j ≤ budget)
    must_cover: Optional[np.ndarray] = None       # index i bắt buộc phải phủ (I_must)
    _coverage_lists: Optional[list] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not sparse.issparse(self.a):
            self.a = sparse.csr_matrix(self.a)
        elif not isinstance(self.a, sparse.csr_matrix):
            self.a = self.a.tocsr()
        # float64 để SCALE=1e6 không mất precision khi round (float32 dễ lệch)
        self.p = np.asarray(self.p, dtype=np.float64)
        self.c = np.asarray(self.c, dtype=np.float64)
        if self.must_cover is not None:
            self.must_cover = np.asarray(self.must_cover, dtype=np.int64)

    @property
    def n_i(self) -> int:
        return int(self.a.shape[0])

    @property
    def n_j(self) -> int:
        return int(self.a.shape[1])

    @property
    def coverage_lists(self) -> list:
        """Danh sách candidate-index phủ từng demand i.

        Trả về list[np.ndarray] đã copy — tránh view vào buffer sparse bị
        invalidate hoặc pickle không an toàn khi đưa vào process pool.
        """
        if self._coverage_lists is None:
            indptr, indices = self.a.indptr, self.a.indices
            self._coverage_lists = [
                np.array(indices[indptr[i]:indptr[i + 1]], dtype=np.int64, copy=True)
                for i in range(self.n_i)
            ]
        return self._coverage_lists

    def invalidate_cache(self) -> None:
        """Gọi lại nếu `a` bị gán/mutate trực tiếp sau khi khởi tạo."""
        self._coverage_lists = None

    def memory_report(self) -> dict:
        """So sánh nhanh bộ nhớ sparse hiện dùng vs. bản dense boolean tương đương."""
        sparse_bytes = self.a.data.nbytes + self.a.indices.nbytes + self.a.indptr.nbytes
        dense_equiv_bytes = self.n_i * self.n_j
        return {
            "sparse_bytes": int(sparse_bytes),
            "dense_equivalent_bytes": int(dense_equiv_bytes),
            "reduction_factor": (dense_equiv_bytes / sparse_bytes) if sparse_bytes else float("inf"),
            "nnz": int(self.a.nnz),
            "density_pct": 100.0 * self.a.nnz / (self.n_i * self.n_j) if self.n_i and self.n_j else 0.0,
        }

    @classmethod
    def from_geodata(
        cls,
        demand_gdf: "gpd.GeoDataFrame",
        candidate_gdf: "gpd.GeoDataFrame",
        candidate_cost: Optional[np.ndarray] = None,
        max_radius_m: Optional[float] = None,
        utm_epsg: int = 32648,
        **kwargs,
    ) -> "MCLP_Data":
        """Lắp ráp MCLP_Data từ GeoDataFrame (sparse coverage).

        Yêu cầu demand_gdf đã có cột 'p_i' và 'coverage_radius_m'
        (do load_places + TaxonomyConfig).
        """
        from core.coverage import build_coverage_matrix_sparse

        a_sparse = build_coverage_matrix_sparse(
            demand_gdf, candidate_gdf, utm_epsg=utm_epsg, max_radius_m=max_radius_m
        )
        p = demand_gdf["p_i"].to_numpy(dtype=np.float64)
        c = (
            candidate_cost if candidate_cost is not None else np.ones(len(candidate_gdf))
        )
        c = np.asarray(c, dtype=np.float64)
        return cls(p=p, a=a_sparse, c=c, **kwargs)


# Alias tương thích ngược
MCLPData = MCLP_Data
