---
name: engine-data-analysis
description: Analyze engine performance data (dyno/bench test data) — turbocharger matching, torque/BSFC/boost comparison, high-altitude capability assessment, and data visualization. Use when the user asks about engine performance data, turbocharger comparison, dyno data analysis, or any .xlsx/.csv engine test files.
---

# 发动机数据分析

分析发动机台架测试数据（dyno data）—— 增压器匹配对比、扭矩/油耗/增压压力分析、高原能力评估、数据可视化。

## 触发条件

当用户提及以下任何内容时，应加载本 skill：
- 发动机 / engine / 台架 / dyno / 增压器 / turbo / 涡轮
- 对比两个或多个部件的性能数据
- 分析 .xlsx / .csv 格式的测试数据
- 评估高原/高海拔性能
- BSFC / 燃油消耗率 / 扭矩 / 增压压力 / 排气温度 / 背压

## 快速入口

核心分析逻辑已封装到 `scripts/engine_analysis.py`，引入后直接调用即可：

```python
import sys
sys.path.insert(0, "/Users/yangdiandian/.hermes/skills/data-science/engine-data-analysis/scripts")
from engine_analysis import *
```

### 一站式分析（推荐）

```python
out = full_analysis(
    filepath="数据文件.xlsx",
    name_a="博马", name_b="奕森",
    n_points=9,               # 每组行数（不指定则自动推断）
    sheet_name="Sheet3",
    skiprows=0,               # 如果有单位行则设为1
    turbo_speed_limit=250000, # 增压器转速限制，需用户确认
    altitude_m=3000,          # 高原评估海拔，设为None则跳过
    save_plot="/tmp/comparison.png",  # 图表保存路径
)
print(out["report"])
```

### 分步分析

```python
# 1. 加载
df = load_excel("数据.xlsx", sheet_name="Sheet3", skiprows=1)
df = clean_columns(df)
df = ensure_numeric(df)

# 2. 查看数据结构
print_data_structure(df)
cols = detect_all_columns(df)
print("检测到的列:", cols)

# 3. 分隔 A/B 两组
df_a, df_b = split_groups(df, n_points=9)

# 4. 对比分析
results = compare_turbochargers(df_a, df_b, "博马", "奕森")

# 5. 高原评估
ha = assess_high_altitude(df_a, df_b, "博马", "奕森", altitude_m=3000)

# 6. 可视化
plot_comparison(results, save_path="/tmp/comparison.png")

# 7. 生成报告
report = generate_text_report(results, ha)
print(report)
```

## 分析工作流

### Step 1: 理解数据结构

数据通常来自 `.xlsx` 台架测试文件，典型格式：
- **列式布局**：转速点（1000~5000rpm × 9 点）为行，各测量指标为列
- **A/B 双组**：上下排列（前 N 行是增压器 A，后 N 行是增压器 B）
- 可能第一行是单位说明，需要用 `skiprows=1` 跳过

先用 `inspect_data(df)` 或 `print_data_structure(df)` 快速查看：
```python
df = load_excel("data.xlsx")
print_data_structure(df)
```

### Step 2: 列名检测

数据集列名可能来源不同（中文/英文/混排、含换行符等），用 `detect_all_columns()` 自动匹配：

```python
cols = detect_all_columns(df)
# 返回: {'rpm': '转速', 'torque': '扭矩', 'bsfc': 'BSFC', ...}
```

如果自动检测不到，手动指定：
```python
rpm_col = detect_column(df, "rpm")      # 自动匹配
torque_col = "DynoTorque"               # 手动指定
```

### Step 3: 数据分隔

两组数据上下排列时，用 `split_groups()` 拆分：

```python
# 明确指定每组行数（推荐）
df_a, df_b = split_groups(df, n_points=9)

# 或让函数自动推断（数据行数为偶数时）
df_a, df_b = split_groups(df)
```

### Step 4: 增压器对比分析

`compare_turbochargers()` 从 7 个维度加权评分：

