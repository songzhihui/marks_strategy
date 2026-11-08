"""霍华德·马克斯选股策略的命令行入口。图形界面请运行 gui.py。

用法：
    python main.py                 # 拉数据、打分、输出报告（默认走 config.PROXY）
    python main.py --refresh       # 忽略当天缓存，重新下载
    python main.py --proxy ""      # 不用代理直连
    python main.py --inspect       # 查看币安合约的分类字段，用来核对股票合约识别规则
"""
import argparse

import pipeline
from data import default_proxy
from report import write_outputs


def main() -> None:
    ap = argparse.ArgumentParser(description="霍华德·马克斯选股策略（币安合约）")
    ap.add_argument("--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890；传空字符串表示直连")
    ap.add_argument("--refresh", action="store_true", help="忽略当天缓存重新下载")
    ap.add_argument("--inspect", action="store_true", help="只打印合约分类字段")
    args = ap.parse_args()

    proxy = args.proxy if args.proxy is not None else default_proxy()
    if args.inspect:
        print(pipeline.inspect_markets(proxy))
        return
    out = pipeline.run(proxy, args.refresh, log=lambda msg: print(msg, flush=True))
    md_path, csv_path, text = write_outputs(out["results"], out["asof"])
    print("\n" + text)
    print(f"\n报告：{md_path}\n明细：{csv_path}")


if __name__ == "__main__":
    main()
