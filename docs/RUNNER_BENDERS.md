# Tích hợp Benders vào `runner.html`

## Chạy
```bash
cd src/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# mở http://localhost:8000/run
```

## Luồng
`runner.html` (4 bước) → `window.getRunConfig()` → `js/runner_benders.js`
→ `POST /api/optimize` → job nền (`api/jobs.py`) → `api/runner_service.py`
→ `Optimization(eps_mode="benders")` (`model/benders_solver.py`) → `GET /api/jobs/{id}` → Bước 4 (Pareto thật).

## Ánh xạ tham số giao diện → mô hình
| Giao diện | Mô hình |
|---|---|
| Candidate đã chọn (Bước 1) | Tập J (cột của `a_ij`) |
| Bán kính / trọng số theo taxonomy (Bước 3) | `coverage_radius_m` và `p_i = weight × confidence` của demand cùng taxonomy_root |
| Confidence toàn cục / riêng từng candidate | Candidate có confidence thấp hơn ngưỡng bị loại khỏi J |
| Demand-weight threshold (Bước 2) | Candidate j chỉ phủ demand có `p_i ≥ ngưỡng × max(p)`; 0 = phủ tất cả |
| P_max, số điểm ε | `P_max`, `n_points` |
| λ₁ / λ₂ | Chọn điểm khuyến nghị (★) trên Pareto: max `λ₁·f₁/f₁max − λ₂·f₂/f₂max` |
| Panel Benders | `benders_max_iters`, `benders_master_time_limit_s`, `time_limit_s` mỗi điểm ε |

Demand = POI trong `data/Xuanhuongward/XuanHuongWarsFeaturesClean.geojson` (confidence ≥ 0.3).
Chi phí `c_j` = xếp hạng class đường gần nhất (`apply_road_cost`), chuẩn hoá theo max.

## Test
```bash
cd src/backend && PYTHONPATH=. pytest tests/test_runner_benders_api.py -q
```
