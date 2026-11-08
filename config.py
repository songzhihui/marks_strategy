"""霍华德·马克斯选股策略：全部可调参数集中在这里。"""

# ---------------- 数据源 ----------------
EXCHANGE_ID = "binanceusdm"            # ccxt 里的币安 U 本位合约
PROXY = "http://127.0.0.1:7890"        # 本机代理。可用环境变量 BINANCE_PROXY 或命令行 --proxy 覆盖，设为 "" 即直连
TIMEOUT_MS = 30_000
CACHE_DIR = "cache"                    # 原始数据按 UTC 日期缓存，同一天重复运行不重复下载
CACHE_KEEP_DAYS = 3                    # 只保留最近 3 天的缓存目录
OUTPUT_DIR = "output"

# ---------------- 选股范围 ----------------
QUOTE = "USDT"                         # 只用 USDT 保证金永续，避免同一标的重复
TOP_N_CRYPTO = 30                      # 加密合约按 24 小时成交额取前 30
STABLECOINS = {
    "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDE", "PYUSD",
    "USD1", "RLUSD", "USDS", "FRAX", "EUR", "EURI", "XUSD",
}
# 股票合约的识别方式：币安 exchangeInfo 里的 underlyingType。
# 实测（2026-11）：美股 EQUITY，港股 HK_EQUITY，韩股 KR_EQUITY，A 股 CN_EQUITY；美股 ETF 也标为 EQUITY。
# 以 _EQUITY 结尾的新市场会自动纳入。大宗商品 COMMODITY、外汇 FX、指数 INDEX 不纳入。
# 上市前合约（OPENAI、ANTHROPIC 等）标为 PREMARKET，没有真实股价，默认不纳入；想纳入就把 "PREMARKET" 加进来。
# 运行 python main.py --inspect 可查看币安当前返回的实际取值。
STOCK_UNDERLYING_TYPES = {"EQUITY", "HK_EQUITY", "KR_EQUITY", "CN_EQUITY"}
CRYPTO_BENCHMARK = "BTC/USDT:USDT"     # 计算“不对称性”时的基准
STOCK_BENCHMARK = "SPY/USDT:USDT"      # 拿不到时退回全部股票合约的等权组合

# ---------------- 历史数据长度 ----------------
OHLCV_DAYS = 500                       # 日线根数，需覆盖一年高点和 200 日均线
FUNDING_LIMIT = 1000                   # 最近 1000 次资金费率
SENTIMENT_DAYS = 30                    # 币安持仓量、多空比历史只提供最近 30 天

# ---------------- 数据清洗：拆股复权 ----------------
# 股票合约的历史 K 线没有按拆股复权，拆股日会出现一根假的暴跌。只对股票合约做识别，加密货币不拆股。
# 单日跳变同时满足下面两条才算拆股：幅度至少是该合约日常波动的 20 倍；跳变比例贴近常见拆股比例。
SPLIT_MIN_X_MEDIAN = 20                # 日常波动用日收益绝对值的中位数衡量
SPLIT_RATIOS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100)
SPLIT_TOL_SMALL = 0.04                 # 1 拆 2、1 拆 3 必须贴得很近，避免把真实的腰斩当成拆股
SPLIT_TOL_LARGE = 0.10                 # 1 拆 4 以上，单日真实涨跌不可能有这么大，可以放宽
REVERSE_SPLIT_MIN = 5                  # 合股（价格暴涨）只认 5 合 1 以上，避免把妖股暴涨当成合股

# ---------------- 杠杆、反向产品识别 ----------------
# 杠杆和反向 ETF 每日再平衡，长期持有有损耗，正是马克斯说的“永久损失”风险，一律回避。
LEVERAGE_WINDOW = 120                  # 用最近 120 天日收益识别
LEVERAGE_MIN_CORR = 0.97               # 与另一个合约的日收益相关性至少 0.97
LEVERAGE_MIN_RATIO = 1.5               # 且波动是对方的 1.5 倍以上（含反向），视为它的杠杆或反向产品
INVERSE_MAX_CORR = -0.5                # 与基准的相关性低于 -0.5，视为做空或波动率产品
MANUAL_LEVERAGED = {"TMF", "TBT", "UVXY"}  # 跟踪的标的不在币安上、数据识别不到的杠杆或反向产品

