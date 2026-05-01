"""
ui/proxy_tab.py - 设备代理设置控件

功能：
    - 显示当前全局 HTTP 代理
    - 设置代理（主机:端口）
    - 清除代理
    - 状态提示
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core.adb_client import AdbClient


class ProxyTab(QWidget):
    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client

        self.init_ui()
        self.load_proxy_status()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 当前代理状态组
        status_group = QGroupBox("当前代理")
        status_layout = QFormLayout()
        self.current_proxy_label = QLabel("未设置")
        self.current_proxy_label.setStyleSheet("font-weight: bold;")
        status_layout.addRow("HTTP 代理:", self.current_proxy_label)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # 设置代理组
        set_group = QGroupBox("设置代理")
        set_layout = QFormLayout()
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("例如 192.168.1.100 或 proxy.example.com")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("例如 8080")
        self.port_edit.setMaximumWidth(100)
        set_layout.addRow("主机:", self.host_edit)
        set_layout.addRow("端口:", self.port_edit)

        btn_layout = QHBoxLayout()
        self.set_btn = QPushButton("应用代理")
        self.set_btn.clicked.connect(self.set_proxy)
        self.clear_btn = QPushButton("清除代理")
        self.clear_btn.clicked.connect(self.clear_proxy)
        btn_layout.addWidget(self.set_btn)
        btn_layout.addWidget(self.clear_btn)
        set_layout.addRow(btn_layout)

        set_group.setLayout(set_layout)
        layout.addWidget(set_group)

        # 状态消息
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    def load_proxy_status(self):
        """读取设备当前代理并显示"""
        try:
            out = self.adb_client.shell_sync("settings get global http_proxy", self.serial, timeout=3)
            proxy = out.strip()
            if proxy and proxy != ":0" and proxy != "null":
                self.current_proxy_label.setText(proxy)
            else:
                self.current_proxy_label.setText("未设置")
        except Exception:
            self.current_proxy_label.setText("读取失败")

    def set_proxy(self):
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        if not host or not port:
            QMessageBox.warning(self, "输入不完整", "请填写主机和端口。")
            return
        if not port.isdigit():
            QMessageBox.warning(self, "无效端口", "端口必须是数字。")
            return

        proxy_value = f"{host}:{port}"
        self.status_label.setText("正在设置代理...")
        self.adb_client.shell_sync(
            f"settings put global http_proxy {proxy_value}",
            self.serial,
            timeout=3
        )
        self.load_proxy_status()
        self.status_label.setText("代理已设置")
        QTimer.singleShot(3000, lambda: self.status_label.clear())
        QMessageBox.information(self, "设置成功", f"代理已设置为 {proxy_value}")

    def clear_proxy(self):
        reply = QMessageBox.question(self, "确认", "确定要清除代理设置吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.status_label.setText("正在清除代理...")
        # 使用 :0 表示禁用代理，某些设备可能需要 delete，这里用 put global http_proxy :0
        self.adb_client.shell_sync(
            "settings put global http_proxy :0",
            self.serial,
            timeout=3
        )
        self.load_proxy_status()
        self.status_label.setText("代理已清除")
        QTimer.singleShot(3000, lambda: self.status_label.clear())
        QMessageBox.information(self, "已清除", "代理设置已清除。")