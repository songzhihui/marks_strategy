"""霍华德·马克斯选股策略的 PyQt6 图形界面。

运行：python gui.py
"""
import html
import os
import sys
import threading
import traceback

import pandas as pd
from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QScrollArea,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

# matplotlib 要在 PyQt6 之后导入，它会自动选用已加载的 PyQt6 作为 Qt 绑定
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

import config
from ui_style import apply_style
import pipeline
from data import BASE_DIR, default_proxy
from report import SEGMENT_TITLES, STYLE_NAMES, write_outputs
from strategy import FACTOR_GROUPS, GROUP_NAMES, highlights

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

FORMATS = {"pct": "{:.1%}", "pct0": "{:.0%}", "z": "{:+.2f}", "num0": "{:.0f}",
           "num2": "{:.2f}", "int": "{:.0f}", "price": "{:.6g}"}
GROUP_COLUMNS = [(GROUP_NAMES[g], "s_" + g, "num0") for g in FACTOR_GROUPS]
PICK_COLUMNS = [("仓位", "weight", "pct"), ("综合分", "score", "num0"), *GROUP_COLUMNS]
ALL_COLUMNS = [
    ("综合分", "score", "num0"), *GROUP_COLUMNS,
    ("距长期均线σ", "ext_ma_z", "z"), ("距一年高点", "drawdown_365", "pct0"),
    ("费率年化", "funding_ann", "pct"), ("多空人数比", "long_short_ratio", "num2"),
    ("距90日低点天数", "days_since_low90", "int"), ("年化波动", "vol_ann", "pct0"),
    ("日均成交额(百万$)", "adv_30", "musd"),
]
DETAIL_FIELDS = [
    ("日线根数", "history_days", "int"), ("最新收盘价", "close", "price"),
    ("年化波动率", "vol_ann", "pct0"), ("长期均线天数", "ma_days", "int"),
    ("距长期均线（σ）", "ext_ma_z", "z"),
    ("距一年高点", "drawdown_365", "pct0"), ("90日动量（σ）", "mom90_z", "z"),
    ("距90日低点天数", "days_since_low90", "int"), ("距20日均线（σ）", "ma20_z", "z"),
    ("年化下行波动", "downside_vol", "pct0"), ("最差5%交易日平均跌幅", "cvar_5", "pct"),
    ("30日日均成交额（百万美元）", "adv_30", "musd"), ("与基准相关性", "bench_corr", "num2"),
    ("上行捕获率", "upside_capture", "num2"),
    ("下行捕获率", "downside_capture", "num2"), ("不对称性（t值）", "asymmetry", "num2"),
    ("资金费率年化（14日）", "funding_ann", "pct"), ("持仓量30日变化", "oi_change_30", "pct0"),
    ("多空人数比", "long_short_ratio", "num2"),
]
STATUS_ORDER = {"候选": 0, "观察": 1, "回避": 2}
THEMES = {
    "light": {
        "row_bg": {"候选": "#e3f4e8", "观察": "#fdf0d5", "回避": "#ececec"},
        "row_fg": "#202020",
        "status_fg": {"候选": "#17663a", "观察": "#8a5a00", "回避": "#666666"},
        "muted": "#777777",
        "axes_fg": "#333333",
        "lines": {"price": "#1f5fa8", "ma": "#d97706", "ma20": "#888888", "high": "#c53030"},
    },
    "dark": {
        "row_bg": {"候选": "#1d3a29", "观察": "#3d3219", "回避": "#2b2b2b"},
        "row_fg": "#e8e8e8",
        "status_fg": {"候选": "#5fd38d", "观察": "#f2b84b", "回避": "#a0a0a0"},
        "muted": "#a0a0a0",
        "axes_fg": "#d0d0d0",
        "lines": {"price": "#6aa9ff", "ma": "#f0a040", "ma20": "#9a9a9a", "high": "#ff6b6b"},
    },
}


