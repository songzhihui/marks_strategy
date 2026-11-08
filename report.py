"""把结果写成 Markdown 报告和 CSV，同时打印到终端。"""
import os

import pandas as pd

import config
from data import BASE_DIR
from strategy import FACTOR_GROUPS, GROUP_NAMES, highlights

SEGMENT_TITLES = {"crypto": f"加密货币合约（24h成交额前{config.TOP_N_CRYPTO}）", "stock": "股票合约（全部）"}
STYLE_NAMES = {"aggressive": "进攻：偏重价值与逆向情绪", "balanced": "平衡",
               "defensive": "防守：偏重风险控制与不对称"}


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _name(symbol: str) -> str:
    return symbol.split("/")[0]


def _fmt(v, spec: str) -> str:
    return "-" if v is None or pd.isna(v) else format(v, spec)


def segment_markdown(seg: str, res: dict) -> str:
    temp, scored, picks = res["temperature"], res["scored"], res["picks"]
    regime = temp["regime"]
    out = [f"## {SEGMENT_TITLES[seg]}", ""]
    if not len(scored):
        return "\n".join(out + ["没有拿到可用数据。", ""])

    t = temp["temperature"]
    out += [f"**市场温度 {_fmt(t, '.0f')} / 100：{regime['name']}。** {regime['advice']}。"
            f"建议该板块总仓位 {regime['exposure']:.0%}，选股风格为“{STYLE_NAMES[regime['style']]}”。", ""]
    if temp["components"]:
        out += [_table(["分项", "读数", "温度", "样本数"],
                       [[c[1], c[3], f"{c[2]:.0f}", c[4]] for c in temp["components"]]), ""]

    out += ["### 入选", ""]
    if picks.empty:
        out += ["没有同时满足“未被排除、综合分达标”的标的，本板块全部持有现金。", ""]
    else:
        rows = [[_name(s), f"{r['weight']:.1%}", f"{r['score']:.0f}",
                 *[_fmt(r.get('s_' + g), '.0f') for g in FACTOR_GROUPS], highlights(r)]
                for s, r in picks.iterrows()]
        out += [_table(["标的", "仓位", "综合分", *[GROUP_NAMES[g] for g in FACTOR_GROUPS], "关键读数"], rows), "",
                f"合计仓位 {picks['weight'].sum():.1%}，其余持有现金。", ""]

    watch = scored[scored["status"] == "观察"].sort_values("score", ascending=False)
    if len(watch):
        out += ["### 观察（还在下跌，不接飞刀）", "",
                _table(["标的", "综合分", "原因"], [[_name(s), _fmt(r["score"], ".0f"), r["note"]]
                                                for s, r in watch.iterrows()]), ""]

    avoid = scored[scored["status"] == "回避"].sort_values("score", ascending=False)
    if len(avoid):
        out += ["### 回避（先避开输家）", "",
                _table(["标的", "综合分", "原因"], [[_name(s), _fmt(r["score"], ".0f"), r["note"]]
                                                for s, r in avoid.iterrows()]), ""]

    others = scored[(scored["status"] == "候选") & ~scored.index.isin(picks.index)]
    others = others.sort_values("score", ascending=False)
    if len(others):
        out += ["### 其余候选（分数不够或名额已满）", "",
                _table(["标的", "综合分", "关键读数"], [[_name(s), _fmt(r["score"], ".0f"), highlights(r)]
                                                  for s, r in others.iterrows()]), ""]
    return "\n".join(out)


def write_outputs(results: dict, asof: pd.Timestamp) -> tuple[str, str, str]:
    """写出 Markdown 报告和 CSV 明细，返回 (报告路径, 明细路径, 报告文本)。"""
    day = asof.strftime("%Y-%m-%d")
    md = [f"# 霍华德·马克斯选股报告（数据截至 {day} UTC 收盘）", "",
          "先判断周期位置，再避开可能永久亏损的标的，最后在剩下的里找“价格低于价值、情绪悲观、"
          "下跌少于上涨”的品种。仓位是该板块资金的比例。本报告只是筛选工具，不构成投资建议。", ""]
    md += [segment_markdown(seg, res) for seg, res in results.items()]
    text = "\n".join(md)

    out_dir = os.path.join(BASE_DIR, config.OUTPUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"report_{day}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    frames = []
    for seg, res in results.items():
        df = res["scored"].copy()
        if not len(df):
            continue
        df.insert(0, "segment", seg)
        df["weight"] = res["picks"]["weight"] if len(res["picks"]) else 0.0
        df["weight"] = df["weight"].fillna(0.0)
        df["temperature"] = res["temperature"]["temperature"]
        frames.append(df)
    csv_path = os.path.join(out_dir, f"selection_{day}.csv")
    if frames:
        pd.concat(frames).to_csv(csv_path, encoding="utf-8-sig", index_label="symbol", float_format="%.6g")
    return md_path, csv_path, text
