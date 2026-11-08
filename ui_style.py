"""Shared visual theme for the strategy desktop application."""
from PyQt6.QtGui import QColor, QFont, QPalette

STYLE = """
QWidget { color: #243248; font-family: 'Microsoft YaHei UI'; font-size: 12px; }
QMainWindow, QWidget#workspace { background: #f3f5f9; }
QLabel { background: transparent; }
QLabel#title { font-size: 23px; font-weight: 700; color: #172b4d; }
QLabel#subtitle, QLabel#muted { color: #768397; }
QLabel#status { color: #52657e; }
QWidget#toolbar { background: white; border: 1px solid #e2e7ef; border-radius: 10px; }
QGroupBox { background: white; border: 1px solid #e2e7ef; border-radius: 10px;
    margin-top: 14px; padding: 18px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
    left: 16px; padding: 0 7px; color: #334968; }
QPushButton { background: white; border: 1px solid #d9e1ed; border-radius: 6px;
    padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #eef4ff; border-color: #91afe0; }
QPushButton:pressed { background: #dce8fc; }
QPushButton#primary { background: #285dcc; color: white; border-color: #285dcc; }
QPushButton#primary:hover { background: #204fae; }
QPushButton:disabled { color: #a3adbc; background: #f4f6f9; border-color: #e6eaf0; }
QPushButton#stop { color: #b34d4d; }
QPushButton#stop:disabled { color: #a3adbc; }
QLineEdit { background: #f8fafd; border: 1px solid #dce3ed; border-radius: 6px;
    padding: 8px 10px; selection-background-color: #285dcc; }
QLineEdit:focus { border-color: #628de2; background: white; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #748297; padding: 11px 21px;
    border-bottom: 3px solid transparent; margin-right: 8px; font-weight: 600; }
QTabBar::tab:selected { color: #285dcc; border-bottom-color: #285dcc; }
QTabBar::tab:hover { background: #eaf0fa; }
QTableWidget { background: white; alternate-background-color: #f8fafd; border: none;
    selection-background-color: #e5edff; selection-color: #174499; outline: none; }
QTableWidget::item { padding: 6px 9px; border-bottom: 1px solid #eef1f6; }
QTableWidget::item:selected { background: #e5edff; color: #174499; }
QHeaderView::section { background: #f3f6fb; color: #63738b; border: none;
    border-bottom: 1px solid #e4eaf2; padding: 9px; font-weight: 600; }
QTextBrowser { background: white; border: 1px solid #e2e7ef; border-radius: 8px; padding: 12px; }
QPlainTextEdit { background: #f8fafd; color: #60718a; border: 1px solid #e2e7ef;
    border-radius: 8px; padding: 10px; font-family: Consolas, 'Microsoft YaHei UI'; font-size: 11px; }
QProgressBar { background: #e5ebf4; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #4777d5; border-radius: 3px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #dce5f3; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 0; }
QScrollBar::handle { background: #c9d3e1; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #243248; color: white; border: none; padding: 6px; }
"""


def apply_style(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#f3f5f9"),
                        (QPalette.ColorRole.Base, "#ffffff"),
                        (QPalette.ColorRole.Text, "#243248"),
                        (QPalette.ColorRole.WindowText, "#243248"),
                        (QPalette.ColorRole.Highlight, "#e5edff"),
                        (QPalette.ColorRole.HighlightedText, "#174499")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(STYLE)
