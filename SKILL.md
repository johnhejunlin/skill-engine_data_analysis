---
name: engine-data-analysis
description: Analyze engine performance data (dyno/bench test data) — turbocharger matching, torque/BSFC/boost comparison, high-altitude capability assessment, combustion analysis (COV/AI50/spark/knock/VVT), data visualization, and performance report generation. Use when the user asks about engine performance data, turbocharger comparison, dyno data analysis, combustion analysis, or any .xlsx/.csv engine test files.
---

# 发动机数据分析

分析发动机台架测试数据（dyno data）—— 增压器匹配对比、扭矩/油耗/增压压力分析、燃烧特性分析（COV/AI50/点火角/爆震/VVT）、高原能力评估、数据可视化。

## 触发条件

当用户提及以下任何内容时，应加载本 skill：
- 发动机 / engine / 台架 / dyno / 增压器 / turbo / 涡轮
- 对比两个或多个部件的性能数据
- 分析 .xlsx / .csv 格式的测试数据
- 评估高原/高海拔性能
- BSFC / 燃油消耗率 / 扭矩 / 增压压力 / 排气温度 / 背压
- **COV / 循环变动 / 燃烧稳定性**
- **AI50 / CA50 / 燃烧相位**
- **点火角 / 点火提前角 / 点火退角 / MBT**
- **爆震 / Knock**
- **VVT / VCT / 可变气门正时 / 凸轮轴**
- **IMEP / 平均有效压力**
- **功率 / 油耗分析 / 万有特性**

## 快速入口

核心分析逻辑已封装到 `scripts/engine_analysis.py`，引入后直接调用即可：

```python
import sys
sys.path.insert(0, "/Users/yangdiandian/.hermes/skills/data-science/engine-data-analysis/scripts")
from engine_analysis import *
```

### A/B 增压器对比分析（推荐）

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

### 单发动机万有特性分析（非对比场景）

当数据是单台发动机的万有特性（全负荷 + 部分负荷稳态点）时，使用 `single_engine_analysis()`：

```python
out = single_engine_analysis(
    filepath="260410-B15HTC万有数据.csv",
    encoding="gbk",            # CSV 编码（常见gbk/latin-1）
    header_rows=5,             # 跳过的元数据行数
    turbo_speed_limit=250000,
    altitude_m=3000,
    save_plot="/tmp/engine_analysis.png",
)
print(out["report"])
```

### 燃烧特性分析（功率/油耗/COV/AI50/点火角/爆震/VVT）

当数据包含燃烧相关信号时，使用 `single_engine_full_analysis()` 一站式分析：

```python
from engine_analysis import *

out = single_engine_full_analysis(
    filepath="260410-B15HTC万有数据.csv",
    encoding="gbk",
    header_rows=5,
    turbo_speed_limit=250000,
    altitude_m=3000,
    save_plot_performance="/tmp/performance.png",
    save_plot_combustion="/tmp/combustion.png",
)
print(out["report"])
```

也可直接调用 `single_engine_combustion_analysis()`：

```python
import sys
sys.path.insert(0, "/Users/yangdiandian/.hermes/skills/data-science/engine-data-analysis/scripts")
from engine_analysis import *

# 加载数据
df = load_csv("260410-B15HTC万有数据.csv", encoding="gbk", header_rows=5)
df = ensure_numeric(df)

# 检测列名
rpm_col = detect_column(df, "rpm")   # → 'DynoSpeed_Avg'
torque_col = detect_column(df, "torque")  # → 'DynoTorque_Avg'
col_map = detect_all_columns(df)     # → {'bsfc': 'BSFC_Avg', 'cov': 'IMEP1CO_Avg', 'ai50': 'AI501_Avg', ...}

# 燃烧特性分析
out = single_engine_combustion_analysis(
    df, rpm_col, torque_col, col_map,
    turbo_speed_limit=250000,
    altitude_m=3000,
    save_plot="/tmp/combustion.png",
)
print(out["report"])
```

**自动检测的燃烧信号（有则分析，无则跳过）：**

