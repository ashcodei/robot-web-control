"""
Hardware Connection Check Dialog (PySide6)
硬件连接检查对话框

Popup dialog that checks all hardware device connectivity.
"""

import os
import socket
import threading
from typing import Dict, Any, Optional, Callable
from gui.qt_imports import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame,
    QPainter, QColor, QBrush, Qt,
)
from gui.widgets.hardware_status_card import StatusIndicator
from config.settings import get_settings, ConfigValidator
from config.i18n import t, get_i18n, Language
from app_core.logger import get_logger
from gui.signals import get_thread_bridge

logger = get_logger(__name__)

DEVICE_CHECK_MAP = {
    'gantry': {
        'type': 'serial', 'config_section': 'gantry',
        'addr_field': 'serial_port', 'name_key': 'hardware.gantry',
        'type_key': 'conn.type_serial',
    },
    'lebai': {
        'type': 'tcp', 'config_section': 'lebai',
        'addr_field': 'ip', 'port_field': 'port',
        'name_key': 'hardware.lebai', 'type_key': 'conn.type_tcp',
    },
    'dual_arm': {
        'type': 'tcp', 'config_section': 'dual_arm',
        'addr_field': 'ip', 'port_field': 'port',
        'name_key': 'hardware.dual_arm', 'type_key': 'conn.type_tcp',
    },
    'linker_hand': {
        'type': 'can', 'config_section': 'linker_hand',
        'addr_field': 'can_interface', 'name_key': 'hardware.linker_hand',
        'type_key': 'conn.type_can',
    },
    'wok': {
        'type': 'serial', 'config_section': 'wok',
        'addr_field': 'serial_port', 'name_key': 'hardware.wok',
        'type_key': 'conn.type_serial',
    },
    'gripper': {
        'type': 'serial', 'config_section': 'gripper',
        'addr_field': 'serial_port', 'name_key': 'hardware.gripper',
        'type_key': 'conn.type_serial',
    },
    'teleop': {
        'type': 'tcp', 'config_section': 'teleop',
        'addr_field': 'ros_host', 'port_field': 'ros_port',
        'name_key': 'hardware.teleop', 'type_key': 'conn.type_ws',
    },
    'dexhand_left': {
        'type': 'can', 'config_section': 'dexhand',
        'addr_field': 'can_interface', 'name_key': 'hardware.dexhand_left',
        'type_key': 'conn.type_can',
    },
    'dexhand_right': {
        'type': 'can', 'config_section': 'dexhand',
        'addr_field': 'can_interface', 'name_key': 'hardware.dexhand_right',
        'type_key': 'conn.type_can',
    },
}

STATUS_COLORS = {
    'unchecked': '#999999',
    'checking': '#f0ad4e',
    'reachable': '#ff8c00',
    'connected': '#28a745',
    'unreachable': '#dc3545',
    'error': '#dc3545',
    'connecting': '#f0ad4e',
    'connect_failed': '#dc3545',
    'disconnected': '#999999',
}


def _ping_tcp(ip, port, timeout=1.0):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _check_serial(port_path):
    return os.path.exists(port_path)


def _check_can(interface):
    return os.path.exists(f'/sys/class/net/{interface}')


