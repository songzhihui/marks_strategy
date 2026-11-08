"""单个合约的因子。只用最近一根已收盘日线及之前的数据。

价格类偏离都除以“随机游走下该偏离的正常幅度”，换算成标准差（σ），
这样波动大的山寨币和波动小的股票可以放在同一把尺子上比较。
"""
import numpy as np
import pandas as pd

import config


def compute_features(d: dict, bench_ret: pd.Series | None) -> dict:
    px, funding, oi, lsr = d["px"], d["funding"], d["oi"], d["lsr"]
    close = px["close"]
    n = len(close)
    f = {"history_days": n}
    if n < config.MIN_BARS_FOR_FEATURES:
        return f

    last = close.iloc[-1]
    ret = close.pct_change().dropna()
    vol_d = np.log(close).diff().tail(config.VOL_WINDOW).std()
    ok = bool(vol_d > 0)
    f["close"] = last
    f["vol_ann"] = vol_d * np.sqrt(365)

    # 价格与价值：离长期均线有多远、离一年高点跌了多少。
    # 长期均线最多 200 天；上市不足 200 天的用上市以来的均线，但至少要 100 天。
    w = min(n, config.LONG_MA_DAYS)
    if w >= config.LONG_MA_MIN_DAYS and ok:
        ma = close.tail(w).mean()
        f["ma_days"] = w
        f["ext_ma_z"] = np.log(last / ma) / (vol_d * np.sqrt(w / 3))
        f["above_ma"] = float(last > ma)
    f["drawdown_365"] = last / close.tail(365).max() - 1

    # 周期动量（只用于市场温度）
    if n > 90 and ok:
        f["mom90_z"] = np.log(last / close.iloc[-91]) / (vol_d * np.sqrt(90))

    # 企稳：多久没再创新低、是否站回短期均线
    w90 = close.tail(90)
    f["days_since_low90"] = (w90.index[-1] - w90.idxmin()).days
    if ok:
        f["ma20_z"] = np.log(last / close.tail(20).mean()) / (vol_d * np.sqrt(20 / 3))

    # 风险：下行波动、最差 5% 日子的平均亏损、流动性
    r = ret.tail(config.RISK_WINDOW)
    f["downside_vol"] = np.sqrt((r.clip(upper=0) ** 2).mean()) * np.sqrt(365)
    f["cvar_5"] = r[r <= r.quantile(0.05)].mean()
    f["adv_30"] = (px["close"] * px["volume"]).tail(30).mean()

    # 不对称：基准上涨时跟涨多少，基准下跌时跟跌多少；相关性用来识别与大盘反向的产品
    if bench_ret is not None and len(bench_ret):
        j = pd.concat([ret, bench_ret], axis=1, join="inner").dropna().tail(config.ASYM_WINDOW)
        a, b = j.iloc[:, 0], j.iloc[:, 1]
        if len(j) >= 40:
            f["bench_corr"] = a.corr(b)
        up, dn = b > 0, b < 0
        if up.sum() >= 20 and dn.sum() >= 20:
            mu, md = b[up].mean(), b[dn].mean()
            f["upside_capture"] = a[up].mean() / mu
            f["downside_capture"] = a[dn].mean() / md
            # 用 t 值衡量不对称：差值除以标准误，避免高波动标的靠运气排到前面
            se = np.sqrt(a[up].var() / up.sum() / mu ** 2 + a[dn].var() / dn.sum() / md ** 2)
            if se > 0:
                f["asymmetry"] = (f["upside_capture"] - f["downside_capture"]) / se

    # 情绪：资金费率、持仓量变化、多空人数比
    if len(funding):
        start = funding.index[-1] - pd.Timedelta(days=config.FUNDING_WINDOW_DAYS)
        if funding.index[0] <= start:
            f["funding_ann"] = funding[funding.index > start].sum() * 365 / config.FUNDING_WINDOW_DAYS
    if len(oi) >= 20 and oi.iloc[0] > 0:
        f["oi_change_30"] = oi.iloc[-1] / oi.iloc[0] - 1
    if len(lsr):
        f["long_short_ratio"] = lsr.tail(3).mean()
    return f


def benchmark_returns(segment: str, symbols: list[str], data: dict) -> pd.Series:
    """加密合约以 BTC 为基准，股票合约以 SPY 为基准；基准拿不到时用本板块等权组合。"""
    rets = pd.DataFrame({s: data[s]["px"]["close"].pct_change() for s in symbols})
    bench = config.CRYPTO_BENCHMARK if segment == "crypto" else config.STOCK_BENCHMARK
    if bench in rets and rets[bench].notna().sum() >= 60:
        return rets[bench].dropna()
    counts = rets.notna().sum(axis=1)
    return rets.mean(axis=1)[counts >= 3]


def find_leveraged(symbols: list[str], data: dict) -> dict[str, str]:
    """找出杠杆、反向产品：日收益几乎就是另一个合约的 L 倍（|L| 不小于 1.5）。返回 {合约: 说明}。

    例如 TQQQ 的日收益约等于 QQQ 的 3 倍，相关性 0.998；普通股票之间的相关性很少超过 0.95。
    """
    rets = pd.DataFrame({s: np.log(data[s]["px"]["close"]).diff() for s in symbols})
    rets = rets.tail(config.LEVERAGE_WINDOW)
    corr = rets.corr(min_periods=40)
    found = {}
    for a in corr.columns:
        best = None
        for b, c in corr[a].drop(a).dropna().items():
            if abs(c) < config.LEVERAGE_MIN_CORR or (best and abs(c) <= abs(best[1])):
                continue
            j = rets[[a, b]].dropna()
            lev = j[a].cov(j[b]) / j[b].var()
            if abs(lev) >= config.LEVERAGE_MIN_RATIO:
                best = (b, c, lev)
        if best:
            b, _, lev = best
            way = "反向" if lev < 0 else ""
            found[a] = f"约{abs(lev):.1f}倍{way}跟踪{b.split('/')[0]}"
    return found