| 信号 | 列名关键词 | 说明 |
|-----|-----------|------|
| COV | `IMEP1CO_Avg`, `cov`, `CoV` | 循环变动系数，<3%稳定，>5%不稳定 |
| AI50 | `AI501_Avg`, `CA50`, `MFB50` | 燃烧相位，最佳6-12°CA ATDC |
| 点火角 | `SPK_dgActSpkAdv_Avg` | 实际点火提前角 (°BTDC) |
| MBT点火角 | `SPK_dgMBTSpkAdv_Avg` | MBT点火角 (°BTDC) |
| 点火退角 | `SPK_dgDltFromMBT_Avg` | 从MBT退角 (°CA)，退角>5°可能受爆震限制 |
| 爆震窗口 | `knockWndStrAng_Avg` | 爆震窗口开始角 |
| VVT | `VVT`, `CamPhs`, `CamPos` | 可变气门正时 |
| 油耗量 | `Fuel_FuelConsume_Avg` | 燃油消耗量 (kg/h) |
| IMEP | `IMEP1_Avg`, `IMEP` | 平均有效压力 (bar) |

**注意：** CSV 文件（.csv）用 `load_csv()` 读取，Excel 文件（.xlsx/.xls）用 `load_excel()`。


### 分步分析（A/B 对比）

```python
# 1. 加载
df = load_excel("数据.xlsx", sheet_name="Sheet3", skiprows=1)
# 或 CSV:  df = load_csv("数据.csv", encoding="gbk", header_rows=5)
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

## CSV 文件处理（特殊注意事项）

台架数据经常以 CSV 格式输出，常见陷阱：

### 编码问题
```python
# 大多数国内台架 CSV 使用 GBK/GB2312 编码
df = load_csv("数据.csv", encoding="gbk", header_rows=5)

# 如果 GBK 报错，尝试 latin-1（接受任何字节）
# 但 latin-1 后的中文字段可能乱码，数值不受影响
```

### 多行表头结构
典型台架 CSV 有 5~8 行表头信息，结构如下：

| 行号 | 内容 | 说明 |
|-----|------|------|
| 1~4 | Logger description, Log period, etc. | 元数据，跳过 |
| 5 (header) | Time, Time, Time, DynoSpeed_Avg, DynoTorque_Avg, ... | 真正的列名 |
| 6 (units) | Date, Time, ms, rev/min, Nm, kW, ... | 单位行，跳过 |
| 7 (type) | Raw, Raw, Raw, Average, Average, ... | 数据类型，跳过 |
| 8+ | 实际数据 | |

```python
# 对复杂表头 CSV，正确的读取方式：
raw = pd.read_csv(filepath, encoding='gbk', header=5)  # row 5 = 列名
# 或：
col_names = pd.read_csv(filepath, encoding='gbk', header=None, nrows=1, skiprows=5)
raw = pd.read_csv(filepath, encoding='gbk', header=5, names=col_names.iloc[0])
```

### 列名去重
ETAS INCA 等工具输出的 CSV 可能有多列同名（如 3 个 "Time" 列），pandas 会自动加 `.1` `.2` 后缀：
```python
# 前 3 列可能是: Time, Time.1, Time.2 — 对应 Date/Time/ms 信号
# 从第 4 列（索引3）开始才是真正的台架信号
df = raw.iloc[:, 3:]  # 跳过前3个时间列
```

## 单发动机万有特性分析（非 A/B 对比）

当数据只有一台发动机的万有特性数据（非增压器对比场景），分析重点是：

### 典型输出指标
- **扭矩特性** — 全负荷外特性曲线 + 部分负荷点
- **BSFC 经济区** — 最低 BSFC 及其对应转速/扭矩、经济区分布
- **增压器工作线** — 各转速点对应的涡轮转速、检查是否接近限制
- **WG 开度分布** — 全速段 WG 开度均值，评估匹配效率
- **增压压力地图** — 转速-扭矩面上的增压压力分布
- **排气温度** — 最高排温点、是否超出限值

### 单机分析示例

```python
from engine_analysis import *

# 加载 CSV 数据
df = load_csv("260410-B15HTC万有数据.csv", encoding="gbk", header_rows=5)
df = clean_columns(df)
df = ensure_numeric(df)

