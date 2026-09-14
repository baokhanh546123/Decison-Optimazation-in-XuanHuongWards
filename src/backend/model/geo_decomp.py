"""Spatial / Geographic Decomposition helpers for MO-MCLP.

Cluster candidates in UTM space (KMeans Lloyd or PAM/k-medoids), keep top
coverage-weight candidates per cluster, return reduced index set.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


def candidate_xy_utm(candidate_set, utm_epsg: int = 32648) -> np.ndarray:
    """Extract UTM (x, y) coordinates from candidate GeoDataFrame. Shape (n_j, 2)."""
    from pyproj import Transformer

    if candidate_set is None:
        raise ValueError(
            "eps_mode='geographic' needs candidate_set (GeoDataFrame) with lon/lat."
        )
    cand = candidate_set
    if hasattr(cand, "geometry") and cand.geometry is not None:
        gdf = cand
        gdf_utm = gdf.to_crs(epsg=utm_epsg)
        xy = np.column_stack(
            [gdf_utm.geometry.x.to_numpy(), gdf_utm.geometry.y.to_numpy()]
        )
        return xy.astype(np.float64)

    if "lon" in cand.columns and "lat" in cand.columns:
        to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        x, y = to_utm.transform(cand["lon"].to_numpy(), cand["lat"].to_numpy())
        return np.column_stack([x, y]).astype(np.float64)

    raise ValueError("candidate_set missing geometry or lon/lat columns.")


def kmeans_numpy(xy: np.ndarray, k: int, max_iter: int = 50, seed: int = 42) -> np.ndarray:
    """Lloyd KMeans (k-means++ init). Returns labels shape (n,)."""
    n = xy.shape[0]
    k = min(k, n)
    rng = np.random.default_rng(seed)
    centers = np.empty((k, xy.shape[1]), dtype=np.float64)
    centers[0] = xy[rng.integers(n)]
    closest = np.full(n, np.inf)
    for c in range(1, k):
        d = np.linalg.norm(xy - centers[c - 1], axis=1)
        closest = np.minimum(closest, d)
        probs = closest ** 2
        s = probs.sum()
        if s <= 0:
            centers[c] = xy[rng.integers(n)]
        else:
            centers[c] = xy[rng.choice(n, p=probs / s)]

    labels = np.zeros(n, dtype=np.int64)
    for _ in range(max_iter):
        dists = np.linalg.norm(xy[:, None, :] - centers[None, :, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            mask = labels == c
            if np.any(mask):
                centers[c] = xy[mask].mean(axis=0)
    return labels


def pam_numpy(xy: np.ndarray, k: int, max_iter: int = 30, seed: int = 42) -> np.ndarray:
    """PAM (k-medoids). Prefer KMeans when n > ~3000."""
    n = xy.shape[0]
    k = min(k, n)
    rng = np.random.default_rng(seed)
    medoid_idx = rng.choice(n, size=k, replace=False)

    def assign(medoids):
        d = np.linalg.norm(xy[:, None, :] - xy[medoids][None, :, :], axis=2)
        return np.argmin(d, axis=1), float(d.min(axis=1).sum())

    labels, cost = assign(medoid_idx)
    for _ in range(max_iter):
        improved = False
        for mi in range(k):
            cluster_pts = np.where(labels == mi)[0]
            if len(cluster_pts) <= 1:
                continue
            best_swap = medoid_idx[mi]
            best_cost = cost
            for cand in cluster_pts:
                if cand == medoid_idx[mi]:
                    continue
                trial = medoid_idx.copy()
                trial[mi] = cand
                _, trial_cost = assign(trial)
                if trial_cost + 1e-9 < best_cost:
                    best_cost = trial_cost
                    best_swap = cand
            if best_swap != medoid_idx[mi]:
                medoid_idx[mi] = best_swap
                labels, cost = assign(medoid_idx)
                improved = True
        if not improved:
            break
    return labels


def select_indices_by_cluster(
    labels: np.ndarray,
    weights: np.ndarray,
    quota: int,
) -> np.ndarray:
    """Keep top-quota candidates by weight inside each cluster. Sorted unique indices."""
    k = int(labels.max()) + 1 if len(labels) else 0
    keep: List[int] = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if len(idx) == 0:
            continue
        order = idx[np.argsort(-weights[idx])]
        take = order[: min(quota, len(order))]
        keep.extend(take.tolist())
    out = np.unique(np.asarray(keep, dtype=np.int64))
    out.sort()
    return out
