# engine-data-analysis

发动机台架性能数据分析工具集 — Hermes Agent Skill

## 功能

- **增压器 A/B 对比** — 双增压器多维度加权评分（低速扭矩 / BSFC / 涡轮转速余量 / WG 效率 / 排温 / 峰值扭矩）
- **燃烧特性分析** — COV（循环变动系数）/ AI50（CA50 燃烧相位）/ 点火角（实际 / MBT / 退角）/ 爆震窗口 / VVT / IMEP
- **高原能力评估** — 根据 ISO 2533 标准大气模型推算高原增压器转速，评估安全余量
- **单发动机万有特性分析** — 全负荷+部分负荷稳态点分析（扭矩/功率/BSFC/增压压力/WG开度/排温/涡轮转速/进气流量）
- **数据可视化** — 支持性能对比图（6 子图）、燃烧特性图（9 子图）、单机分析图（8 子图）
- **自动列名检测** — 20+ 种发动机信号自动模糊匹配（支持中文/英文/ETAS INCA 命名）

## 快速使用

```python
from engine_analysis import *

# A/B 增压器对比
out = full_analysis("数据文件.xlsx", "博马", "奕森", n_points=9)
print(out["report"])

# 单发动机燃烧分析
out = single_engine_full_analysis(
    "260410-B15HTC万有数据.csv",
    encoding="gbk", header_rows=5,
    save_plot_performance="/tmp/performance.png",
    save_plot_combustion="/tmp/combustion.png",
)
print(out["report"])
```

## 支持的信号

rpm / torque / power / BSFC / boost / EGT / turbo_speed / WG / airflow / backpressure / intake_temp / **COV** / **AI50** / **spark_act** / **spark_mbt** / **spark_delta** / **knock** / **VVT** / **fuel_flow** / **IMEP**

---

## 更新日志

### 2026-06-02 — feat: add combustion analysis
- 新增燃烧特性分析：COV/AI50/点火角/点火退角/爆震/VVT/IMEP 信号检测
- 新增 `single_engine_combustion_analysis()` 燃烧一站式分析
- 新增 `single_engine_full_analysis()` 性能+燃烧双通道全分析
- 新增 `_plot_combustion_analysis()` 9 子图燃烧可视化
- `COLUMN_PATTERNS` 新增 9 种信号类型（cov/ai50/spark_act/spark_mbt/spark_delta/knock/vvt/fuel_flow/imep）
- SKILL.md 更新：触发条件、快速入口、列名参考表