# 提取关键信号
df_clean = pd.DataFrame()
df_clean['rpm'] = pd.to_numeric(df['DynoSpeed_Avg'], errors='coerce')
df_clean['torque'] = pd.to_numeric(df['DynoTorque_Avg'], errors='coerce')
# ... 提取其他信号

# 按转速分组合并稳态点
df_clean['rpm_group'] = np.round(df_clean['rpm'] / 50) * 50
summary = df_clean.groupby('rpm_group').agg({
    'torque': ['mean', 'max'],
    'bsfc': 'mean',
    'boost': 'mean',
    'wg': 'mean',
    'egt': 'mean',
    'turbo_speed': 'mean',
})

# 高原评估
ha = assess_high_altitude_single(speed_values, rpm_values, altitude_m=3000)
```

### 评分参考

| 指标 | 优秀 | 良好 | 一般 | 差 |
|------|------|------|------|----|
| 最低 BSFC | < 230 g/kWh | 230~250 | 250~270 | > 270 |
| 涡轮转速余量（海平面） | > 50k rpm | 30k~50k | 15k~30k | < 15k |
| 低速扭矩（1000rpm） | > 100 Nm | 80~100 | 60~80 | < 60 |
| WG 高转速开度 | < 30% | 30~50% | 50~70% | > 70% |
| 最高排温 | < 800°C | 800~850 | 850~900 | > 900°C |

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
5. **CSV 多行表头** — 用 `load_csv()` 的 `header_rows` 参数指定跳过行数

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
| BSFC | `bsfc` | BSFC, 燃油消耗率, FuelCOSP, FB_RATE |
| 增压器转速 | `turbo_speed` | 增压器转速, TURBOSPEED, Trbch_N, TurboSpeed, turbine |
| 增压压力 | `boost` | 增压压力, Boost, BSTC_pActBoostPress, VBOOST, P3, P_Intake |
| 排气温度 | `egt` | 排气温度, EGT, exhaust, T_EXH, EXHT_tMnfdTemp, MEANTEXH |
| 排气背压 | `backpressure` | 背压, Back, FT_TACT, P_EXH, ExhP_pUpFstCat |
| WG 开度 | `wg` | WG开度, WG, wastegate, EWGC_rActlPos, EWGC_rPosDsrd, BCEW_rDesWGPos |
| 进气流量 | `airflow` | 进气流量, AirFlow, AFS_dm |
| 功率 | `power` | 功率, Power, BrakePower |
| 进气温度 | `intake_temp` | 进气温度, T_Intake, T_AIR, T_ACS |
| **COV** | **`cov`** | **COV, IMEPCOV, IMEP1CO, CoV, 循环变动** |
| **AI50** | **`ai50`** | **AI50, CA50, MFB50, AI501, 燃烧相位** |
| **点火角** | **`spark_act`** | **SPK_dgActSpkAdv, SPK_dgMainSpkAdv, 点火角, 点火提前角** |
| **MBT点火角** | **`spark_mbt`** | **SPK_dgMBTSpkAdv, MBT** |
| **点火退角** | **`spark_delta`** | **SPK_dgDltFromMBT, DltFromMBT, 点火退角** |
| **爆震** | **`knock`** | **Knock, KNK, knockWnd, 爆震** |
| **VVT** | **`vvt`** | **VVT, VCT, Cam, CamPhs, 进气门, 排气门** |
| **油耗量** | **`fuel_flow`** | **Fuel_FuelConsume, FuelMassFlow, 油耗量** |
| **IMEP** | **`imep`** | **IMEP, 平均有效压力** |

> ⚠️ ETAS INCA 输出的信号名通常带 `_Avg` 后缀（如 `DynoSpeed_Avg`、`BSTC_pActBoostPress_Avg`、`EWGC_rActlPos_Avg`、`EXHT_tMnfdTemp_Avg`、`TURBOSPEED_Avg`、`IMEP1CO_Avg`、`AI501_Avg`、`SPK_dgActSpkAdv_Avg`、`Fuel_FuelConsume_Avg`），列名检测时包含 `_Avg` 也能匹配到

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