def theme() -> dict:
    """跟随系统深浅色：窗口底色偏暗就用深色配色。"""
    app = QApplication.instance()
    dark = app is not None and app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return THEMES["dark" if dark else "light"]


def base_color() -> str:
    """表格底色，走势图用同一个颜色，和界面融为一体。"""
    app = QApplication.instance()
    return app.palette().color(QPalette.ColorRole.Base).name() if app else "#ffffff"


def fmt(v, kind: str) -> str:
    if v is None or pd.isna(v):
        return "-"
    if kind == "musd":
        return f"{v / 1e6:,.1f}"
    return FORMATS[kind].format(v)


def short(symbol: str) -> str:
    return symbol.split("/")[0]


def temp_color(t) -> str:
    """0 分蓝、50 分灰、100 分红。"""
    if t is None or pd.isna(t):
        return "#888888"
    t = min(max(float(t), 0.0), 100.0)
    (x0, c0), (x1, c1) = ((0, (37, 99, 235)), (50, (130, 130, 130))) if t <= 50 else \
                         ((50, (130, 130, 130)), (100, (220, 38, 38)))
    a = (t - x0) / (x1 - x0)
    r, g, b = (round(c0[i] + a * (c1[i] - c0[i])) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


class Item(QTableWidgetItem):
    """带排序键的单元格：有键的按键排序，空值的键是负无穷。"""

    def __init__(self, text: str, key=None, align_right: bool = False):
        super().__init__(text)
        self.key = key
        if align_right:
            self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, Item) and self.key is not None and other.key is not None:
            return self.key < other.key
        return super().__lt__(other)


def num_item(v, kind: str) -> Item:
    key = float(v) if v is not None and pd.notna(v) else float("-inf")
    return Item(fmt(v, kind), key, align_right=True)


