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

## Bước 4 — 2 section + biểu đồ (package `visualize`)
Khi vào Bước 4 thẻ wizard mở rộng (GSAP, tối đa 1640px) và chia 2 cột:

| Section | Nội dung |
|---|---|
| 01 — Kết quả | Pareto front (canvas vẽ động), thống kê, bảng điểm, vị trí được chọn |
| 02 — Biểu đồ | Bản đồ nhiệt / bản đồ ghim (pydeck, iframe) và ảnh tĩnh (matplotlib); phạm vi "Toàn bộ Pareto" hoặc "Điểm #k" đang xem ở Section 01 |

Biểu đồ do `visualize/visualize_plot.py` dựng: `plot_pareto_map_pydeck` + `export_deck_html` (html) và
`plot_pareto_static_jpeg` (jpeg), qua `api/runner_maps.py`. Mỗi lần chạy xong có `run_id` trong kết quả:

```
GET /api/runs/{run_id}/map.html?mode=heatmap|dot[&point=k]
GET /api/runs/{run_id}/map.jpg[?point=k]
```
Server giữ ngữ cảnh 6 lần chạy gần nhất (RAM + thư mục tạm); restart server thì phải chạy lại để xem biểu đồ.
Bản đồ pydeck tải deck.gl và nền bản đồ từ CDN nên cần mạng ở trình duyệt; ảnh tĩnh thì không.
Cần `pip install pydeck matplotlib` (đã có trong requirements.txt).
JS: `runner_fx.js` (GSAP: mở rộng width, stagger, count-up), `runner_charts.js` (tab, tải biểu đồ).
