"""数据层：用 ccxt 从币安 U 本位合约获取日线、资金费率、持仓量和多空比。

原始数据按 UTC 日期缓存在 cache/ 下，同一天重复运行直接读缓存。
"""
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from functools import partial

import ccxt
import numpy as np
import pandas as pd

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def default_proxy() -> str:
    return os.environ.get("BINANCE_PROXY", config.PROXY)


def make_exchange(proxy: str | None):
    ex = getattr(ccxt, config.EXCHANGE_ID)({"enableRateLimit": True, "timeout": config.TIMEOUT_MS})
    if proxy:
        if proxy.startswith("socks"):
            ex.socksProxy = proxy
        else:
            ex.httpsProxy = proxy
    return ex


def is_perpetual(market: dict) -> bool:
    """ccxt 识别的永续，或 contractType 以 PERPETUAL 结尾的合约（如币安 TradFi 永续）。"""
    ctype = str(market["info"].get("contractType") or "").upper()
    return bool(market.get("linear") and (market.get("swap") or ctype.endswith("PERPETUAL")))


def classify(market: dict) -> str | None:
    """把合约分成 'crypto' 或 'stock'；商品、外汇、指数、上市前等其它合约返回 None。"""
    utype = str(market["info"].get("underlyingType") or "").upper()
    if utype in config.STOCK_UNDERLYING_TYPES or utype.endswith("_EQUITY"):
        return "stock"
    if utype == "COIN" and market["base"] not in config.STABLECOINS:
        return "crypto"
    return None


def retry(fn, tries: int = 4):
    """网络错误（含代理断开、超时）时等几秒重试，其它错误直接抛出。"""
    for k in range(tries):
        try:
            return fn()
        except ccxt.NetworkError:
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def build_universe(ex) -> pd.DataFrame:
    """加密合约按 24h 成交额取前 N，再加上全部股票合约。"""
    markets = retry(ex.load_markets)
    perps = [
        m for m in markets.values()
        if is_perpetual(m) and m.get("active")
        and m.get("quote") == config.QUOTE and m.get("settle") == config.QUOTE
    ]
    tickers = retry(ex.fetch_tickers)
    rows = []
    for m in perps:
        segment = classify(m)
        if segment is None:
            continue
        t = tickers.get(m["symbol"]) or {}
        rows.append({
            "symbol": m["symbol"],
            "id": m["id"],
            "base": m["base"],
            "segment": segment,
            "quote_volume_24h": float(t.get("quoteVolume") or 0.0),
        })
    df = pd.DataFrame(rows, columns=["symbol", "id", "base", "segment", "quote_volume_24h"])
    crypto = df[df["segment"] == "crypto"].nlargest(config.TOP_N_CRYPTO, "quote_volume_24h")
    stock = df[df["segment"] == "stock"].sort_values("quote_volume_24h", ascending=False)
    return pd.concat([crypto, stock], ignore_index=True)


class Cache:
    def __init__(self, refresh: bool = False):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        root = os.path.join(BASE_DIR, config.CACHE_DIR)
        self.dir = os.path.join(root, day)
        self.refresh = refresh
        os.makedirs(self.dir, exist_ok=True)
        # 只清理本程序按日期命名的缓存目录，保留最近几天
        days = sorted(d for d in os.listdir(root)
                      if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and os.path.isdir(os.path.join(root, d)))
        for old in days[:-config.CACHE_KEEP_DAYS]:
            shutil.rmtree(os.path.join(root, old), ignore_errors=True)

    def get(self, key: str, fetch):
        path = os.path.join(self.dir, key + ".json")
        if not self.refresh and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        data = fetch()  # 失败时抛异常，不写缓存，下次会重试
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return data


def fetch_symbol_data(ex, cache: Cache, symbol: str, market_id: str, log=print,
                      split_adjust: bool = False) -> dict:
    jobs = {
        "ohlcv": lambda: ex.fetch_ohlcv(symbol, "1d", limit=config.OHLCV_DAYS),
        "funding": lambda: [[r["timestamp"], r["fundingRate"]]
                            for r in ex.fetch_funding_rate_history(symbol, limit=config.FUNDING_LIMIT)],
        "oi": lambda: [[r["timestamp"], r["openInterestAmount"]]
                       for r in ex.fetch_open_interest_history(symbol, "1d", limit=config.SENTIMENT_DAYS)],
        "lsr": lambda: [[r["timestamp"], r["longShortRatio"]]
                        for r in ex.fetch_long_short_ratio_history(symbol, "1d", limit=config.SENTIMENT_DAYS)],
    }
    raw = {}
    for kind, job in jobs.items():
        try:
            raw[kind] = cache.get(f"{kind}_{market_id}", partial(retry, job))
        except ccxt.BaseError as e:
            log(f"    ! {symbol} {kind} 获取失败：{type(e).__name__} {str(e)[:150]}")
            raw[kind] = []
    frames = _to_frames(raw)
    if split_adjust:
        frames["px"], events = adjust_splits(frames["px"])
        for day, factor in events:
            desc = f"1拆{factor:g}" if factor > 1 else f"{1 / factor:g}合1"
            log(f"    * {symbol} {day:%Y-%m-%d} 疑似{desc}，已对之前的价格复权")
    return frames


def adjust_splits(px: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """识别拆股、合股并向前复权。返回 (复权后的日线, [(日期, 比例)])，比例 k>1 表示 1 拆 k。"""
    if len(px) < 3:
        return px, []
    r = np.log(px["close"]).diff()
    med = r.abs().median()
    if not med > 0:
        return px, []
    px, events = px.copy(), []
    for day in r.index[r.abs() >= config.SPLIT_MIN_X_MEDIAN * med]:
        q = float(np.exp(-r[day]))           # 前收盘 / 当天收盘
        forward = q > 1                      # 价格暴跌：拆股；价格暴涨：合股
        q = q if forward else 1 / q
        k = min(config.SPLIT_RATIOS, key=lambda s: abs(np.log(q / s)))
        tol = config.SPLIT_TOL_SMALL if k <= 3 else config.SPLIT_TOL_LARGE
        if abs(np.log(q / k)) > tol or (not forward and k < config.REVERSE_SPLIT_MIN):
            continue
        factor = k if forward else 1 / k
        before = px.index < day
        px.loc[before, ["open", "high", "low", "close"]] /= factor
        px.loc[before, "volume"] *= factor
        events.append((day, factor))
    return px, events


def _series(rows: list, name: str) -> pd.Series:
    rows = [r for r in rows if r[0] is not None and r[1] is not None]
    if not rows:
        return pd.Series(dtype=float, name=name)
    idx = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
    return pd.Series([float(r[1]) for r in rows], index=idx, name=name).sort_index()


def _to_frames(raw: dict) -> dict:
    cols = ["open", "high", "low", "close", "volume"]
    rows = raw["ohlcv"]
    px = pd.DataFrame([r[1:6] for r in rows], columns=cols, dtype=float,
                      index=pd.to_datetime([r[0] for r in rows], unit="ms", utc=True))
    if len(px) and px.index[-1] + pd.Timedelta(days=1) > pd.Timestamp.now(tz="UTC"):
        px = px.iloc[:-1]  # 当天的 K 线还没收盘，不参与计算
    return {
        "px": px,
        "funding": _series(raw["funding"], "funding"),
        "oi": _series(raw["oi"], "oi"),
        "lsr": _series(raw["lsr"], "lsr"),
    }
