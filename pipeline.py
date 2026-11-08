"""选股流程：拉数据，再对每个板块算因子、量温度、打分、过滤、配仓。命令行和界面共用。"""
import collections

import pandas as pd

import config
from cycle import market_temperature
from data import Cache, build_universe, fetch_symbol_data, is_perpetual, make_exchange, retry
from factors import benchmark_returns, compute_features, find_leveraged
from strategy import apply_filters, build_portfolio, score

SEGMENTS = ("crypto", "stock")


class Cancelled(Exception):
    """用户中途停止。"""


def run_segment(segment: str, symbols: list[str], data: dict) -> dict:
    symbols = [s for s in symbols if s in data and len(data[s]["px"])]
    bench = benchmark_returns(segment, symbols, data) if symbols else None
    rows = [{"symbol": s, **compute_features(data[s], bench)} for s in symbols]
    feats = pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame()
    if feats.empty:
        temp = market_temperature(feats)
        return {"temperature": temp, "scored": feats, "picks": feats}

    lev = find_leveraged(symbols, data)
    for s in symbols:
        if s not in lev and s.split("/")[0] in config.MANUAL_LEVERAGED:
            lev[s] = "人工名单"
    feats["leveraged"] = pd.Series(lev, dtype=object)
    # 杠杆、反向产品会重复计算或抵消大盘涨跌，量温度时剔除
    corr = feats["bench_corr"] if "bench_corr" in feats else pd.Series(float("nan"), index=feats.index)
    structural = feats["leveraged"].notna() | (corr <= config.INVERSE_MAX_CORR)
    temp = market_temperature(feats[~structural])

    scored = score(feats, config.FACTOR_WEIGHTS[temp["regime"]["style"]])
    scored = apply_filters(scored, config.FILTERS[segment])
    picks = build_portfolio(scored, temp["regime"], config.MAX_PICKS[segment])
    return {"temperature": temp, "scored": scored, "picks": picks}


def run(proxy: str, refresh: bool = False, log=print, progress=None, should_stop=None) -> dict:
    """progress(k, total, symbol) 在下载第 k 个标的前调用；should_stop() 返回 True 时中止。"""
    ex = make_exchange(proxy)
    log(f"连接币安 U 本位合约（代理：{proxy or '无'}）…")
    universe = build_universe(ex)
    counts = universe["segment"].value_counts()
    log(f"选股范围：加密合约 {counts.get('crypto', 0)} 个，股票合约 {counts.get('stock', 0)} 个")

    cache = Cache(refresh=refresh)
    data = {}
    total = len(universe)
    for k, row in enumerate(universe.itertuples(), 1):
        if should_stop and should_stop():
            raise Cancelled("已停止")
        if progress:
            progress(k, total, row.symbol)
        else:
            log(f"[{k}/{total}] {row.symbol}")
        data[row.symbol] = fetch_symbol_data(ex, cache, row.symbol, row.id, log,
                                             split_adjust=row.segment == "stock")

    last_bars = [d["px"].index[-1] for d in data.values() if len(d["px"])]
    if not last_bars:
        raise RuntimeError("没有拿到任何日线数据，请检查网络或代理。")
    results = {seg: run_segment(seg, universe.loc[universe["segment"] == seg, "symbol"].tolist(), data)
               for seg in SEGMENTS}
    return {"results": results, "asof": max(last_bars), "data": data, "universe": universe}


def inspect_markets(proxy: str) -> str:
    """列出合约分类字段，用来核对股票合约的识别规则。"""
    markets = retry(make_exchange(proxy).load_markets)
    perps = [m for m in markets.values() if is_perpetual(m)]
    subtypes = collections.Counter(s for m in perps for s in m["info"].get("underlyingSubType") or [])
    lines = [
        "contractType: " + str(dict(collections.Counter(m["info"].get("contractType") for m in perps))),
        "underlyingType: " + str(dict(collections.Counter(m["info"].get("underlyingType") for m in perps))),
        "underlyingSubType: " + str(dict(subtypes.most_common())),
        "",
        "非 COIN 合约：",
    ]
    for m in sorted(perps, key=lambda m: m["symbol"]):
        i = m["info"]
        if i.get("underlyingType") != "COIN":
            onboard = pd.to_datetime(int(i.get("onboardDate") or 0), unit="ms").strftime("%Y-%m-%d")
            lines.append(f"  {m['symbol']:<22} {m['type']:<6} {i.get('contractType')!s:<20} "
                         f"{i.get('underlyingType')!s:<10} {i.get('underlyingSubType')} {i.get('status')} "
                         f"上线 {onboard} active={m['active']}")
    return "\n".join(lines)
