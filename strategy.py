"""先排除输家，再给剩下的打分，最后按市场温度决定仓位。"""
import numpy as np
import pandas as pd

import config

# 五组因子：(列名, 方向)。+1 越大越好，-1 越小越好。组内取截面百分位的平均。
FACTOR_GROUPS = {
    "value":     [("ext_ma_z", -1), ("drawdown_365", -1)],
    "sentiment": [("funding_ann", -1), ("long_short_ratio", -1), ("oi_change_30", -1)],
    "risk":      [("downside_vol", -1), ("cvar_5", +1), ("adv_30", +1)],
    "asymmetry": [("asymmetry", +1)],
    "stability": [("days_since_low90", +1), ("ma20_z_capped", +1)],
}
GROUP_NAMES = {"value": "价值", "sentiment": "逆向情绪", "risk": "风险控制",
               "asymmetry": "不对称", "stability": "企稳"}


def score(feats: pd.DataFrame, weights: dict) -> pd.DataFrame:
    df = feats.copy()
    if "ma20_z" in df:
        df["ma20_z_capped"] = df["ma20_z"].clip(upper=config.MA20_Z_CAP)
    for g, items in FACTOR_GROUPS.items():
        ranks = [(sign * df[c]).rank(pct=True) for c, sign in items
                 if c in df and df[c].notna().sum() >= 3]
        df["s_" + g] = pd.concat(ranks, axis=1).mean(axis=1) * 100 if ranks else np.nan
    cols = ["s_" + g for g in FACTOR_GROUPS]
    w = pd.Series([weights[g] for g in FACTOR_GROUPS], index=cols)
    available = df[cols].notna().astype(float)
    df["score"] = (df[cols].fillna(0) * w).sum(axis=1) / (available * w).sum(axis=1).replace(0, np.nan)
    return df


def _num(r: pd.Series, col: str) -> float:
    v = r.get(col)
    return float(v) if v is not None and pd.notna(v) else float("nan")


def apply_filters(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    """回避：可能永久亏损或明显过热的；观察：还在创新低的；其余为候选。"""
    status, notes = [], []
    for _, r in df.iterrows():
        avoid = []
        hist, adv, dd = _num(r, "history_days"), _num(r, "adv_30"), _num(r, "drawdown_365")
        fund, ext, low = _num(r, "funding_ann"), _num(r, "ext_ma_z"), _num(r, "days_since_low90")
        lev, corr = r.get("leveraged"), _num(r, "bench_corr")
        if isinstance(lev, str):
            avoid.append(f"杠杆或反向产品（{lev}），每日再平衡会造成长期损耗")
        elif corr <= config.INVERSE_MAX_CORR:
            avoid.append(f"与基准反向（相关性{corr:.2f}），属于做空或波动率产品")
        if hist < flt["min_history_days"]:
            avoid.append(f"上市仅{int(hist)}天，未经周期检验")
        if adv < flt["min_adv_usd"]:
            avoid.append(f"日均成交额仅{adv / 1e6:.1f}M美元，流动性不足")
        if dd <= flt["max_drawdown"]:
            avoid.append(f"较一年高点下跌{-dd:.0%}，可能已是永久损失")
        if fund >= flt["max_funding_ann"]:
            avoid.append(f"资金费率年化{fund:.0%}，多头拥挤")
        if ext >= flt["max_ext_z"]:
            avoid.append(f"高于长期均线{ext:.1f}σ，价格透支")
        if avoid:
            status.append("回避")
            notes.append("；".join(avoid))
        elif low < flt["knife_days"]:
            status.append("观察")
            when = "最新收盘价就是" if low == 0 else f"{int(low)}天前刚创"
            notes.append(f"{when}90日新低，等企稳再说")
        else:
            status.append("候选")
            notes.append("")
    out = df.copy()
    out["status"] = status
    out["note"] = notes
    return out


def build_portfolio(df: pd.DataFrame, regime: dict, max_picks: int) -> pd.DataFrame:
    """取综合分最高的候选，按波动率倒数分配，总仓位由市场温度决定。"""
    picks = df[(df["status"] == "候选") & (df["score"] >= config.MIN_SCORE)]
    picks = picks.nlargest(max_picks, "score").copy()
    if picks.empty:
        return picks
    inv_vol = 1 / picks["vol_ann"]
    picks["weight"] = (inv_vol / inv_vol.sum() * regime["exposure"]).clip(upper=config.MAX_POSITION)
    return picks


def highlights(r: pd.Series) -> str:
    """把关键读数写成一句话，方便人工复核。"""
    parts = []
    v = _num(r, "ext_ma_z")
    if v == v:
        parts.append(f"距长期均线{v:+.1f}σ")
    v = _num(r, "drawdown_365")
    if v == v:
        parts.append(f"距一年高点{v:.0%}")
    v = _num(r, "funding_ann")
    if v == v:
        parts.append(f"费率年化{v:+.0%}")
    v = _num(r, "long_short_ratio")
    if v == v:
        parts.append(f"多空人数比{v:.2f}")
    v = _num(r, "days_since_low90")
    if v == v:
        parts.append(f"距90日低点{int(v)}天")
    up, dn = _num(r, "upside_capture"), _num(r, "downside_capture")
    if up == up and dn == dn:
        parts.append(f"上/下行捕获{up:.2f}/{dn:.2f}")
    return "，".join(parts)
