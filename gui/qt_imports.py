"""
Central PySide6 Import File
PySide6 集中导入文件

Change this single file to swap between PySide6 and PyQt6.
修改此文件即可在 PySide6 和 PyQt6 之间切换。
"""

# Core
from PySide6.QtCore import (
    Qt, QObject, Signal, Slot, QTimer, QThread, QSize, QPoint, QRect,
    QPointF, QRectF, QEvent, QMimeData, Property,
)

# Widgets
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QSplitter, QTabWidget, QScrollArea, QGroupBox,
    QLabel, QPushButton, QToolButton, QCheckBox, QRadioButton,
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
    QSlider, QSpinBox, QDoubleSpinBox, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QStatusBar, QMenuBar, QMenu, QToolBar,
    QFileDialog, QMessageBox, QInputDialog, QColorDialog,
    QSizePolicy, QSpacerItem, QStackedWidget,
    QButtonGroup, QDialogButtonBox,
)

# GUI
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPixmap, QImage, QPainterPath, QIcon,
    QAction, QKeySequence, QCursor,
    QTextCharFormat, QTextCursor,
    QMouseEvent, QPaintEvent, QResizeEvent, QCloseEvent, QWheelEvent,
)
