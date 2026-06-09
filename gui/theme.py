"""
Theme and Stylesheet Module
主题和样式表模块

QSS stylesheet + color constants replacing Tkinter _setup_styles().
QSS 样式表 + 颜色常量，替代 Tkinter _setup_styles()。
"""

# ── Color constants ──

COLORS = {
    'bg': '#f0f0f0',
    'bg_dark': '#e0e0e0',
    'bg_card': '#ffffff',
    'text': '#212529',
    'text_muted': '#6c757d',
    'text_source': '#0056b3',

    'connected': '#28a745',
    'disconnected': '#6c757d',
    'running': '#007bff',
    'paused': '#17a2b8',
    'error': '#dc3545',
    'warning': '#ffc107',
    'connecting': '#ffc107',

    'emergency_bg': '#dc3545',
    'emergency_active': '#c82333',
    'emergency_pressed': '#bd2130',
    'emergency_release_bg': '#ffc107',

    'btn_hover': '#e2e6ea',
    'border': '#cccccc',
    'separator': '#dee2e6',
}

# State color map (reused by indicators)
STATE_COLORS = {
    'disconnected': COLORS['disconnected'],
    'connecting': COLORS['connecting'],
    'connected': COLORS['connected'],
    'running': COLORS['running'],
    'paused': COLORS['paused'],
    'error': COLORS['error'],
    'emergency_stop': COLORS['error'],
}

# Log level colors
LOG_COLORS = {
    'DEBUG': '#6c757d',
    'INFO': '#212529',
    'WARNING': '#856404',
    'ERROR': '#721c24',
    'CRITICAL': '#721c24',
}


def load_stylesheet() -> str:
    """Return the global QSS stylesheet."""
    return """
/* ── Global ── */
QMainWindow, QWidget {
    background-color: #f0f0f0;
    font-family: "Microsoft YaHei UI", "Noto Sans CJK SC", "Arial", sans-serif;
    font-size: 10pt;
}

/* ── Group boxes ── */
QGroupBox {
    font-weight: bold;
    border: 1px solid #cccccc;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

/* ── Buttons ── */
QPushButton {
    padding: 5px 12px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    background-color: #ffffff;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #e2e6ea;
}
QPushButton:pressed {
    background-color: #d6d6d6;
}
QPushButton:disabled {
    color: #999999;
    background-color: #e8e8e8;
}

/* ── Emergency button ── */
QPushButton#emergencyButton {
    background-color: #dc3545;
    color: white;
    font-size: 14pt;
    font-weight: bold;
    border: 3px outset #8b0000;
    border-radius: 6px;
    min-height: 60px;
    min-width: 120px;
}
QPushButton#emergencyButton:hover {
    background-color: #c82333;
}
QPushButton#emergencyButton:pressed {
    background-color: #bd2130;
    border-style: inset;
}
QPushButton#emergencyButton[active="true"] {
    background-color: #ffc107;
    color: black;
    border-color: #cc9900;
}

/* ── Labels ── */
QLabel {
    color: #212529;
}
QLabel#headerLabel {
    font-size: 12pt;
    font-weight: bold;
}
QLabel#statusLabel {
    font-size: 9pt;
    color: #6c757d;
}

/* ── Text edit (log panel) ── */
QTextEdit#logTextEdit {
    font-family: "Consolas", "Noto Mono", monospace;
    font-size: 9pt;
    background-color: #ffffff;
    border: 1px solid #cccccc;
}

/* ── Combo box ── */
QComboBox {
    padding: 3px 8px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    background-color: #ffffff;
}

/* ── Sliders ── */
QSlider::groove:horizontal {
    height: 6px;
    background: #cccccc;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -5px 0;
    background: #007bff;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #0056b3;
}

/* ── Progress bar ── */
QProgressBar {
    border: 1px solid #cccccc;
    border-radius: 3px;
    text-align: center;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #007bff;
    border-radius: 2px;
}

/* ── Scroll area ── */
QScrollArea {
    border: none;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #cccccc;
    border-radius: 3px;
}
QTabBar::tab {
    padding: 6px 16px;
    border: 1px solid #cccccc;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom: 2px solid #007bff;
}
QTabBar::tab:!selected {
    background-color: #e8e8e8;
}
QTabBar::tab:hover:!selected {
    background-color: #d6d6d6;
}

/* ── Splitter ── */
QSplitter::handle {
    background-color: #cccccc;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}

/* ── Tree widget ── */
QTreeWidget, QListWidget, QTableWidget {
    border: 1px solid #cccccc;
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #007bff;
    color: white;
}
QHeaderView::section {
    background-color: #e8e8e8;
    border: 1px solid #cccccc;
    padding: 4px;
    font-weight: bold;
}

/* ── Line edit ── */
QLineEdit {
    padding: 4px 8px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    background-color: #ffffff;
}

/* ── Spin box ── */
QSpinBox, QDoubleSpinBox {
    padding: 3px;
    border: 1px solid #cccccc;
    border-radius: 3px;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #e8e8e8;
    border-top: 1px solid #cccccc;
}

/* ── Colored state buttons ── */
QPushButton.greenButton {
    background-color: #27ae60;
    color: white;
    font-weight: bold;
}
QPushButton.greenButton:hover { background-color: #2ecc71; }

QPushButton.redButton {
    background-color: #c0392b;
    color: white;
    font-weight: bold;
}
QPushButton.redButton:hover { background-color: #e74c3c; }

QPushButton.blueButton {
    background-color: #1a6ec2;
    color: white;
    font-weight: bold;
}
QPushButton.blueButton:hover { background-color: #2980d9; }

QPushButton.darkButton {
    background-color: #2c2c2c;
    color: white;
    font-weight: bold;
}
QPushButton.darkButton:hover { background-color: #444444; }

QPushButton.purpleButton {
    background-color: #8e44ad;
    color: white;
    font-weight: bold;
}
QPushButton.purpleButton:hover { background-color: #9b59b6; }

QPushButton.orangeButton {
    background-color: #d35400;
    color: white;
    font-weight: bold;
}
QPushButton.orangeButton:hover { background-color: #e67e22; }
"""
