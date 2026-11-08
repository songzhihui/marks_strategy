"""市场温度计。

马克斯：我们无法预测未来，但可以知道自己身处周期的什么位置。
这里用四个分项给一个板块“量体温”，0 分最冷（恐慌），100 分最热（贪婪）。
"""
import numpy as np
import pandas as pd

import config


def _z_score_to_temp(z: float) -> float:
    return float(np.clip(50 + 25 * z, 0, 100))  # ±2σ 对应 0 / 100 分


def _funding_to_temp(f: float) -> float:
    lo, mid, hi = config.FUNDING_ANCHORS
    if f <= mid:
        return float(np.clip(50 * (f - lo) / (mid - lo), 0, 50))
    return float(np.clip(50 + 50 * (f - mid) / (hi - mid), 50, 100))


def market_temperature(feats: pd.DataFrame) -> dict:
    def col(name: str) -> pd.Series:
        return feats[name].dropna() if name in feats else pd.Series(dtype=float)

    comps = []  # (分项键, 名称, 温度, 读数, 样本数)
    s = col("ext_ma_z")
    if len(s) >= 3:
        comps.append(("valuation", "估值：价格相对长期均线", _z_score_to_temp(s.median()),
                      f"中位数 {s.median():+.2f}σ", len(s)))
    s = col("funding_ann")
    if len(s) >= 3:
        comps.append(("sentiment", "情绪：资金费率", _funding_to_temp(s.median()),
                      f"年化中位数 {s.median():+.1%}", len(s)))
    s = col("above_ma")
    if len(s) >= 3:
        comps.append(("breadth", "宽度：站上长期均线的比例", 100 * s.mean(),
                      f"{s.mean():.0%}", len(s)))
    s = col("mom90_z")
    if len(s) >= 3:
        comps.append(("momentum", "动量：90日涨跌", _z_score_to_temp(s.median()),
                      f"中位数 {s.median():+.2f}σ", len(s)))

    if not comps:  # 数据不足以判断周期，按中性处理
        return {"temperature": float("nan"), "components": [], "regime": config.REGIMES[2]}
    w = config.TEMPERATURE_WEIGHTS
    temp = sum(w[c[0]] * c[2] for c in comps) / sum(w[c[0]] for c in comps)
    regime = next(r for r in config.REGIMES if temp < r["upper"])
    return {"temperature": temp, "components": comps, "regime": regime}