class ConnectionCheckDialog(QDialog):
    """Hardware connection check popup dialog."""

    def __init__(self, parent, hardware: Dict[str, Any],
                 on_close_callback: Optional[Callable] = None):
        super().__init__(parent)

        self._hardware = hardware
        self._on_close_callback = on_close_callback
        self._settings = get_settings()
        self._i18n = get_i18n()
        self._bridge = get_thread_bridge()
        self._closed = False

        self._device_rows: Dict[str, Dict[str, Any]] = {}
        self._device_status: Dict[str, str] = {}
        self._editing: Dict[str, bool] = {}

        self._build_dialog()
        self._sync_live_status()
        self._i18n.add_callback(self._on_language_changed)

    def _sync_live_status(self):
        try:
            from hardware.base_hardware import HardwareState
        except ImportError:
            return

        state_map = {
            HardwareState.CONNECTED: 'connected',
            HardwareState.RUNNING: 'connected',
            HardwareState.CONNECTING: 'connecting',
            HardwareState.ERROR: 'error',
            HardwareState.EMERGENCY_STOP: 'error',
            HardwareState.DISCONNECTED: 'disconnected',
            HardwareState.PAUSED: 'connected',
        }

        for dev_name in DEVICE_CHECK_MAP:
            controller = self._hardware.get(dev_name)
            if controller is None or not hasattr(controller, 'state'):
                continue
            dialog_status = state_map.get(controller.state)
            if dialog_status:
                self._update_device_status(dev_name, dialog_status)

    def _build_dialog(self):
        self.setWindowTitle(t("conn.title"))
        self.resize(780, 520)
        self.setMinimumSize(750, 480)

        layout = QVBoxLayout(self)

        # Title
        self._title_label = QLabel(t("conn.title"))
        self._title_label.setObjectName("headerLabel")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        # Device rows
        self._devices_frame = QVBoxLayout()
        for dev_name in DEVICE_CHECK_MAP:
            self._build_device_row(dev_name)
        layout.addLayout(self._devices_frame)

        layout.addStretch()

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Button bar
        btn_layout = QHBoxLayout()

        self._check_all_btn = QPushButton(t("conn.check_all"))
        self._check_all_btn.clicked.connect(self.check_all)
        btn_layout.addWidget(self._check_all_btn)

        self._connect_reachable_btn = QPushButton(t("conn.connect_reachable"))
        self._connect_reachable_btn.clicked.connect(self._connect_all_reachable)
        btn_layout.addWidget(self._connect_reachable_btn)

        btn_layout.addStretch()

        self._lang_btn = QPushButton("中文/EN")
        self._lang_btn.setFixedWidth(80)
        self._lang_btn.clicked.connect(self._toggle_language)
        btn_layout.addWidget(self._lang_btn)

        self._close_btn = QPushButton(t("common.close"))
        self._close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)

    def _safe_callback(self, callback):
        """Thread-safe callback via signal."""
        if self._closed:
            return
        self._bridge.gui_callback.emit(callback)

    def _get_device_address(self, dev_name):
        info = DEVICE_CHECK_MAP[dev_name]
        section = info['config_section']
        config_obj = getattr(self._settings, section)
        addr = getattr(config_obj, info['addr_field'])
        if 'port_field' in info:
            port = getattr(config_obj, info['port_field'])
            return f"{addr}:{port}"
        return str(addr)

    def _build_device_row(self, dev_name):
        info = DEVICE_CHECK_MAP[dev_name]
        row = QHBoxLayout()

        indicator = StatusIndicator(self, size=14)
        row.addWidget(indicator)

        name_label = QLabel(t(info['name_key']))
        name_label.setFixedWidth(110)
        row.addWidget(name_label)

        type_label = QLabel(t(info['type_key']))
        type_label.setFixedWidth(70)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_label.setStyleSheet("font-size: 9pt; color: #6c757d;")
        row.addWidget(type_label)

        addr_label = QLabel(self._get_device_address(dev_name))
        addr_label.setFixedWidth(160)
        row.addWidget(addr_label)

        addr_entry = QLineEdit()
        addr_entry.setFixedWidth(160)
        addr_entry.hide()
        row.addWidget(addr_entry)

        edit_btn = QPushButton(t("conn.edit"))
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda checked, dn=dev_name: self._on_edit_address(dn))
        row.addWidget(edit_btn)

        status_label = QLabel(t("conn.unchecked"))
        status_label.setFixedWidth(90)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(status_label)

        action_btn = QPushButton(t("common.connect"))
        action_btn.setFixedWidth(90)
        action_btn.clicked.connect(lambda checked, dn=dev_name: self._on_action_button(dn))
        row.addWidget(action_btn)

        self._devices_frame.addLayout(row)

        self._device_rows[dev_name] = {
            'indicator': indicator,
            'name_label': name_label,
            'type_label': type_label,
            'addr_label': addr_label,
            'addr_entry': addr_entry,
            'edit_btn': edit_btn,
            'status_label': status_label,
            'action_btn': action_btn,
        }
        self._device_status[dev_name] = 'unchecked'
        self._editing[dev_name] = False

    def _update_device_status(self, dev_name, status):
        if dev_name not in self._device_rows:
            return

        self._device_status[dev_name] = status
        row = self._device_rows[dev_name]

        color = STATUS_COLORS.get(status, '#999999')
        row['indicator'].set_color(color)

        status_key_map = {
            'unchecked': 'conn.unchecked', 'checking': 'conn.checking',
            'reachable': 'conn.reachable', 'connected': 'conn.connected',
            'unreachable': 'conn.unreachable', 'error': 'common.error',
            'connecting': 'conn.connecting', 'connect_failed': 'conn.connect_failed',
            'disconnected': 'conn.disconnected',
        }
        row['status_label'].setText(t(status_key_map.get(status, 'conn.unchecked')))

        if status == 'connected':
            row['action_btn'].setText(t("common.disconnect"))
            try:
                row['action_btn'].clicked.disconnect()
            except RuntimeError:
                pass
            row['action_btn'].clicked.connect(lambda checked, dn=dev_name: self._disconnect_device(dn))
            row['action_btn'].setEnabled(True)
        elif status in ('error', 'connect_failed'):
            row['action_btn'].setText(t("conn.retry"))
            row['action_btn'].setEnabled(True)
            try:
                row['action_btn'].clicked.disconnect()
            except RuntimeError:
                pass
            row['action_btn'].clicked.connect(lambda checked, dn=dev_name: self._on_action_button(dn))
        elif status in ('checking', 'connecting'):
            row['action_btn'].setEnabled(False)
        else:
            row['action_btn'].setText(t("common.connect"))
            row['action_btn'].setEnabled(True)
            try:
                row['action_btn'].clicked.disconnect()
            except RuntimeError:
                pass
            row['action_btn'].clicked.connect(lambda checked, dn=dev_name: self._on_action_button(dn))

    def check_all(self):
        for dev_name in DEVICE_CHECK_MAP:
            self._update_device_status(dev_name, 'checking')
            threading.Thread(
                target=self._check_single_device, args=(dev_name,),
                daemon=True, name=f"ConnCheck-{dev_name}"
            ).start()

    def _check_single_device(self, dev_name):
        info = DEVICE_CHECK_MAP[dev_name]
        section = info['config_section']
        config_obj = getattr(self._settings, section)

        try:
            reachable = False
            if info['type'] == 'tcp':
                ip = getattr(config_obj, info['addr_field'])
                port = getattr(config_obj, info['port_field'])
                reachable = _ping_tcp(ip, port)
            elif info['type'] == 'serial':
                port_path = getattr(config_obj, info['addr_field'])
                reachable = _check_serial(port_path)
            elif info['type'] == 'can':
                interface = getattr(config_obj, info['addr_field'])
                reachable = _check_can(interface)

            if reachable:
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'reachable'))
                self._do_connect(dev_name)
            else:
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'unreachable'))
        except Exception as e:
            logger.warning(f"Connection check failed for {dev_name}: {e}")
            self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'error'))

    def _on_action_button(self, dev_name):
        self._update_device_status(dev_name, 'connecting')
        threading.Thread(
            target=self._do_connect, args=(dev_name,),
            daemon=True, name=f"Connect-{dev_name}"
        ).start()

    def _do_connect(self, dev_name):
        self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connecting'))

        controller = self._hardware.get(dev_name)
        if controller is None:
            self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'error'))
            return

        connect_timeout = 5
        result_holder = [None]
        exception_holder = [None]

        def do_connect():
            try:
                result_holder[0] = controller.connect()
            except Exception as e:
                exception_holder[0] = e

        connect_thread = threading.Thread(target=do_connect, daemon=True)
        connect_thread.start()
        connect_thread.join(timeout=connect_timeout)

        if connect_thread.is_alive():
            self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connect_failed'))
            return

        if exception_holder[0]:
            self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connect_failed'))
            return

        try:
            from hardware.base_hardware import HardwareState
            result = result_holder[0]
            actually_connected = (
                result is True
                and hasattr(controller, 'state')
                and controller.state in (HardwareState.CONNECTED, HardwareState.RUNNING)
            )
            if actually_connected:
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connected'))
            else:
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connect_failed'))
        except Exception:
            self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'connect_failed'))

    def _disconnect_device(self, dev_name):
        controller = self._hardware.get(dev_name)
        if controller is None:
            return

        def do_disconnect():
            try:
                controller.disconnect()
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'disconnected'))
            except Exception:
                self._safe_callback(lambda dn=dev_name: self._update_device_status(dn, 'error'))

        threading.Thread(target=do_disconnect, daemon=True, name=f"Disconnect-{dev_name}").start()

    def _connect_all_reachable(self):
        for dev_name, status in self._device_status.items():
            if status == 'reachable':
                self._on_action_button(dev_name)

    def _on_edit_address(self, dev_name):
        row = self._device_rows[dev_name]
        if not self._editing[dev_name]:
            self._editing[dev_name] = True
            row['addr_entry'].setText(self._get_device_address(dev_name))
            row['addr_label'].hide()
            row['addr_entry'].show()
            row['edit_btn'].setText(t("conn.save_addr"))
            try:
                row['edit_btn'].clicked.disconnect()
            except RuntimeError:
                pass
            row['edit_btn'].clicked.connect(lambda checked, dn=dev_name: self._on_save_address(dn))
        else:
            self._cancel_edit(dev_name)

    def _on_save_address(self, dev_name):
        row = self._device_rows[dev_name]
        new_value = row['addr_entry'].text().strip()
        info = DEVICE_CHECK_MAP[dev_name]

        if not new_value:
            self._cancel_edit(dev_name)
            return

        section = info['config_section']
        update_kwargs = {}

        if info['type'] == 'tcp':
            if ':' in new_value:
                parts = new_value.rsplit(':', 1)
                ip = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    self._cancel_edit(dev_name)
                    return
                if not ConfigValidator.validate_ip(ip, f"{dev_name}.ip"):
                    self._cancel_edit(dev_name)
                    return
                if not ConfigValidator.validate_port(port, f"{dev_name}.port"):
                    self._cancel_edit(dev_name)
                    return
                update_kwargs[info['addr_field']] = ip
                update_kwargs[info['port_field']] = port
            else:
                if not ConfigValidator.validate_ip(new_value, f"{dev_name}.ip"):
                    self._cancel_edit(dev_name)
                    return
                update_kwargs[info['addr_field']] = new_value
        elif info['type'] in ('serial', 'can'):
            update_kwargs[info['addr_field']] = new_value

        self._settings.update(section, **update_kwargs)

        for hw_name, hw_info in DEVICE_CHECK_MAP.items():
            if hw_info['config_section'] == section:
                controller = self._hardware.get(hw_name)
                if controller and hasattr(controller, '_can_interface') and 'can_interface' in update_kwargs:
                    controller._can_interface = update_kwargs['can_interface']

        self._editing[dev_name] = False
        row['addr_entry'].hide()
        row['addr_label'].setText(self._get_device_address(dev_name))
        row['addr_label'].show()
        row['edit_btn'].setText(t("conn.edit"))
        try:
            row['edit_btn'].clicked.disconnect()
        except RuntimeError:
            pass
        row['edit_btn'].clicked.connect(lambda checked, dn=dev_name: self._on_edit_address(dn))

        for sibling_name, sibling_info in DEVICE_CHECK_MAP.items():
            if sibling_name != dev_name and sibling_info['config_section'] == section:
                if sibling_name in self._device_rows and not self._editing.get(sibling_name, False):
                    self._device_rows[sibling_name]['addr_label'].setText(
                        self._get_device_address(sibling_name))

    def _cancel_edit(self, dev_name):
        row = self._device_rows[dev_name]
        self._editing[dev_name] = False
        row['addr_entry'].hide()
        row['addr_label'].show()
        row['edit_btn'].setText(t("conn.edit"))
        try:
            row['edit_btn'].clicked.disconnect()
        except RuntimeError:
            pass
        row['edit_btn'].clicked.connect(lambda checked, dn=dev_name: self._on_edit_address(dn))

    def _on_language_changed(self, language):
        self.setWindowTitle(t("conn.title"))
        self._title_label.setText(t("conn.title"))
        self._check_all_btn.setText(t("conn.check_all"))
        self._connect_reachable_btn.setText(t("conn.connect_reachable"))
        self._close_btn.setText(t("common.close"))

        for dev_name, row in self._device_rows.items():
            info = DEVICE_CHECK_MAP[dev_name]
            row['name_label'].setText(t(info['name_key']))
            row['type_label'].setText(t(info['type_key']))
            if not self._editing.get(dev_name, False):
                row['addr_label'].setText(self._get_device_address(dev_name))
            if self._editing.get(dev_name, False):
                row['edit_btn'].setText(t("conn.save_addr"))
            else:
                row['edit_btn'].setText(t("conn.edit"))
            self._update_device_status(dev_name, self._device_status[dev_name])

    def update_language(self):
        self._on_language_changed(self._i18n.language)

    def _toggle_language(self):
        self._i18n.toggle_language()

    def closeEvent(self, event):
        self._closed = True
        try:
            self._i18n.remove_callback(self._on_language_changed)
        except Exception:
            pass
        if self._on_close_callback:
            try:
                self._on_close_callback()
            except Exception:
                pass
        super().closeEvent(event)
