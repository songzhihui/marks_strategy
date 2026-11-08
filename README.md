# Marks Strategy

English | [简体中文](README.zh-CN.md)

A Howard Marks-inspired research screener for Binance USDT-margined perpetual contracts. It combines cycle awareness, contrarian sentiment, downside risk and asymmetric returns to produce separate cryptocurrency and equity watchlists with suggested portfolio weights.

The application reads public market data through **ccxt**. No API key is required, and it does not place orders. The desktop interface, logs and generated reports are currently in Chinese; this README is the English project guide.

## Features

- Screen the top 30 cryptocurrency contracts by 24-hour quote volume and all eligible equity contracts, including ETFs.
- Assess crypto and equities independently using a 0–100 market temperature.
- Rank five factor groups: value, contrarian sentiment, risk control, asymmetry and stabilization.
- Explain exclusions and distinguish candidates, watchlist entries and avoided instruments.
- Allocate by inverse volatility, with regime-dependent exposure and a 25% cap per instrument.
- Explore results in a PyQt6 desktop application or export Markdown and CSV from the CLI.
- Cache downloaded symbol data by UTC date and infer possible equity splits and leveraged products.

## Quick start

Use Python **3.10 or later** with compatible dependency builds. A virtual environment is recommended. Run commands from the project directory.

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and launch either entry point:

```bash
python -m pip install -r requirements.txt
python gui.py
# Or run the command-line screener:
python main.py
```

Dependencies: ccxt, pandas, NumPy, PyQt6 and Matplotlib. The GUI requires a graphical desktop. On Windows, `run.bat` starts the GUI using the Python on your PATH; install dependencies first.

### Proxy configuration

The default proxy is **`http://127.0.0.1:7890`**. Change it if your local proxy uses another port, or disable it for a direct connection.

```bash
python main.py --proxy http://127.0.0.1:7890
python main.py --proxy ""
python main.py --refresh
python main.py --inspect
python main.py --help
```

| Option | Behavior |
| --- | --- |
| `--proxy URL` | Override the proxy; an empty string requests a direct connection. |
| `--refresh` | Bypass today's cached symbol data and download it again. |
| `--inspect` | Print contract classification metadata and exit without screening. |
| `--help` | Show CLI usage without fetching market data. |

CLI proxy precedence: `--proxy` → `BINANCE_PROXY` environment variable → `config.PROXY`. For example, in PowerShell:

```powershell
$env:BINANCE_PROXY = "http://127.0.0.1:7890"
python main.py
```

Some shells or older PowerShell versions may drop an empty quoted argument. If `--proxy ""` reports a missing argument, set `PROXY = ""` in `config.py` and remove any `BINANCE_PROXY` override. The GUI also provides a proxy field.

The first run downloads daily candles, funding rates, open interest and long/short ratios for each instrument and can take several minutes. Subsequent runs reuse symbol data cached on the same UTC day; market discovery still uses the network. By default, only the latest three dated cache directories are retained.

## How the strategy works

### 1. Build the universe

Only active, linear USDT-quoted and USDT-settled perpetual contracts are eligible. Crypto contracts use `underlyingType=COIN`, excluding configured stablecoins, and are ranked by 24-hour quote volume. Equities use configured equity types or types ending in `_EQUITY`.

The configuration recognizes `EQUITY`, `HK_EQUITY`, `KR_EQUITY` and `CN_EQUITY`. Actual availability depends on exchange metadata. Commodities, FX, indices and premarket contracts are excluded by default. Use `--inspect` to inspect the exchange's current classifications.

### 2. Measure cycle temperature

Each segment gets its own temperature from valuation (35%), funding sentiment (35%), breadth (15%) and 90-day momentum (15%). Leveraged and inverse products are excluded from temperature calculations. Missing components are omitted, and component sample counts are reported.

| Temperature | Regime | Target segment exposure | Factor style |
| --- | --- | --- | --- |
| Below 20 | Extremely cold | 100% | Aggressive |
| 20 to below 40 | Cold | 80% | Aggressive |
| 40 to below 60 | Neutral | 60% | Balanced |
| 60 to below 80 | Hot | 40% | Defensive |
| 80 and above | Overheated | 20% | Defensive |

### 3. Score and filter

| Factor group | Signals |
| --- | --- |
| Value | Price deviation from the long moving average; drawdown from the trailing one-year high |
| Contrarian sentiment | Annualized funding, long/short account ratio, 30-day open-interest change |
| Risk control | Downside volatility, mean return on the worst 5% of days, trading liquidity |
| Asymmetry | Upside capture minus downside capture, scaled by its standard error |
| Stabilization | Days since the 90-day low; capped deviation from the 20-day moving average |

