# Finding Location For Business By Multi-Objective Optimization

<div align="center">

**Decision Intelligence · Multi-Objective Maximum Covering Location Problem (MO-MCLP)**

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success)]()

**Case study:** Phường Xuân Hương – Đà Lạt, Việt Nam

</div>

---

## <a id="toc">Mục lục / Table of Contents</a>

| STT | Nội dung |
|-----|----------|
| 1   | [Introduction](#introduction) |
| 2   | [Method](#method) |
| 3   | [Features](#features) |
| 4   | [Project Structure](#structure) |
| 5   | [Install & Run](#install-run) |
| 6   | [Usage Example](#usage) |
| 7   | [Citation](#citation) |
| 8   | [License & Contact](#license) |

---

## <a id="introduction">1. Introduction</a>

### Bối cảnh Decision Intelligence

Trong **Decision Intelligence (DI)**, quyết định định vị cơ sở kinh doanh (cửa hàng, kho, trạm sạc, trung tâm logistics…) không chỉ dựa trên một tiêu chí đơn lẻ (chi phí thấp nhất) mà phải cân bằng nhiều mục tiêu mâu thuẫn:

- **Lợi nhuận / Độ phủ**: Tối đa hóa lượng khách hàng hoặc nhu cầu được phục vụ (*max covering profit*).
- **Chi phí / Rủi ro**: Tối thiểu hóa chi phí đầu tư, vận chuyển hoặc rủi ro.
- **Công bằng / Chất lượng dịch vụ**: Đảm bảo các khu vực đều được tiếp cận, tránh chênh lệch quá lớn.

Bài toán này thuộc nhóm **Multi-objective Maximum Covering Location Problem (MO-MCLP)** — mở rộng của bài toán kinh điển MCLP (Church & ReVelle, 1974).

### Phát biểu bài toán cụ thể

Cho:

- Tập **Demand Set** \(I\): các khu vực / khách hàng có nhu cầu.
- Tập **Candidate Set** \(J\): các vị trí ứng viên có thể mở cơ sở.
- Tham số: lợi nhuận \(p_i\) (hoặc nhu cầu \(d_i\)), chi phí \(c_j\), ma trận phủ \(a_{ij}\) (1 nếu \(j\) phủ được \(i\)).

**Yêu cầu:** Chọn tập con các candidate để mở cơ sở sao cho:

1. **Max covering profit** — tổng lợi nhuận từ các demand được phủ là lớn nhất.
2. **Accept to demand set** — đảm bảo ràng buộc về tập nhu cầu (phủ tối thiểu tỷ lệ \(\alpha\), hoặc các demand quan trọng bắt buộc phải được phủ).
3. **Candidate set & ngân sách** — chỉ chọn trong tập ứng viên cho phép, với giới hạn số cơ sở hoặc tổng chi phí.

Đây là bài toán **NP-hard**, do đó cần phương pháp giải đặc thù (exact solver cho bài nhỏ, meta-heuristic cho bài lớn).

> **Ứng dụng thực tế trong repo này:** Tối ưu vị trí kinh doanh tại khu vực phường Xuân Hương, Đà Lạt.

---

## <a id="method">2. Method</a>

### 2.1. Ký hiệu toán học

#### Tập hợp (Sets)

| Ký hiệu | Mô tả | Kích thước |
|---------|-------|------------|
| \(I\) | Tập các điểm nhu cầu (demand points) | \(\|I\| = n\) |
| \(J\) | Tập các vị trí ứng viên (candidate locations) | \(\|J\| = m\) |
| \(I_{\text{must}} \subseteq I\) | Tập demand bắt buộc phải được phủ (nếu có) | — |

#### Tham số (Parameters)

| Ký hiệu | Miền giá trị | Ý nghĩa |
|---------|--------------|---------|
| \(p_i\) | \(p_i \ge 0\) | Lợi nhuận (hoặc trọng số nhu cầu) tại demand \(i \in I\) |
| \(c_j\) | \(c_j \ge 0\) | Chi phí mở cơ sở tại candidate \(j \in J\) |
| \(a_{ij}\) | \(\{0,1\}\) | Ma trận phủ: \(a_{ij} = 1\) nếu candidate \(j\) phủ được demand \(i\) (khoảng cách \(\le\) bán kính phục vụ), ngược lại \(= 0\) |
| \(B\) | \(B > 0\) | Ngân sách tối đa cho việc mở cơ sở |
| \(P_{\max}\) | \(P_{\max} \in \mathbb{Z}^+\) | Số cơ sở tối đa được phép mở |
| \(\alpha\) | \(\alpha \in [0,1]\) | Tỷ lệ phủ tối thiểu yêu cầu (theo trọng số hoặc theo số lượng) |

#### Biến quyết định (Decision Variables)

\[
\begin{aligned}
x_j &\in \{0,1\}, && \forall j \in J \\
y_i &\in \{0,1\}, && \forall i \in I
\end{aligned}
\]

| Biến | Giá trị | Ý nghĩa |
|------|---------|---------|
| \(x_j = 1\) | Binary | Mở cơ sở tại vị trí ứng viên \(j\) |
| \(x_j = 0\) | Binary | Không mở cơ sở tại \(j\) |
| \(y_i = 1\) | Binary | Demand \(i\) được phủ bởi **ít nhất một** cơ sở được chọn |
| \(y_i = 0\) | Binary | Demand \(i\) không được phủ |

---

### 2.2. Mô hình toán học đầy đủ (MO-MCLP)

**Mục tiêu 1 — Max Covering Profit**

\[
\max \; f_1(\mathbf{x},\mathbf{y}) = \sum_{i \in I} p_i \, y_i
\]

**Mục tiêu 2 — Min Cost** (hoặc Max Net Profit)

\[
\min \; f_2(\mathbf{x}) = \sum_{j \in J} c_j \, x_j
\]

hoặc dạng net profit:

\[
\max \; f_2'(\mathbf{x},\mathbf{y}) = \sum_{i \in I} p_i y_i - \sum_{j \in J} c_j x_j
\]

**Ràng buộc**

\[
\begin{align}
& y_i \;\le\; \sum_{j \in J} a_{ij}\, x_j, && \forall i \in I && \text{(1) Logic covering} \\[6pt]
& \sum_{i \in I} p_i y_i \;\ge\; \alpha \sum_{i \in I} p_i, && && \text{(2a) Phủ tối thiểu theo trọng số} \\[6pt]
& \sum_{i \in I} y_i \;\ge\; \alpha \, |I|, && && \text{(2b) Phủ tối thiểu theo số lượng} \\[6pt]
& y_i = 1, && \forall i \in I_{\text{must}} && \text{(2c) Demand bắt buộc} \\[6pt]
& \sum_{j \in J} c_j x_j \;\le\; B, && && \text{(3a) Giới hạn ngân sách} \\[6pt]
& \sum_{j \in J} x_j \;\le\; P_{\max}, && && \text{(3b) Giới hạn số cơ sở} \\[6pt]
& x_j \in \{0,1\}, \quad y_i \in \{0,1\}, && \forall i \in I,\; j \in J && \text{(4) Binary}
\end{align}
\]

> **Ghi chú:** Ràng buộc (2a)/(2b)/(2c) và (3a)/(3b) là tùy chọn — tùy theo yêu cầu thực tế của bài toán mà kích hoạt.

---

### 2.3. Phương pháp giải

| Phương pháp | Mô tả ngắn | Phù hợp khi |
|-------------|------------|-------------|
| **Weighted Sum / Scalarization** | Gộp mục tiêu thành một hàm với trọng số \(\lambda_1, \lambda_2\) | Muốn giải nhanh bằng MILP (Gurobi, SCIP, CBC, PuLP) |
| **ε-constraint / Augmented ε-constraint** | Giữ 1 mục tiêu chính, biến mục tiêu còn lại thành ràng buộc \(\varepsilon\) | Cần kiểm soát rõ ngân sách / chi phí theo từng kịch bản |
| **MOEA (NSGA-II, NSGA-III, MOEA/D, MOPSO)** | Thuật toán tiến hóa đa mục tiêu, sinh Pareto front | Bài lớn, cần nhiều phương án trade-off cho Decision Maker |

**Quy trình Decision Intelligence trong hệ thống:**

1. **Data layer** → thu thập demand, chi phí, khoảng cách, candidate locations  
2. **Model layer** → xây dựng mô hình MO-MCLP như trên  
3. **Optimization layer** → chạy solver / MOEA sinh Pareto front  
4. **Decision layer** → nhà quản trị chọn nghiệm theo chiến lược (ưu tiên profit, cân bằng cost–coverage…)

---

## <a id="features">3. Features</a>

- Mô hình **Multi-Objective Maximum Covering Location Problem (MO-MCLP)**
- Hỗ trợ ràng buộc phủ tối thiểu (\(\alpha\)), ngân sách, số cơ sở tối đa
- Tích hợp solver chính xác (SCIP / PuLP) và meta-heuristic đa mục tiêu
- Case study thực tế: phường **Xuân Hương – Đà Lạt**
- Xuất kết quả dạng bảng + trực quan hóa vị trí trên bản đồ
- Cấu trúc backend sẵn sàng mở rộng (API / dashboard)

---

## <a id="structure">4. Project Structure</a>

```text
Decison-Optimazation-in-XuanHuongWards/
├── src/
│   └── backend/
│       ├── main.py              # Entry point
│       ├── requirements.txt
│       ├── models/              # Mô hình toán học & solver
│       ├── data/                # Demand, candidate, ma trận phủ
│       └── utils/               # Helper functions
├── docs/                        # Tài liệu bổ sung
├── README.md
└── ...
```

> *Lưu ý:* Tên repo hiện tại còn lỗi chính tả (`Decison` → `Decision`). Nên đổi tên khi refactor.

---

## <a id="install-run">5. Install & Run</a>

### Yêu cầu

- Python **3.12+**
- Git
- (Khuyến nghị) Virtual environment

### Install

#### Linux / macOS

```bash
git clone https://github.com/baokhanh546123/Decison-Optimazation-in-XuanHuongWards
cd Decison-Optimazation-in-XuanHuongWards/src/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Windows

```bash
git clone https://github.com/baokhanh546123/Decison-Optimazation-in-XuanHuongWards
cd Decison-Optimazation-in-XuanHuongWards\src\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

Sau khi chạy, hệ thống sẽ:

1. Load dữ liệu demand & candidate của khu vực Xuân Hương  
2. Xây dựng mô hình MO-MCLP  
3. Giải bài toán và xuất tập nghiệm Pareto / nghiệm tối ưu theo tham số  
4. In kết quả ra console (và có thể xuất file / bản đồ tùy cấu hình)

---

## <a id="usage">6. Usage Example</a>

```python
# Ví dụ cấu hình nhanh (trong main.py hoặc config)
config = {
    "alpha": 0.8,          # phủ tối thiểu 80% nhu cầu
    "P_max": 5,            # tối đa 5 cơ sở
    "budget": None,        # hoặc giới hạn ngân sách
    "method": "epsilon",   # "weighted" | "epsilon" | "nsga2"
}

# Chạy tối ưu
results = solve_mo_mclp(config)
print(results.pareto_front)
```

---

## <a id="citation">7. Citation</a>

Nếu bạn sử dụng mã nguồn hoặc ý tưởng từ dự án này, vui lòng trích dẫn các công trình liên quan:

```bibtex
@article{dominguez2024cooperative,
  title   = {The Cooperative Maximal Covering Location Problem with ordered partial attractions},
  author  = {Domínguez, Concepción and Gázquez, Ricardo and Morales, Juan Miguel and Pineda, Salvador},
  journal = {arXiv preprint arXiv:2305.15169},
  year    = {2024},
  url     = {https://arxiv.org/html/2305.15169v3}
}

@article{khalilzadeh2025biobjective,
  title   = {A Bi-Objective Mathematical Programming Model for a Maximal Covering Hub Location Problem Under Uncertainty},
  author  = {Khalilzadeh, M. and Ahmadi, M. and Kebriyaii, O.},
  journal = {SAGE Open},
  year    = {2025}
}

@article{church1974mclp,
  title   = {The Maximal Covering Location Problem},
  author  = {Church, Richard and ReVelle, Charles},
  journal = {Papers of the Regional Science Association},
  year    = {1974}
}
```

**Tài liệu tham khảo bổ sung:**

1. Khalilzadeh, M., & Bahari, A. (2023). A Multi-objective Mathematical Programming Model for the Problem of P-envy Emergency Medical Service Location. *Health Services Insights*.
2. Frontiers (2025). Deep reinforcement learning for multi-objective location optimization of onshore wind power stations. *Frontiers in Energy Research*.
3. ScienceDirect (2023). Continuous covering on networks: Improved mixed integer programming formulations. *Omega*.
4. MDPI (2024). Elite Multi-Criteria Decision Making—Pareto Front Optimization in Multi-Objective Optimization. *Algorithms*.
5. Medium (2024). Augmented epsilon constraint (AEC) method.
6. Substack (2025). A Practical Guide to Multi-Objective Optimization with Pymoo.

---

## <a id="license">8. License & Contact</a>

- **License:** MIT (hoặc cập nhật theo repo chính thức)
- **Repository:** [github.com/baokhanh546123/Decison-Optimazation-in-XuanHuongWards](https://github.com/baokhanh546123/Decison-Optimazation-in-XuanHuongWards)
- **Case study area:** Phường Xuân Hương, Đà Lạt, Lâm Đồng, Việt Nam
- **Author:** Khanh Tran, Tien Luu

---