# ---------------- 因子窗口 ----------------
MIN_BARS_FOR_FEATURES = 20             # 日线少于这个数就不算因子，直接按“上市太短”回避
VOL_WINDOW = 90                        # 波动率窗口，用于把涨跌幅换算成“几个标准差”
LONG_MA_DAYS = 200                     # 长期均线：价格相对它的位置用来近似“贵还是便宜”
LONG_MA_MIN_DAYS = 100                 # 上市不足 200 天的用上市以来的均线，但至少要有 100 天
RISK_WINDOW = 180                      # 下行波动、尾部亏损的窗口
ASYM_WINDOW = 180                      # 上行/下行捕获率的窗口
FUNDING_WINDOW_DAYS = 14               # 资金费率取最近 14 天的年化均值
MA20_Z_CAP = 0.5                       # 企稳因子只奖励“止跌”，不奖励短期暴涨

# ---------------- 市场温度计 ----------------
# 各分项 0~100 分，越高越热。加权平均得到市场温度。
TEMPERATURE_WEIGHTS = {"valuation": 0.35, "sentiment": 0.35, "breadth": 0.15, "momentum": 0.15}
# 年化资金费率对应的温度锚点：(0 分, 50 分, 100 分)。
# 币安默认资金费率 0.01%/8h ≈ 年化 10.95%，代表没有溢价的中性状态。
FUNDING_ANCHORS = (-0.10, 0.1095, 0.50)

# 温度 → 周期阶段、建议仓位、选股风格
REGIMES = [
    {"upper": 20, "name": "冰点：极度悲观", "exposure": 1.00, "style": "aggressive",
     "advice": "钟摆摆到恐惧一端，好东西也在被抛售，应当积极买入"},
    {"upper": 40, "name": "偏冷：悲观", "exposure": 0.80, "style": "aggressive",
     "advice": "多数人谨慎，价格低于价值的机会较多，可以偏进攻"},
    {"upper": 60, "name": "中性", "exposure": 0.60, "style": "balanced",
     "advice": "既不便宜也不昂贵，攻守平衡，耐心等待更好的价格"},
    {"upper": 80, "name": "偏热：乐观", "exposure": 0.40, "style": "defensive",
     "advice": "乐观情绪推高价格，风险在累积，转向防守"},
    {"upper": float("inf"), "name": "过热：贪婪", "exposure": 0.20, "style": "defensive",
     "advice": "人们认为风险最低的时候风险最高，大幅降低仓位"},
]

# 不同风格下五组因子的权重
FACTOR_WEIGHTS = {
    "aggressive": {"value": 0.30, "sentiment": 0.25, "risk": 0.15, "asymmetry": 0.15, "stability": 0.15},
    "balanced":   {"value": 0.20, "sentiment": 0.20, "risk": 0.25, "asymmetry": 0.20, "stability": 0.15},
    "defensive":  {"value": 0.15, "sentiment": 0.10, "risk": 0.35, "asymmetry": 0.25, "stability": 0.15},
}

# ---------------- 先排除输家 ----------------
FILTERS = {
    "crypto": {
        "min_history_days": 180,       # 新上市热门币没经历过完整周期
        "min_adv_usd": 20e6,           # 30 日日均成交额下限（美元）
        "max_drawdown": -0.90,         # 较一年高点跌超 90%，视为可能永久损失
        "max_funding_ann": 0.40,       # 资金费率年化超 40%，多头过度拥挤
        "max_ext_z": 2.0,              # 高于长期均线 2 个标准差以上，价格透支
        "knife_days": 5,               # 5 天内刚创 90 日新低，列入观察，不接飞刀
    },
    "stock": {
        "min_history_days": 60,
        "min_adv_usd": 1e6,
        "max_drawdown": -0.70,
        "max_funding_ann": 0.40,
        "max_ext_z": 2.0,
        "knife_days": 5,
    },
}

# ---------------- 组合 ----------------
MAX_PICKS = {"crypto": 6, "stock": 6}  # 每个板块最多选几只
MIN_SCORE = 55                         # 综合分低于这个值宁可持有现金
MAX_POSITION = 0.25                    # 单只上限，超出部分留作现金