Price deviations are volatility-normalized. Factor inputs are percentile-ranked within each segment; available factor groups are combined using the current regime's weights. BTC is the crypto benchmark; equities use SPY when available, otherwise an equal-weight equity basket.

Default filters avoid leveraged/inverse products, insufficient history or liquidity, extreme drawdowns, excessive funding and prices far above the long moving average. Crypto requires 180 daily bars and $20 million average daily turnover; equities require 60 bars and $1 million. Instruments that made a new 90-day low fewer than five days ago go on the watchlist.

### 4. Construct a research portfolio

Eligible candidates need a score of at least **55**. Each segment selects at most **six** instruments and weights them by inverse annualized volatility. Each weight is capped at **25% of that segment's capital**. Capped allocations are not redistributed; unused exposure remains cash. Allocation between crypto and equities is left to the user.

## Data handling

- The current unfinished daily candle is removed before calculating price factors.
- The long moving average uses up to 200 daily bars and requires at least 100. Shorter histories omit those signals.
- Possible equity splits/reverse splits are inferred from extreme price jumps near configured split ratios; earlier prices and volumes are adjusted and events are logged. Crypto prices are not split-adjusted.
- Leveraged/inverse products are inferred using return correlation and volatility ratios, benchmark correlation and a manual exclusion list. These are heuristics requiring review.
- Failed symbol-data requests are logged. Missing inputs can reduce signal coverage and affect rankings; inspect the report and logs before interpreting results.

## Desktop interface

Enter your proxy and select **运行选股** to start. Downloads run in a background worker; **停止** requests cancellation. Crypto and equities have separate tabs with temperature components, portfolio weights and sortable results. Select a row to view its price history and factor details. Truncated cells expose full text on hover, and styling follows the system theme.

**检查合约分类** prints metadata for reviewing universe classification. Completed GUI runs write the same report files as the CLI.

## Output

Files are stored relative to the application directory:

| Path | Contents |
| --- | --- |
| `output/report_YYYY-MM-DD.md` | Segment temperatures, allocations, watchlists, exclusions and reasons |
| `output/selection_YYYY-MM-DD.csv` | Raw features, factor scores, composite scores, status, weights and temperature |
| `cache/YYYY-MM-DD/` | Downloaded symbol data, grouped by UTC retrieval date |

Report filenames use the latest available closed daily candle date across downloaded instruments, which may differ from the retrieval date. Repeated runs for the same report date overwrite the files. A CSV is only written when at least one segment has scored rows. CSV files use UTF-8 with BOM for spreadsheet compatibility.

Status labels: **候选** = candidate, **观察** = watchlist, **回避** = avoid. A candidate is not necessarily selected: score thresholds and portfolio size limits still apply.

## Configuration and project layout

All tunable defaults live in `config.py`: exchange and proxy, universe size, cache retention, historical windows, split/product detection, filters, temperature regimes, factor weights and portfolio limits.

```text
main.py           CLI entry point
gui.py           PyQt6 desktop application
ui_style.py      Desktop styles
pipeline.py      Shared data-to-portfolio workflow
data.py          Exchange access, caching, classification and split adjustment
factors.py       Features, benchmarks and leveraged-product detection
cycle.py         Market temperature and regime selection
strategy.py      Scoring, filtering and portfolio weights
report.py        Markdown and CSV output
config.py        Strategy and data settings
requirements.txt Python dependencies
run.bat          Windows GUI launcher
```

## Troubleshooting

- **Connection or proxy errors:** verify the configured proxy and Binance connectivity. Use `--inspect` to check market discovery separately from screening.
- **No equity contracts:** inspect metadata and eligibility; contracts may be unavailable or classified differently. Review `STOCK_UNDERLYING_TYPES` before changing it.
- **No selections:** review exclusion reasons and scores. An all-cash result is possible under the default rules.
- **Missing factor values:** check history length, failed requests and sample coverage. Exchange sentiment history is limited, and young contracts may lack a long moving average.
- **GUI import errors:** install requirements using the same Python interpreter used to launch the application.

## Limitations

This is an independent interpretation of Howard Marks' ideas, not an implementation of an official Oaktree strategy. Price relative to a moving average is a proxy for cheapness, not an estimate of intrinsic value from fundamentals.

The strategy has **not been backtested**. A retrospective test using today's top-volume universe would introduce survivorship and selection bias. Open-interest and long/short history are limited to approximately 30 days by the configured source. Split and product detection can misclassify instruments, and missing data can change scores.

Outputs are research aids, not investment advice. Suggested weights do not model margin, liquidation, execution costs or the full risks of leveraged perpetual contracts.