| 维度 | 权重 | 说明 |
|------|------|------|
| 低速扭矩（1000-1500rpm） | ×2.0 | 起步响应，最重要 |
| 燃油经济性（BSFC） | ×2.0 | 越低越好，排除 1000rpm 异常点 |
| 涡轮转速余量（≥4000rpm） | ×1.5 | 余量大则安全 |
| WG 开度（≥3000rpm） | ×1.5 | 越小废气利用率越高 |
| 排气温度 | ×1.0 | 越低越好 |
| 峰值扭矩 | ×1.0 | 越高越好 |

```python
results = compare_turbochargers(df_a, df_b, "博马", "奕森")
print(results["scores"])    # {'博马': 8.5, '奕森': 6.0}
print(results["winner"])    # '博马'
```

### Step 5: 高原能力评估

关键公式：

```
Speed_alt = Speed_0 × √(P0 / P_alt)
P_alt = 101.325 × (1 - 0.0065 × h / 288.15) ^ 5.255
```

```python
ha = assess_high_altitude(df_a, df_b, "博马", "奕森", altitude_m=3000)
print(ha["博马"]["safety"])   # "✅ 安全" / "⚠️ 可接受" / "❌ 高风险"
```

### Step 6: 可视化

`plot_comparison(results)` 自动生成 2×3 子图：
- 扭矩对比 / BSFC对比 / 增压器转速（含限制线）
- 排气温度 / 增压压力 / WG开度

会根据数据存在性自动调整子图数量。

### Step 7: 报告生成

`generate_text_report(results, altitude_results)` 返回 Markdown 格式的完整报告：
- 📊 基本数据表格
- 🏆 综合评分（含权重说明）
- 📈 关键曲线解读
- 🏔️ 高原能力评估（如提供）
- 💡 综合建议（含风险提示）

## 关键公式与注意事项

### ✅ 增压比公式
```
增压比 = 增压压力(kPa) / 标准大气压(101.325 kPa)
```
> ❌ 不是 增压压力 / 排气背压

### ✅ 高原转速推算
```
Speed_alt = Speed_0 × √(P0 / P_alt)
```
> 使用前需用户确认增压器限制值和评估海拔

### ⚠️ BSFC 异常值
1000rpm 的 BSFC 值可能异常高（如 494 g/kWh vs 351 g/kWh），分析时 `compare_turbochargers()` 自动排除 1000rpm 数据点。

### ⚠️ WG 开度解读
| WG 开度 | 含义 |
|---------|------|
| < 10% | ✅ 匹配优秀，废气能量利用率高 |
| 10~20% | ⚡ 匹配良好 |
| > 20% | ⚠️ 匹配效率低，需要放掉大量废气 |

用辅助函数直接评估：
```python
print(wg_efficiency_assessment(wg_values, rpm_values))
```

### ⚠️ 增压器转速安全余量
| 余量 | 判定 |
|------|------|
| > 30000 rpm | ✅ 安全 |
| 15000~30000 rpm | ⚠️ 可接受 |
| < 15000 rpm | ❌ 高风险 |

## 数据清洗要点

```python
# 典型清洗流程
df = load_excel(fp, sheet_name="Sheet3", skiprows=1)  # 跳过单位行
df = clean_columns(df)                                 # 清理列名(换行符/空格)
df = ensure_numeric(df)                                # 转数值类型
```

常见问题：
1. **单位行** — Excel 第二行是单位，用 `skiprows=1`
2. **列名含换行符** — `clean_columns()` 自动处理
3. **数值为 object 类型** — `ensure_numeric()` 自动转换
4. **合并单元格** — 先 `df.ffill()` 填充

## 标准大气压参考

| 海拔 | 大气压(kPa) | 与海平面比值 |
|------|-------------|-------------|
| 海平面 0m | 101.325 | 1.000 |
| 1000m | 89.9 | 0.887 |
| 2000m | 79.5 | 0.785 |
| 3000m | 70.1 | 0.692 |
| 4000m | 61.6 | 0.608 |

## 列名检测参考