def text_item(text: str) -> Item:
    """长文本单元格：悬停时显示全文。"""
    item = Item(text)
    item.setToolTip(text)
    return item


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setWordWrap(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(36)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setMinimumWidth(0)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def fit_rows(t: QTableWidget, n: int) -> None:
    """把表格高度固定为恰好显示表头和 n 行；最后一列被压缩时悬停可看全文。"""
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = t.horizontalHeader().sizeHint().height()
    t.setFixedHeight(header + n * t.verticalHeader().defaultSectionSize() + 2 * t.frameWidth() + 2)


def fill_table(t: QTableWidget, rows: list, sort_col: int | None = None,
               order: Qt.SortOrder = Qt.SortOrder.DescendingOrder) -> None:
    """rows 是 [(symbol, [Item, ...], 状态或 None)]；sort_col 为 None 时保持给定顺序。"""
    th = theme()
    t.setSortingEnabled(False)
    t.clearContents()
    t.setRowCount(len(rows))
    for i, (symbol, items, status) in enumerate(rows):
        for j, item in enumerate(items):
            item.setData(Qt.ItemDataRole.UserRole, symbol)
            if status and j == 1:
                item.setBackground(QColor(th["row_bg"][status]))
                item.setForeground(QColor(th["status_fg"][status]))
            t.setItem(i, j, item)
    if sort_col is not None:
        t.horizontalHeader().setSortIndicator(sort_col, order)
        t.setSortingEnabled(True)


class TemperaturePanel(QGroupBox):
    def __init__(self):
        super().__init__("市场温度")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 40px; font-weight: 700; color: #285dcc;")
        font = self.value.font()
        font.setPointSize(34)
        font.setBold(True)
        self.value.setFont(font)
        self.regime = QLabel("等待分析")
        self.regime.setStyleSheet("font-size: 14px; font-weight: 600;")
        font = self.regime.font()
        font.setPointSize(13)
        font.setBold(True)
        self.regime.setFont(font)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12)
        self.advice = QLabel("运行选股后，查看市场周期与仓位建议。")
        self.advice.setObjectName("muted")
        self.advice.setWordWrap(True)
        self.exposure = QLabel("")
        self.exposure.setWordWrap(True)
        self.components = make_table(["分项", "读数", "温度", "样本数"])
        fit_rows(self.components, len(config.TEMPERATURE_WEIGHTS))
        header = self.components.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 面板窄时分项名称显示省略号，数字列完整显示

        head = QHBoxLayout()
        head.addWidget(self.value)
        head.addWidget(self.regime, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(head)
        layout.addWidget(self.bar)
        layout.addWidget(self.advice)
        layout.addWidget(self.exposure)
        layout.addWidget(self.components)
        layout.addStretch(1)

    def show_temperature(self, temp: dict) -> None:
        t, regime = temp["temperature"], temp["regime"]
        color = temp_color(t)
        self.value.setText(fmt(t, "num0"))
        self.value.setStyleSheet(f"font-size: 40px; font-weight: 700; color: {color};")
        self.regime.setText(regime["name"])
        self.bar.setValue(0 if pd.isna(t) else int(round(t)))
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
        self.advice.setText(regime["advice"] + "。")
        self.exposure.setText(f"建议板块总仓位 {regime['exposure']:.0%}，风格：{STYLE_NAMES[regime['style']]}")
        rows = [(None, [text_item(c[1]), Item(c[3]), num_item(c[2], "num0"), num_item(c[4], "int")], None)
                for c in temp["components"]]
        fill_table(self.components, rows)


class PriceChart(FigureCanvasQTAgg):
    """最近一年的收盘价、20 日均线、长期均线和一年高点。"""

    def __init__(self):
        super().__init__(Figure(figsize=(5, 3), layout="tight"))  # 父类会把图存到 self.figure
        self.setMinimumHeight(220)
        self.ax = self.figure.add_subplot(111)
        self.plot(None, "")

    def plot(self, px: pd.DataFrame | None, title: str) -> None:
        th, bg = theme(), base_color()
        self.figure.set_facecolor(bg)
        ax = self.ax
        ax.clear()
        ax.set_facecolor(bg)
        if px is None or px.empty:
            ax.set_axis_off()
            ax.text(0.5, 0.5, "在表格中选中一行查看走势", ha="center", va="center",
                    color=th["muted"], transform=ax.transAxes)
        else:
            ax.set_axis_on()
            lines = th["lines"]
            s = pd.Series(px["close"].to_numpy(), index=px.index.tz_convert(None))
            last = s.tail(365)
            ax.plot(last.index, last.values, color=lines["price"], lw=1.4, label="收盘价")
            # 与因子一致：最多 200 日，上市不足 200 天的用上市以来的均线（至少 100 天才画）
            ma = s.rolling(config.LONG_MA_DAYS, min_periods=config.LONG_MA_MIN_DAYS).mean().tail(365)
            if ma.notna().any():
                ax.plot(ma.index, ma.values, color=lines["ma"], lw=1.2, label="长期均线")
            ma20 = s.rolling(20).mean().tail(365)
            ax.plot(ma20.index, ma20.values, color=lines["ma20"], lw=0.9, ls="--", label="20日均线")
            ax.axhline(last.max(), color=lines["high"], lw=0.8, ls=":", label="一年高点")
            ax.set_title(title, fontsize=10, color=th["axes_fg"])
            ax.grid(alpha=0.25, color=th["muted"])
            ax.tick_params(labelsize=8, colors=th["axes_fg"])
            for spine in ax.spines.values():
                spine.set_color(th["muted"])
            ax.legend(fontsize=8, loc="best", facecolor=bg, edgecolor=th["muted"], labelcolor=th["axes_fg"])
            self.figure.autofmt_xdate()
        self.draw_idle()


class SegmentView(QWidget):
    """一个板块：市场温度、入选组合、全部标的、选中标的的详情和走势。"""

    def __init__(self):
        super().__init__()
        self.scored = pd.DataFrame()
        self.picks = pd.DataFrame()
        self.data = {}

        self.temperature = TemperaturePanel()
        self.pick_table = make_table(["标的", *[c[0] for c in PICK_COLUMNS], "关键读数"])
        fit_rows(self.pick_table, max(config.MAX_PICKS.values()))
        self.cash_label = QLabel("")
        self.cash_label.setWordWrap(True)
        self.cash_label.setObjectName("muted")
        self.all_table = make_table(["标的", "状态", *[c[0] for c in ALL_COLUMNS], "说明"])
        self.chart = PriceChart()
        self.detail = QTextBrowser()
        self.detail.setMinimumHeight(100)
        self.detail.setHtml(self.placeholder())

        pick_box = QGroupBox("入选组合")
        box = QVBoxLayout(pick_box)
        box.addWidget(self.pick_table)
        box.addWidget(self.cash_label)
        box.addStretch(1)
        all_box = QGroupBox("全部标的 · 点击表头排序，选择标的查看详情")
        QVBoxLayout(all_box).addWidget(self.all_table)

        side = QSplitter(Qt.Orientation.Vertical)
        side.setChildrenCollapsible(False)
        side.setHandleWidth(10)
        side.addWidget(self.chart)
        side.addWidget(self.detail)
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)
        top.setHandleWidth(14)
        top.addWidget(self.temperature)
        top.addWidget(pick_box)
        top.setStretchFactor(0, 2)
        top.setStretchFactor(1, 4)
        top.setSizes([360, 950])
        top.setMinimumHeight(350)
        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.setChildrenCollapsible(False)
        bottom.setHandleWidth(14)
        bottom.addWidget(all_box)
        bottom.addWidget(side)
        bottom.setStretchFactor(0, 5)
        bottom.setStretchFactor(1, 3)
        outer = QSplitter(Qt.Orientation.Vertical)
        outer.setChildrenCollapsible(False)
        outer.setHandleWidth(12)
        outer.setMinimumHeight(700)
        outer.addWidget(top)
        outer.addWidget(bottom)
        outer.setStretchFactor(0, 0)  # 上半区按内容高度，多出的空间都给下面的全部标的
        outer.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: #f3f5f9; }")
        scroll.setWidget(outer)
        layout.addWidget(scroll)

        self.pick_table.itemSelectionChanged.connect(lambda: self.on_select(self.pick_table))
        self.all_table.itemSelectionChanged.connect(lambda: self.on_select(self.all_table))

    def placeholder(self) -> str:
        return f"<p style='color:{theme()['muted']}'>在表格中选中一行查看因子详情。</p>"

    def show_result(self, res: dict, data: dict) -> None:
        self.scored, self.picks, self.data = res["scored"], res["picks"], data
        self.temperature.show_temperature(res["temperature"])
        self.detail.setHtml(self.placeholder())
        self.chart.plot(None, "")
        if self.scored.empty:
            fill_table(self.pick_table, [])
            fill_table(self.all_table, [])
            self.cash_label.setText("没有拿到可用数据。")
            return

        pick_rows = [(sym, [Item(short(sym)), *[num_item(r.get(c), k) for _, c, k in PICK_COLUMNS],
                            text_item(highlights(r))], None)
                     for sym, r in self.picks.iterrows()]
        fill_table(self.pick_table, pick_rows, sort_col=1)
        if len(self.picks):
            invested = self.picks["weight"].sum()
            self.cash_label.setText(f"合计仓位 {invested:.1%}，现金 {1 - invested:.1%}")
        else:
            self.cash_label.setText("没有同时满足“未被排除、综合分达标”的标的，本板块全部持有现金。")

        all_rows = []
        for sym, r in self.scored.iterrows():
            status, s = r["status"], r["score"]
            key = STATUS_ORDER[status] * 1000 - (s if pd.notna(s) else -1)  # 先按状态，再按分数从高到低
            items = [Item(short(sym)), Item(status, key), *[num_item(r.get(c), k) for _, c, k in ALL_COLUMNS],
                     text_item(self.describe(sym, r))]
            all_rows.append((sym, items, status))
        fill_table(self.all_table, all_rows, sort_col=1, order=Qt.SortOrder.AscendingOrder)

    def describe(self, sym: str, r: pd.Series) -> str:
        if sym in self.picks.index:
            return f"入选，仓位 {self.picks.loc[sym, 'weight']:.1%}"
        if r["status"] != "候选":
            return r["note"]
        if pd.isna(r["score"]) or r["score"] < config.MIN_SCORE:
            return f"综合分低于 {config.MIN_SCORE}，宁可持有现金"
        return "名额已满"

    def on_select(self, table: QTableWidget) -> None:
        items = table.selectedItems()
        if not items:
            return
        sym = items[0].data(Qt.ItemDataRole.UserRole)
        if sym is None or sym not in self.scored.index:
            return
        r = self.scored.loc[sym]
        self.detail.setHtml(self.detail_html(sym, r))
        d = self.data.get(sym)
        self.chart.plot(d["px"] if d else None, short(sym))

    def detail_html(self, sym: str, r: pd.Series) -> str:
        th, status = theme(), r["status"]
        groups = "".join(f"<tr><td>{GROUP_NAMES[g]}</td><td align='right'>{fmt(r.get('s_' + g), 'num0')}</td></tr>"
                         for g in FACTOR_GROUPS)
        fields = "".join(f"<tr><td>{html.escape(label)}</td><td align='right'>{fmt(r.get(col), kind)}</td></tr>"
                         for label, col, kind in DETAIL_FIELDS)
        return (f"<h3>{html.escape(short(sym))} <span style='color:{th['status_fg'][status]}'>{status}</span></h3>"
                f"<p style='color:{th['muted']}'>{html.escape(sym)}</p>"
                f"<p>{html.escape(self.describe(sym, r))}</p>"
                f"<p><b>综合分 {fmt(r.get('score'), 'num0')}</b></p>"
                f"<table cellpadding='3'>{groups}</table><hr><table cellpadding='3'>{fields}</table>")


