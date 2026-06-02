"""
engine_analysis.py — 发动机台架性能数据分析工具集

分析增压器匹配对比、扭矩/BSFC/增压压力、高原能力评估、数据可视化。
所有函数接受 DataFrame 和列名参数，带自动列名检测和错误处理。

用法示例：
    from engine_analysis import *
    df = load_excel("data.xlsx")
    df_a, df_b = split_groups(df, n_points=9)
    results = compare_turbochargers(df_a, df_b)
    plot_comparison(results)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional, Dict, Tuple, List

# ────────────────────────────────────────────────────────────
# 常量
# ────────────────────────────────────────────────────────────

# 标准大气压 (kPa)
ATM_STANDARD = 101.325

# 各海拔大气压 (基于 ISO 2533 标准大气)
ALTITUDE_PRESSURE = {
    0:     101.325,
    1000:   89.9,
    2000:   79.5,
    3000:   70.1,
    4000:   61.6,
}

# 默认增压器转速限制 (rpm) — 需用户根据供应商确认
TURBO_SPEED_LIMIT_DEFAULT = 250000

# 默认转速点
DEFAULT_RPM_POINTS = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]

# 列名关键词映射 (检测顺序 = 优先匹配顺序)
COLUMN_PATTERNS = {
    "rpm":     ["转速", "rpm", "RPM", "SPEED", "EngineSpeed", "DynoSpeed", "Epm_nEng"],
    "torque":  ["扭矩", "Torque", "TORQUE", "DynoTorque"],
    "bsfc":    ["BSFC", "燃油消耗率", "FuelCOSP", "FB_RATE"],
    "turbo_speed": ["增压器转速", "TURBOSPEED", "Trbch_N", "TurboSpeed",
                    "turbine", "Turbo", "涡轮转速"],
    "boost":   ["增压压力", "Boost", "BOOST", "BSTC_pActBoostPress",
                "VBOOST", "P3", "P_Intake"],
    "egt":     ["排气温度", "EGT", "egt", "exhaust", "T_EXH", "EXHT_tMnfdTemp",
                "MEANTEXH"],
    "backpressure": ["背压", "Back", "back", "FT_TACT", "P_EXH", "ExhP_pUpFstCat"],
    "wg":      ["WG开度", "WG", "wg", "wastegate", "EWGC_rActlPos",
                "EWGC_rPosDsrd", "BCEW_rDesWGPos"],
    "airflow": ["进气流量", "AirFlow", "AFS_dm", "air", "流量"],
    "power":   ["功率", "Power", "POWER", "BrakePower"],
    "intake_temp": ["进气温度", "进气歧管温度", "T_Intake", "T_AIR", "T_AIR_IN",
                    "T_ACS"],
}

# ────────────────────────────────────────────────────────────
# 1. 数据加载与清洗
# ────────────────────────────────────────────────────────────

def load_excel(filepath: str, sheet_name: Optional[str] = None,
               skiprows: int = 0) -> pd.DataFrame:
    """读取 Excel 台架数据，支持自动探测 sheet 名。

    Args:
        filepath: Excel 文件路径
        sheet_name: sheet 名称，为 None 时打印所有可用 sheet
        skiprows: 跳过前 N 行 (如单位行)

    Returns:
        DataFrame

    用法:
        df = load_excel("data.xlsx", sheet_name="Sheet3", skiprows=1)
    """
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    xl = pd.ExcelFile(p)
    print(f"📋 可用 sheet: {xl.sheet_names}")

    if sheet_name is None and len(xl.sheet_names) == 1:
        sheet_name = xl.sheet_names[0]
        print(f"→ 使用唯一 sheet: {sheet_name}")
    elif sheet_name is None:
        sheet_name = xl.sheet_names[0]
        print(f"→ 默认使用第一个 sheet: {sheet_name}")

    df = pd.read_excel(xl, sheet_name=sheet_name, skiprows=skiprows)
    print(f"→ 读取完成: {df.shape[0]} 行 x {df.shape[1]} 列")
    return df


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """清理列名: 去除换行符、首尾空格、统一命名。"""
    df = df.copy()
    df.columns = (
        df.columns
        .str.replace('\n', '', regex=False)
        .str.replace('\r', '', regex=False)
        .str.strip()
    )
    return df


def ensure_numeric(df: pd.DataFrame,
                   exclude_cols: Optional[List[str]] = None) -> pd.DataFrame:
    """将 DataFrame 中的 object 列转为数值类型 (无法转换的置为 NaN)。"""
    df = df.copy()
    ex = set(exclude_cols or [])
    for col in df.columns:
        if col in ex:
            continue
        if df[col].dtype == 'object':
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def inspect_data(df: pd.DataFrame, head_n: int = 20) -> None:
    """打印数据概览: 列名、前若干行、数据类型。"""
    print(f"📐 列名 ({len(df.columns)}): {df.columns.tolist()}")
    print(f"\n📄 前 {head_n} 行:")
    print(df.head(head_n).to_string())
    print(f"\n🔢 数据类型:")
    print(df.dtypes)


# ────────────────────────────────────────────────────────────
# 2. 列名检测
# ────────────────────────────────────────────────────────────

def detect_column(df: pd.DataFrame, key: str,
                  case_sensitive: bool = False) -> Optional[str]:
    """在 DataFrame 中根据关键词模式检测目标列名 (模糊匹配)。

    Args:
        df: 目标 DataFrame
        key: COLUMN_PATTERNS 中的键名 (如 'rpm', 'torque', 'bsfc')
        case_sensitive: 是否大小写敏感

    Returns:
        匹配到的列名，或 None

    示例:
        rpm_col = detect_column(df, "rpm")  # 自动找到转速列
    """
    if key not in COLUMN_PATTERNS:
        raise ValueError(f"未知列类型 '{key}'，可用: {list(COLUMN_PATTERNS.keys())}")

    patterns = COLUMN_PATTERNS[key]
    columns = df.columns.tolist()

    if not case_sensitive:
        cols_lower = {c: c.lower() for c in columns}
        patterns = [p.lower() for p in patterns]
    else:
        cols_lower = {c: c for c in columns}

    # 优先完全匹配
    for col in columns:
        col_check = col if case_sensitive else col.lower()
        if col_check in patterns:
            return col

    # 再部分匹配 (包含关键词)
    for col in columns:
        col_check = col if case_sensitive else col.lower()
        for pat in patterns:
            if pat in col_check or col_check in pat:
                return col

    # 最后子串匹配 (separator 分割后匹配)
    for col in columns:
        col_check = col if case_sensitive else col.lower()
        parts = set(col_check.replace('_', ' ').replace('.', ' ').split())
        for pat in patterns:
            pat_parts = set(pat.replace('_', ' ').replace('.', ' ').split())
            if pat_parts & parts:
                return col
            # 单项匹配 (长度≥3 避免单字母误配, 如 'p' in '(rpm)')
            for pp in pat_parts:
                if len(pp) < 3:
                    continue
                for cp in parts:
                    if len(cp) < 3:
                        continue
                    if pp in cp or cp in pp:
                        return col

    return None


def detect_all_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """检测 DataFrame 中所有已知类型的列。

    Returns:
        {类型键: 列名} 字典

    示例:
        cols = detect_all_columns(df)
        # cols = {'rpm': '转速', 'torque': '扭矩(Bm)', 'bsfc': None, ...}
    """
    result = {}
    for key in COLUMN_PATTERNS:
        col = detect_column(df, key)
        if col is not None:
            result[key] = col
    return result


# ────────────────────────────────────────────────────────────
# 3. 数据分隔 (A/B 两组上下排列的情况)
# ────────────────────────────────────────────────────────────

def split_groups(df: pd.DataFrame, n_points: Optional[int] = None,
                 rpm_col: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """将上下排列的两组数据按行分为 A、B 两组。

    常见场景: Excel 中前 N 行是增压器 A，后 N 行是增压器 B。

    Args:
        df: 原始 DataFrame
        n_points: 每组行数。为 None 时尝试按 DEFAULT_RPM_POINTS 推断
        rpm_col: 转速列名，用于辅助推断

    Returns:
        (df_a, df_b)

    用法:
        df_a, df_b = split_groups(df, n_points=9)
        df_a, df_b = split_groups(df, rpm_col="转速")  # 自动推断
    """
    if n_points is not None:
        m = len(df) // 2
        df_a = df.iloc[:n_points].copy().reset_index(drop=True)
        df_b = df.iloc[n_points:n_points * 2].copy().reset_index(drop=True)
        print(f"→ A 组: {len(df_a)} 行, B 组: {len(df_b)} 行")
        return df_a, df_b

    # 尝试自动推断 — 假设数据行数是标准转速点的 2 倍
    total = len(df)
    if total % 2 == 0:
        half = total // 2
        if rpm_col is not None and rpm_col in df.columns:
            # 看换行位置是否是标准 rpm 点的结束
            test = df[rpm_col].values[:half]
            # 如果前半部分比较连续/完整
            pass
        df_a = df.iloc[:half].copy().reset_index(drop=True)
        df_b = df.iloc[half:].copy().reset_index(drop=True)
        print(f"→ 自动推断: A 组 {len(df_a)} 行, B 组 {len(df_b)} 行")
        return df_a, df_b

    raise ValueError(
        f"无法自动推断分组行数 (数据总行数 {total} 不是偶数)。"
        f"请指定 n_points 参数。"
    )


# ────────────────────────────────────────────────────────────
# 4. 增压器对比分析
# ────────────────────────────────────────────────────────────

def _safe_float(arr):
    """安全转为 float ndarray，non-numeric 置 NaN。"""
    return pd.to_numeric(pd.Series(arr), errors='coerce').values.astype(float)


def compare_turbochargers(df_a: pd.DataFrame, df_b: pd.DataFrame,
                          name_a: str = "A", name_b: str = "B",
                          rpm_col: Optional[str] = None,
                          torque_col: Optional[str] = None,
                          turbo_speed_limit: int = TURBO_SPEED_LIMIT_DEFAULT
                          ) -> Dict:
    """双增压器全面对比分析。

    Args:
        df_a: 增压器 A 的数据
        df_b: 增压器 B 的数据
        name_a: 增压器 A 名称
        name_b: 增压器 B 名称
        rpm_col: 转速列名；为 None 时自动检测
        torque_col: 扭矩列名；为 None 时自动检测
        turbo_speed_limit: 增压器转速限制值 (rpm)，默认 250000

    Returns:
        Dict 包含:
          - summary: 关键指标汇总
          - scores: 加权评分
          - details: 各维度详细数据
          - col_map: 列名映射
          - names: (name_a, name_b)

    用法:
        results = compare_turbochargers(df_a, df_b, "博马", "奕森")
        print(results["summary"])
        print(results["scores"])
    """
    # --- 列名检测 ---
    rpm_col = rpm_col or detect_column(df_a, "rpm")
    torque_col = torque_col or detect_column(df_a, "torque")

    if rpm_col is None:
        raise ValueError("无法检测到转速列，请通过 rpm_col= 指定")
    if torque_col is None:
        raise ValueError("无法检测到扭矩列，请通过 torque_col= 指定")

    col_map = detect_all_columns(df_a)
    col_map["rpm"] = rpm_col
    col_map["torque"] = torque_col

    # --- 安全提取数值 ---
    rpm = _safe_float(df_a[rpm_col].values)
    torque_a = _safe_float(df_a[torque_col].values)
    torque_b = _safe_float(df_b[torque_col].values)

    print(f"📊 列名映射: {col_map}")

    # ── 1. 扭矩分析 ──
    low_end = rpm <= 1500
    tq_low_a = np.nanmean(torque_a[low_end])
    tq_low_b = np.nanmean(torque_b[low_end])
    tq_peak_a = np.nanmax(torque_a)
    tq_peak_b = np.nanmax(torque_b)
    tq_avg_a = np.nanmean(torque_a)
    tq_avg_b = np.nanmean(torque_b)
    tq_peak_rpm_a = rpm[np.nanargmax(torque_a)] if not np.all(np.isnan(torque_a)) else 0
    tq_peak_rpm_b = rpm[np.nanargmax(torque_b)] if not np.all(np.isnan(torque_b)) else 0

    # ── 2. BSFC ──
    bsfc_a = bsfc_b = bsfc_main_a = bsfc_main_b = None
    if "bsfc" in col_map:
        bsfc_a = _safe_float(df_a[col_map["bsfc"]].values)
        bsfc_b = _safe_float(df_b[col_map["bsfc"]].values)
        # 排除 1000rpm (异常偏高)
        bsfc_main = rpm > 1000
        bsfc_main_a = np.nanmean(bsfc_a[bsfc_main])
        bsfc_main_b = np.nanmean(bsfc_b[bsfc_main])

    # ── 3. 增压器转速 ──
    speed_a = speed_b = speed_margin_a = speed_margin_b = None
    if "turbo_speed" in col_map:
        speed_a = _safe_float(df_a[col_map["turbo_speed"]].values)
        speed_b = _safe_float(df_b[col_map["turbo_speed"]].values)
        speed_margin_a = turbo_speed_limit - np.nanmax(speed_a)
        speed_margin_b = turbo_speed_limit - np.nanmax(speed_b)

    # ── 4. 排气温度 ──
    egt_a = egt_b = egt_max_a = egt_max_b = egt_avg_a = egt_avg_b = None
    if "egt" in col_map:
        egt_a = _safe_float(df_a[col_map["egt"]].values)
        egt_b = _safe_float(df_b[col_map["egt"]].values)
        egt_max_a = np.nanmax(egt_a)
        egt_max_b = np.nanmax(egt_b)
        egt_avg_a = np.nanmean(egt_a)
        egt_avg_b = np.nanmean(egt_b)

    # ── 5. 增压压力 ──
    boost_a = boost_b = None
    if "boost" in col_map:
        boost_a = _safe_float(df_a[col_map["boost"]].values)
        boost_b = _safe_float(df_b[col_map["boost"]].values)

    # ── 6. WG 开度 ──
    wg_a = wg_b = wg_high_a = wg_high_b = None
    if "wg" in col_map:
        wg_a = _safe_float(df_a[col_map["wg"]].values)
        wg_b = _safe_float(df_b[col_map["wg"]].values)
        high_rpm = rpm >= 3000
        wg_high_a = np.nanmean(wg_a[high_rpm])
        wg_high_b = np.nanmean(wg_b[high_rpm])

    # ── 7. 背压 ──
    bp_a = bp_b = None
    if "backpressure" in col_map:
        bp_a = _safe_float(df_a[col_map["backpressure"]].values)
        bp_b = _safe_float(df_b[col_map["backpressure"]].values)

    # ── 8. 功率 ──
    power_a = power_b = None
    if "power" in col_map:
        power_a = _safe_float(df_a[col_map["power"]].values)
        power_b = _safe_float(df_b[col_map["power"]].values)

    # ── 评分 ──
    scores = {name_a: 0.0, name_b: 0.0}
    weights = {}

    # 低速扭矩 (权重 2.0)
    weights["低速扭矩"] = (2.0, name_a if tq_low_a > tq_low_b else name_b)
    if tq_low_a > tq_low_b:
        scores[name_a] += 2.0
    else:
        scores[name_b] += 2.0

    # BSFC — 越低越好 (权重 2.0)
    if bsfc_main_a is not None:
        if bsfc_main_a < bsfc_main_b:
            scores[name_a] += 2.0
            weights["燃油经济性"] = (2.0, name_a)
        elif bsfc_main_b < bsfc_main_a:
            scores[name_b] += 2.0
            weights["燃油经济性"] = (2.0, name_b)
        else:
            weights["燃油经济性"] = (2.0, "持平")

    # 涡轮转速 — 高速段 (≥4000rpm) 越低越好 (余量大) (权重 1.5)
    if speed_a is not None:
        high_end = rpm >= 4000
        spd_high_a = np.nanmean(speed_a[high_end])
        spd_high_b = np.nanmean(speed_b[high_end])
        if spd_high_a < spd_high_b:
            scores[name_a] += 1.5
            weights["涡轮转速余量"] = (1.5, name_a)
        elif spd_high_b < spd_high_a:
            scores[name_b] += 1.5
            weights["涡轮转速余量"] = (1.5, name_b)
        else:
            weights["涡轮转速余量"] = (1.5, "持平")

    # 排气温度 — 越低越好 (权重 1.0)
    if egt_avg_a is not None:
        if egt_avg_a < egt_avg_b:
            scores[name_a] += 1.0
            weights["排气温度"] = (1.0, name_a)
        elif egt_avg_b < egt_avg_a:
            scores[name_b] += 1.0
            weights["排气温度"] = (1.0, name_b)
        else:
            weights["排气温度"] = (1.0, "持平")

    # WG 开度 — 高转速段越小越好 (权重 1.5)
    if wg_high_a is not None:
        if wg_high_a < wg_high_b:
            scores[name_a] += 1.5
            weights["WG效率"] = (1.5, name_a)
        elif wg_high_b < wg_high_a:
            scores[name_b] += 1.5
            weights["WG效率"] = (1.5, name_b)
        else:
            weights["WG效率"] = (1.5, "持平")

    # 峰值扭矩 (权重 1.0)
    if tq_peak_a > tq_peak_b:
        scores[name_a] += 1.0
        weights["峰值扭矩"] = (1.0, name_a)
    elif tq_peak_b > tq_peak_a:
        scores[name_b] += 1.0
        weights["峰值扭矩"] = (1.0, name_b)
    else:
        weights["峰值扭矩"] = (1.0, "持平")

    winner = name_a if scores[name_a] > scores[name_b] else name_b

    # ── 打包结果 ──
    return {
        "names": (name_a, name_b),
        "winner": winner,
        "scores": scores,
        "weights": weights,
        "col_map": col_map,
        "rpm": rpm,
        "summary": {
            "torque_low":      (round(tq_low_a, 1), round(tq_low_b, 1)),
            "torque_peak":     (round(tq_peak_a, 1), round(tq_peak_b, 1)),
            "torque_peak_rpm": (int(tq_peak_rpm_a), int(tq_peak_rpm_b)),
            "torque_avg":      (round(tq_avg_a, 1), round(tq_avg_b, 1)),
            "bsfc_avg":        (round(bsfc_main_a, 1) if bsfc_main_a else None,
                                round(bsfc_main_b, 1) if bsfc_main_b else None),
            "speed_margin":    (round(speed_margin_a) if speed_margin_a else None,
                                round(speed_margin_b) if speed_margin_b else None),
            "egt_max":         (round(egt_max_a) if egt_max_a else None,
                                round(egt_max_b) if egt_max_b else None),
            "egt_avg":         (round(egt_avg_a, 1) if egt_avg_a else None,
                                round(egt_avg_b, 1) if egt_avg_b else None),
            "wg_high_avg":     (round(wg_high_a, 1) if wg_high_a else None,
                                round(wg_high_b, 1) if wg_high_b else None),
            "turbo_speed_limit": turbo_speed_limit,
        },
        "raw": {
            "torque_a": torque_a, "torque_b": torque_b,
            "bsfc_a": bsfc_a, "bsfc_b": bsfc_b,
            "speed_a": speed_a, "speed_b": speed_b,
            "egt_a": egt_a, "egt_b": egt_b,
            "boost_a": boost_a, "boost_b": boost_b,
            "wg_a": wg_a, "wg_b": wg_b,
            "bp_a": bp_a, "bp_b": bp_b,
            "power_a": power_a, "power_b": power_b,
        },
    }


# ────────────────────────────────────────────────────────────
# 5. 高原能力评估
# ────────────────────────────────────────────────────────────

def calc_altitude_pressure(altitude_m: float) -> float:
    """计算给定海拔的标准大气压 (kPa)。

    使用 ISO 2533 标准大气模型:
        P = 101.325 × (1 - 0.0065 × h / 288.15) ^ 5.255
    """
    return ATM_STANDARD * (1 - 0.0065 * altitude_m / 288.15) ** 5.255


def assess_high_altitude(df_a: pd.DataFrame, df_b: pd.DataFrame,
                         name_a: str = "A", name_b: str = "B",
                         altitude_m: float = 3000,
                         turbo_speed_limit: int = TURBO_SPEED_LIMIT_DEFAULT,
                         rpm_col: Optional[str] = None
                         ) -> Dict:
    """评估两款增压器在指定海拔的高原性能。

    关键公式:
        Speed_alt = Speed_0 × √(P0 / P_alt)
    其中 P0 = 101.325 kPa, P_alt 为对应海拔的大气压。

    Args:
        df_a / df_b: 两组增压器数据
        name_a / name_b: 名称
        altitude_m: 海拔高度 (米)
        turbo_speed_limit: 增压器转速限制值
        rpm_col: 转速列名

    Returns:
        Dict 包含高原评估结果

    用法:
        ha = assess_high_altitude(df_a, df_b, "博马", "奕森",
                                  altitude_m=3000)
    """
    rpm_col = rpm_col or detect_column(df_a, "rpm")
    if rpm_col is None:
        raise ValueError("无法检测到转速列")

    speed_col = detect_column(df_a, "turbo_speed")
    if speed_col is None:
        return {"error": "无法检测增压器转速列，无法评估高原能力"}

    rpm = _safe_float(df_a[rpm_col].values)
    speed_a = _safe_float(df_a[speed_col].values)
    speed_b = _safe_float(df_b[speed_col].values)

    P_alt = calc_altitude_pressure(altitude_m)
    ratio = np.sqrt(ATM_STANDARD / P_alt)

    speed_alt_a = speed_a * ratio
    speed_alt_b = speed_b * ratio

    max_a = np.nanmax(speed_alt_a)
    max_b = np.nanmax(speed_alt_b)
    margin_a = turbo_speed_limit - max_a
    margin_b = turbo_speed_limit - max_b

    def safety_label(margin):
        if margin > 30000:
            return "✅ 安全"
        elif margin > 15000:
            return "⚠️ 可接受"
        else:
            return "❌ 高风险"

    # 增压比分析 (如数据存在)
    boost_col = detect_column(df_a, "boost")
    pr_a = pr_b = None
    if boost_col is not None:
        boost_a = _safe_float(df_a[boost_col].values)
        boost_b = _safe_float(df_b[boost_col].values)
        pr_a = boost_a / P_alt
        pr_b = boost_b / P_alt

    return {
        "altitude_m": altitude_m,
        "P_alt_kPa": round(P_alt, 2),
        "P0_kPa": ATM_STANDARD,
        "speed_multiplier": round(ratio, 4),
        turbo_speed_limit: turbo_speed_limit,
        name_a: {
            "max_speed_alt": round(max_a),
            "margin": round(margin_a),
            "safety": safety_label(margin_a),
            "pressure_ratio_range": (
                (round(float(pr_a.min()), 3), round(float(pr_a.max()), 3))
                if pr_a is not None else None
            ),
        },
        name_b: {
            "max_speed_alt": round(max_b),
            "margin": round(margin_b),
            "safety": safety_label(margin_b),
            "pressure_ratio_range": (
                (round(float(pr_b.min()), 3), round(float(pr_b.max()), 3))
                if pr_b is not None else None
            ),
        },
    }


# ────────────────────────────────────────────────────────────
# 6. 数据可视化
# ────────────────────────────────────────────────────────────

def _setup_chinese_font():
    """设置 matplotlib 中文字体。macOS 优先用 PingFang。"""
    for font in ["PingFang SC", "Heiti TC", "Arial Unicode MS",
                  "Noto Sans CJK SC", "SimHei"]:
        try:
            plt.rcParams['font.family'] = [font, 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            fig, ax = plt.subplots()
            ax.set_title("测试")
            plt.close(fig)
            return
        except Exception:
            continue
    # fallback
    plt.rcParams['font.family'] = ['sans-serif']
    plt.rcParams['axes.unicode_minus'] = False


def plot_comparison(results: Dict, save_path: Optional[str] = None,
                    figsize: Tuple[int, int] = (16, 10)):
    """生成增压器对比图: 扭矩 / BSFC / 增压器转速 / EGT / 增压压力 / WG 开度。

    Args:
        results: compare_turbochargers() 返回值
        save_path: 图片保存路径，为 None 则显示
        figsize: 画布大小

    用法:
        plot_comparison(results, "/tmp/comparison.png")
    """
    _setup_chinese_font()

    name_a, name_b = results["names"]
    rpm = results["rpm"]
    r = results["raw"]
    sm = results["summary"]

    # 确定子图数量
    subplots = [1]  # 扭矩总是有
    labels = {1: "扭矩"}
    idx = 2
    for key, label in [("bsfc_a", "BSFC"), ("speed_a", "增压器转速"),
                       ("egt_a", "排气温度"), ("boost_a", "增压压力"),
                       ("wg_a", "WG开度")]:
        if r.get(key) is not None:
            subplots.append(idx)
            labels[idx] = label
            idx += 1

    n_plots = len(subplots)
    n_rows = (n_plots + 2) // 3  # 最多3列
    n_cols = min(n_plots, 3)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
    axes_flat = np.atleast_1d(axes).ravel()

    # 隐藏多余子图
    for i in range(n_plots, len(axes_flat)):
        axes_flat[i].set_visible(False)

    def _plot_ax(ax, y_a, y_b, title, ylabel="", ylim=None,
                 show_limit=None):
        if y_a is None or y_b is None:
            return
        ax.plot(rpm, y_a, 'o-', label=name_a, linewidth=1.5)
        ax.plot(rpm, y_b, 's-', label=name_b, linewidth=1.5)
        ax.set_title(title)
        ax.set_xlabel("转速 (rpm)")
        ax.set_ylabel(ylabel)
        if ylim:
            ax.set_ylim(ylim)
        if show_limit:
            ax.axhline(y=show_limit[0], color='r', linestyle='--',
                       alpha=0.5, label=show_limit[1])
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.ticklabel_format(style='plain', axis='y')

    # 1. 扭矩
    _plot_ax(axes_flat[0], r["torque_a"], r["torque_b"],
             f"扭矩对比 (Nm)", "Nm")

    # 2. BSFC
    if r["bsfc_a"] is not None:
        _plot_ax(axes_flat[1], r["bsfc_a"], r["bsfc_b"],
                 "BSFC 对比 (g/kWh)", "g/kWh")

    # 3. 增压器转速
    if r["speed_a"] is not None:
        _plot_ax(axes_flat[2], r["speed_a"], r["speed_b"],
                 "增压器转速 (rpm)", "rpm",
                 show_limit=(sm.get("turbo_speed_limit", 250000),
                             f"限制 {sm.get('turbo_speed_limit', 250000)} rpm"))

    # 4. EGT
    if r["egt_a"] is not None:
        _plot_ax(axes_flat[3], r["egt_a"], r["egt_b"],
                 "排气温度 (°C)", "°C")

    # 5. 增压压力
    if r["boost_a"] is not None:
        _plot_ax(axes_flat[4], r["boost_a"], r["boost_b"],
                 "增压压力 (kPa)", "kPa")

    # 6. WG 开度
    if r["wg_a"] is not None:
        _plot_ax(axes_flat[5], r["wg_a"], r["wg_b"],
                 "WG开度 (%)", "%")

    plt.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"📈 图表已保存: {save_path}")
    else:
        plt.show()
    plt.close()


# ────────────────────────────────────────────────────────────
# 7. 报告生成
# ────────────────────────────────────────────────────────────

def _fmt(val_a, val_b, unit="", better="higher"):
    """格式化两个值的对比行，返回 (显示字符串, 胜者)"""
    if val_a is None or val_b is None:
        return ("-", "-", "-")
    result = f"{val_a} vs {val_b}"
    if unit:
        result = f"{val_a}{unit} vs {val_b}{unit}"
    if better == "higher":
        win = name_a if val_a > val_b else name_b
    else:
        win = name_a if val_a < val_b else name_b
    return result, win


def generate_text_report(results: Dict,
                         altitude_results: Optional[Dict] = None) -> str:
    """生成文本格式分析报告。

    Args:
        results: compare_turbochargers() 返回值
        altitude_results: assess_high_altitude() 返回值 (可选)

    Returns:
        格式化的报告字符串

    用法:
        report = generate_text_report(results, altitude_results)
        print(report)
    """
    name_a, name_b = results["names"]
    sm = results["summary"]
    weights = results["weights"]
    scores = results["scores"]
    winner = results["winner"]

    lines = []
    _w = lines.append

    _w(f"## 🔧 增压器对比分析报告")
    _w(f"")
    _w(f"### 📊 基本数据")
    _w(f"")
    _w(f"| 指标 | {name_a} | {name_b} | 优劣 |")
    _w(f"|------|----------|----------|------|")

    rows = [
        ("峰值扭矩",
         f"{sm['torque_peak'][0]} Nm @ {sm['torque_peak_rpm'][0]}rpm",
         f"{sm['torque_peak'][1]} Nm @ {sm['torque_peak_rpm'][1]}rpm"),
        ("平均扭矩",
         f"{sm['torque_avg'][0]} Nm",
         f"{sm['torque_avg'][1]} Nm"),
    ]

    if sm["bsfc_avg"][0] is not None and sm["bsfc_avg"][1] is not None:
        winner_bsfc = (name_a if sm["bsfc_avg"][0] < sm["bsfc_avg"][1]
                       else name_b)
        rows.append(("平均BSFC",
                     f"{sm['bsfc_avg'][0]} g/kWh",
                     f"{sm['bsfc_avg'][1]} g/kWh",
                     f"⭐ {winner_bsfc} 省油"))

    if sm["speed_margin"][0] is not None and sm["speed_margin"][1] is not None:
        winner_margin = (name_a if sm["speed_margin"][0] > sm["speed_margin"][1]
                         else name_b)
        rows.append(("转速余量",
                     f"{sm['speed_margin'][0]:,} rpm",
                     f"{sm['speed_margin'][1]:,} rpm",
                     f"⭐ {winner_margin} 安全"))

    if sm["egt_max"][0] is not None and sm["egt_max"][1] is not None:
        winner_egt = (name_a if sm["egt_max"][0] < sm["egt_max"][1]
                      else name_b)
        rows.append(("最高排气温度",
                     f"{sm['egt_max'][0]}°C",
                     f"{sm['egt_max'][1]}°C",
                     f"⭐ {winner_egt} 热管理好"))

    if sm["wg_high_avg"][0] is not None and sm["wg_high_avg"][1] is not None:
        winner_wg = (name_a if sm["wg_high_avg"][0] < sm["wg_high_avg"][1]
                     else name_b)
        rows.append(("WG高转速均开度",
                     f"{sm['wg_high_avg'][0]}%",
                     f"{sm['wg_high_avg'][1]}%",
                     f"⭐ {winner_wg} 效率高"))

    for row in rows:
        _w(f"| {' | '.join(str(x) for x in row)} |")

    _w(f"")
    _w(f"### 🏆 综合评分")
    _w(f"")
    _w(f"| 维度 (权重) | {name_a} | {name_b} | 胜者 |")
    _w(f"|------------|----------|----------|------|")
    for dim, (w, w_winner) in weights.items():
        a_mark = "✅" if w_winner == name_a else ""
        b_mark = "✅" if w_winner == name_b else ""
        _w(f"| {dim} (×{w}) | {a_mark} | {b_mark} | {w_winner} |")

    _w(f"| **总分** | **{scores[name_a]}** | **{scores[name_b]}** | **🏆 {winner}** |")

    _w(f"")
    _w(f"### 📈 关键曲线解读")
    _w(f"")
    # 自动生成解读骨架
    tq_low_a, tq_low_b = sm["torque_low"]
    _w(f"1. **低速段 (1000-1500rpm)** — "
       f"平均扭矩 {tq_low_a} Nm vs {tq_low_b} Nm, "
       f"{'👍' if tq_low_a > tq_low_b else '👍'}{name_a if tq_low_a > tq_low_b else name_b} 起步响应更好")
    _w(f"2. **中速段 (2000-3000rpm)** — "
       f"峰值扭矩 {sm['torque_peak'][0]} Nm @ {sm['torque_peak_rpm'][0]}rpm "
       f"vs {sm['torque_peak'][1]} Nm @ {sm['torque_peak_rpm'][1]}rpm")
    _w(f"3. **高速段 (3500-5000rpm)** — "
       f"关注增压器转速余量和 WG 开度效率")

    # 高原
    if altitude_results and "error" not in altitude_results:
        _w(f"")
        _w(f"### 🏔️ 高原能力评估 ({altitude_results['altitude_m']}m 海拔)")
        _w(f"")
        _w(f"| 指标 | {name_a} | {name_b} |")
        _w(f"|------|----------|----------|")
        d_a = altitude_results[name_a]
        d_b = altitude_results[name_b]
        _w(f"| 预计最高增压器转速 | {d_a['max_speed_alt']:,} rpm | {d_b['max_speed_alt']:,} rpm |")
        _w(f"| 安全余量 | {d_a['margin']:,} rpm | {d_b['margin']:,} rpm |")
        _w(f"| 安全性 | {d_a['safety']} | {d_b['safety']} |")
        if d_a.get("pressure_ratio_range") and d_b.get("pressure_ratio_range"):
            _w(f"| 增压比 (全速段) | {d_a['pressure_ratio_range'][0]}~{d_a['pressure_ratio_range'][1]} | "
               f"{d_b['pressure_ratio_range'][0]}~{d_b['pressure_ratio_range'][1]} |")
        _w(f"")
        _w(f"> 关键公式: Speed_alt = Speed_0 × √(P0 / P_alt)")
        _w(f"> P_alt = {altitude_results['P_alt_kPa']} kPa, "
           f"转速放大系数 = {altitude_results['speed_multiplier']}×")

    _w(f"")
    _w(f"### 💡 综合建议")
    _w(f"")
    _w(f"- **推荐方案:** {winner}")
    _w(f"- **核心理由:** 综合评分 {scores[winner]} 分 (vs {scores[name_a if winner==name_b else name_b]} 分)")
    _w(f"- **风险提示:** ")
    _w(f"  - 增压器转速限制值 ({sm.get('turbo_speed_limit', 250000)} rpm) 需供应商确认")
    if altitude_results and "error" not in altitude_results:
        if "❌" in altitude_results[name_a]["safety"] or \
           "❌" in altitude_results[name_b]["safety"]:
            _w(f"  - 高原可能超速，需确认 ECU 降扭策略")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# 8. 一站式分析工作流
# ────────────────────────────────────────────────────────────

def full_analysis(filepath: str,
                  name_a: str = "A", name_b: str = "B",
                  n_points: Optional[int] = None,
                  sheet_name: Optional[str] = None,
                  skiprows: int = 0,
                  turbo_speed_limit: int = TURBO_SPEED_LIMIT_DEFAULT,
                  altitude_m: Optional[float] = 3000,
                  save_plot: Optional[str] = None) -> Dict:
    """完整分析流程: 加载 → 分隔 → 对比 → 高原评估 → 可视化 → 报告。

    Args:
        filepath: Excel 文件路径
        name_a, name_b: 增压器名称
        n_points: 每组数据行数 (见 split_groups)
        sheet_name: Excel sheet 名
        skiprows: 跳过的起始行数
        turbo_speed_limit: 增压器转速限制
        altitude_m: 评估海拔 (米)，设为 None 则跳过
        save_plot: 图表保存路径，设为 None 则不保存

    Returns:
        {"results": ..., "altitude": ..., "report": "..."}

    用法 (快捷方式):
        out = full_analysis("260601-增压器对比数据.xlsx",
                            "博马", "奕森", n_points=9)
        print(out["report"])
    """
    print(f"{'='*60}")
    print(f"🔧 增压器对比分析 — {name_a} vs {name_b}")
    print(f"{'='*60}\n")

    # Step 1: 加载数据
    df = load_excel(filepath, sheet_name=sheet_name, skiprows=skiprows)
    df = clean_columns(df)
    df = ensure_numeric(df)

    # Step 2: 分隔
    df_a, df_b = split_groups(df, n_points=n_points)

    # Step 3: 对比
    results = compare_turbochargers(
        df_a, df_b, name_a=name_a, name_b=name_b,
        turbo_speed_limit=turbo_speed_limit,
    )

    # Step 4: 高原评估
    altitude_results = None
    if altitude_m is not None:
        try:
            altitude_results = assess_high_altitude(
                df_a, df_b, name_a=name_a, name_b=name_b,
                altitude_m=altitude_m,
                turbo_speed_limit=turbo_speed_limit,
            )
        except Exception as e:
            print(f"⚠️ 高原评估跳过: {e}")

    # Step 5: 可视化
    if save_plot:
        try:
            plot_comparison(results, save_path=save_plot)
        except Exception as e:
            print(f"⚠️ 图表生成跳过: {e}")

    # Step 6: 报告
    report = generate_text_report(results, altitude_results)

    # 打印结果
    print(report)

    return {
        "results": results,
        "altitude": altitude_results,
        "report": report,
    }


# ────────────────────────────────────────────────────────────
# 辅助工具
# ────────────────────────────────────────────────────────────

def calculate_pressure_ratio(boost_kpa: np.ndarray,
                             altitude_m: float = 0) -> np.ndarray:
    """计算增压比 (PR = 增压压力 / 对应海拔的大气压)。

    Args:
        boost_kpa: 增压压力数组 (kPa)
        altitude_m: 海拔高度 (米)，默认海平面

    Returns:
        增压比数组

    用法:
        pr = calculate_pressure_ratio(boost_values, altitude_m=3000)
    """
    P_alt = calc_altitude_pressure(altitude_m)
    return boost_kpa / P_alt


def estimate_turbo_speed_at_altitude(speed_sea_level: np.ndarray,
                                     altitude_m: float) -> np.ndarray:
    """推算高原增压器转速。

    Speed_alt = Speed_0 × √(P0 / P_alt)

    Args:
        speed_sea_level: 海平面增压器转速数组 (rpm)
        altitude_m: 目标海拔 (米)

    Returns:
        高原增压器转速数组 (rpm)
    """
    P_alt = calc_altitude_pressure(altitude_m)
    ratio = np.sqrt(ATM_STANDARD / P_alt)
    return speed_sea_level * ratio


def wg_efficiency_assessment(wg_opening: np.ndarray, rpm: np.ndarray,
                             threshold_low: float = 10.0,
                             threshold_high: float = 20.0) -> str:
    """评估 WG 开度效率。

    - < 10%:   ✅ 匹配优秀，废气能量利用率高
    - 10~20%:  ⚡ 匹配良好
    - > 20%:   ⚠️ 匹配效率低，需要放掉大量废气

    Args:
        wg_opening: WG 开度数组 (%)
        rpm: 转速数组
        threshold_low: 低阈值
        threshold_high: 高阈值

    Returns:
        评估结论字符串
    """
    avg = np.nanmean(wg_opening)
    max_val = np.nanmax(wg_opening)

    if max_val < threshold_low:
        return f"✅ 匹配优秀 (平均 {avg:.1f}%, 最大 {max_val:.1f}%)"
    elif avg < threshold_high:
        return f"⚡ 匹配良好 (平均 {avg:.1f}%)"
    else:
        high_rpm_avg = np.nanmean(
            wg_opening[rpm >= 3000] if any(rpm >= 3000) else wg_opening
        )
        return f"⚠️ 匹配效率低 (平均 {avg:.1f}%, 高转速均 {high_rpm_avg:.1f}%)"


def print_data_structure(df: pd.DataFrame) -> None:
    """打印数据结构的友好界面，方便快速理解 Excel 布局。"""
    print(f"📋 行数: {df.shape[0]}, 列数: {df.shape[1]}")
    print(f"\n📐 列名:")
    for i, col in enumerate(df.columns):
        print(f"  [{i:2d}] {col}")
    print(f"\n📄 前 5 行 (缩略):")
    print(df.head(5).to_string(max_colwidth=20))
    print(f"\n📄 后 5 行 (缩略):")
    print(df.tail(5).to_string(max_colwidth=20))


# ────────────────────────────────────────────────────────────
# CLI 入口 (方便快速调试)
# ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("用法: python engine_analysis.py <file.xlsx> <名称A> <名称B> [行数]")
        print("示例: python engine_analysis.py data.xlsx 博马 奕森 9")
        sys.exit(1)

    fp = sys.argv[1]
    name_a = sys.argv[2]
    name_b = sys.argv[3]
    n_pts = int(sys.argv[4]) if len(sys.argv) > 4 else None

    full_analysis(fp, name_a, name_b, n_points=n_pts)