`engine_analysis.py` 内置的 `COLUMN_PATTERNS` 覆盖以下信号类型：

| 信号类型 | COLUMN_PATTERNS 键名 | 关键词（按优先级） |
|----------|---------------------|-------------------|
| 转速 | `rpm` | 转速, rpm, SPEED, EngineSpeed, DynoSpeed |
| 扭矩 | `torque` | 扭矩, Torque, TORQUE, DynoTorque |
| BSFC | `bsfc` | BSFC, 燃油消耗率, FuelCOSP |
| 增压器转速 | `turbo_speed` | 增压器转速, TURBOSPEED, Trbch_N |
| 增压压力 | `boost` | 增压压力, Boost, BSTC_pActBoostPress, VBOOST, P3 |
| 排气温度 | `egt` | 排气温度, EGT, T_EXH, EXHT_tMnfdTemp |
| 排气背压 | `backpressure` | 背压, FT_TACT, P_EXH |
| WG 开度 | `wg` | WG开度, EWGC_rActlPos |
| 进气流量 | `airflow` | 进气流量, AirFlow, AFS_dm |
| 功率 | `power` | 功率, Power, BrakePower |

## CLI 快速调试

脚本支持命令行调用（无需写 Python）：

```bash
python /Users/yangdiandian/.hermes/skills/data-science/engine-data-analysis/scripts/engine_analysis.py \
    "数据文件.xlsx" "博马" "奕森" 9
```

## 常见问题

### Q: 列名检测不到怎么办？
A: 函数会自动模糊匹配，如果仍匹配不上，手动指定列名：
```python
results = compare_turbochargers(df_a, df_b, rpm_col="我的转速列", torque_col="我的扭矩列")
```

### Q: 数据不是 9 行一组怎么办？
A: 调整 `n_points` 参数，或用 `df.shape` 先确认行数。

### Q: 如何导出图片到指定路径？
```python
plot_comparison(results, save_path="./output.png")
```

### Q: 只想算增压比？
```python
from engine_analysis import calculate_pressure_ratio
pr = calculate_pressure_ratio(boost_kpa_values, altitude_m=3000)
```

## 文件路径约定

- 用户数据文件：`~/Documents/01-Work/*.xlsx`
- 图表输出：工作目录或 `~/Documents/`
- 报告输出：Markdown 格式

> ⚠️ 工具使用：DeepSeek 不支持 vision_analyze，Excel 数据直接用 pandas 读取；文件路径不要在代码中硬编码，通过参数传入。

## 发动机数据名称参考

> 来源：`260601-发动机测量数据名称_v1.0.xlsx`，涵盖汽油机与柴油机台架测试数据命名规范。

### 汽油机增压器关键信号

| 信号名称 | 中文含义 |
|----------|----------|
| `BSTC_pActBoostPress` | 实际增压压力 |
| `TURBOSPEED` | 涡轮转速 |
| `VBOOST` | 增压压力 |
| `EWGC_rActlPos` | 废气门实际位置 |
| `TurbineInPressG` | 涡轮入口表压 |
| `P_Turbine_in` | 涡轮入口压力 |

完整的汽油机/柴油机数据名称清单见原文档，这里只列出增压器分析最相关的信号。

> ⚠️ 增压器相关关键信号：`BSTC_pActBoostPress`（实际增压压力）、`TURBOSPEED`（涡轮转速）、`VBOOST`（增压压力）、`EWGC_rActlPos`（废气门实际位置）、`TurbineInPressG`（涡轮入口表压）、`P_Turbine_in`（涡轮入口压力）

### 柴油机增压器关键信号

| 信号名称 | 中文含义 |
|----------|----------|
| `Trbch_N` | 涡轮增压器转速 |
| `P3` | 增压空气压力 |
| `P_Intake` | 进气歧管压力 |
| `FT_TACT` | 排气背压 |

> ⚠️ 柴油机增压器关键信号：`Trbch_N`（涡轮增压器转速）、`P3`（增压空气压力）、`P_Intake`（进气歧管压力）、`FT_TACT`（排气背压）