class Bridge(QObject):
    """后台线程通过这些信号把进度和结果交回界面线程。"""
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("霍华德·马克斯选股 · 币安合约")
        self.resize(1440, 920)
        self.setMinimumSize(1100, 780)
        self.stop_event = threading.Event()

        self.bridge = Bridge()
        self.bridge.progress.connect(self.on_progress)
        self.bridge.log.connect(self.append_log)
        self.bridge.done.connect(self.on_done)
        self.bridge.failed.connect(self.on_failed)

        self.proxy_edit = QLineEdit(default_proxy())
        self.proxy_edit.setPlaceholderText("留空表示直连")
        self.refresh_box = QCheckBox("忽略缓存重新下载")
        self.run_btn = QPushButton("运行选股")
        self.run_btn.setObjectName("primary")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("stop")
        self.inspect_btn = QPushButton("检查合约分类")
        self.open_btn = QPushButton("打开输出目录")
        self.run_btn.clicked.connect(lambda: self.start("run"))
        self.inspect_btn.clicked.connect(lambda: self.start("inspect"))
        self.stop_btn.clicked.connect(self.stop)
        self.open_btn.clicked.connect(self.open_output)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("status")

        self.views = {seg: SegmentView() for seg in pipeline.SEGMENTS}
        self.tabs = QTabWidget()
        for seg, view in self.views.items():
            self.tabs.addTab(view, SEGMENT_TITLES[seg])
        self.tabs.addTab(self.method_page(), "方法说明")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)

        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(16, 12, 16, 12)
        bar.setSpacing(12)
        bar.addWidget(QLabel("代理"))
        bar.addWidget(self.proxy_edit, 1)
        self.proxy_edit.setMaximumWidth(330)
        bar.addWidget(self.refresh_box)
        bar.addStretch(1)
        for btn in (self.run_btn, self.stop_btn, self.inspect_btn, self.open_btn):
            bar.addWidget(btn)
        prog = QHBoxLayout()
        prog.addWidget(self.status_label, 1)
        self.log_toggle = QPushButton("运行日志 ▾")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.toggled.connect(self.toggle_log)
        prog.addWidget(self.log_toggle)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tabs)
        split.addWidget(self.log_view)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        self.log_view.hide()

        central = QWidget()
        central.setObjectName("workspace")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 16)
        root.setSpacing(12)
        title = QLabel("马克斯策略研究台")
        title.setObjectName("title")
        subtitle = QLabel("市场周期  /  多因子筛选  /  组合配置")
        subtitle.setObjectName("subtitle")
        heading = QHBoxLayout()
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(subtitle)
        root.addLayout(heading)
        root.addWidget(toolbar)
        root.addLayout(prog)
        root.addWidget(self.progress_bar)
        root.addWidget(split, 1)
        self.setCentralWidget(central)
        self.set_busy(False)

    def toggle_log(self, visible: bool) -> None:
        self.log_view.setVisible(visible)
        self.log_toggle.setText("运行日志 ▴" if visible else "运行日志 ▾")

    def method_page(self) -> QTextBrowser:
        page = QTextBrowser()
        path = os.path.join(BASE_DIR, "README.md")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                page.setMarkdown(fh.read())
        return page

    def set_busy(self, busy: bool) -> None:
        for widget in (self.run_btn, self.inspect_btn, self.proxy_edit, self.refresh_box):
            widget.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    def start(self, task: str) -> None:
        self.stop_event.clear()
        self.set_busy(True)
        self.progress_bar.setRange(0, 0)  # 还不知道总数时显示滚动条
        self.status_label.setText("正在连接币安…")
        proxy, refresh = self.proxy_edit.text().strip(), self.refresh_box.isChecked()
        threading.Thread(target=self.work, args=(task, proxy, refresh), daemon=True).start()

    def work(self, task: str, proxy: str, refresh: bool) -> None:
        """在后台线程运行，只通过 bridge 的信号和界面通信。"""
        b = self.bridge
        try:
            if task == "inspect":
                b.log.emit(pipeline.inspect_markets(proxy))
                b.done.emit(None)
                return
            out = pipeline.run(proxy, refresh, log=b.log.emit, progress=b.progress.emit,
                               should_stop=self.stop_event.is_set)
            out["paths"] = write_outputs(out["results"], out["asof"])[:2]
            b.done.emit(out)
        except pipeline.Cancelled:
            b.failed.emit("")
        except Exception:
            b.failed.emit(traceback.format_exc())

    def stop(self) -> None:
        self.stop_event.set()
        self.stop_btn.setEnabled(False)
        self.status_label.setText("正在停止，等当前标的下载完…")

    def on_progress(self, k: int, total: int, symbol: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(k - 1)
        self.status_label.setText(f"下载 {k}/{total}：{symbol}")

    def on_done(self, out) -> None:
        self.set_busy(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        if out is None:
            self.status_label.setText("合约分类已输出到下方日志")
            return
        for i, seg in enumerate(pipeline.SEGMENTS):
            res = out["results"][seg]
            self.views[seg].show_result(res, out["data"])
            t = res["temperature"]["temperature"]
            self.tabs.setTabText(i, f"{SEGMENT_TITLES[seg]}  温度 {fmt(t, 'num0')}")
        md_path, csv_path = out["paths"]
        self.status_label.setText(f"完成，数据截至 {out['asof']:%Y-%m-%d} UTC 收盘")
        self.append_log(f"报告：{md_path}\n明细：{csv_path}")

    def on_failed(self, message: str) -> None:
        self.log_toggle.setChecked(True)
        self.set_busy(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        if not message:
            self.status_label.setText("已停止")
            self.append_log("已停止")
            return
        self.status_label.setText("运行失败，详见下方日志")
        self.append_log(message)
        QMessageBox.warning(self, "运行失败", message.strip().splitlines()[-1])

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def open_output(self) -> None:
        path = os.path.join(BASE_DIR, config.OUTPUT_DIR)
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def closeEvent(self, event) -> None:
        self.stop_event.set()  # 后台线程是守护线程，随进程退出
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    apply_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
