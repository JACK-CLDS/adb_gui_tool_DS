"""
ui/proxy_tab.py - 设备代理设置控件 (Device Proxy Settings)

功能 (Features):
    - 显示当前全局 HTTP 代理 (Display current global HTTP proxy)
    - 设置代理（主机:端口） (Set proxy via host:port)
    - 清除代理 (Clear proxy)
    - 操作状态反馈 (Operation status feedback)

多语言 (i18n):
    所有用户可见字符串均已使用 self.tr() 包裹，可通过翻译文件切换语言。
    All user-visible strings are wrapped with self.tr() for translation.

依赖 (Dependencies): PyQt5, core.adb_client
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer

from core.adb_client import AdbClient


class ProxyTab(QWidget):
    """代理设置控件 (Proxy settings widget)"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client

        self.init_ui()
        self.load_proxy_status()

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建界面布局 (Create UI layout)"""
        layout = QVBoxLayout(self)

        # ---- 当前代理状态 (Current proxy status) ----
        status_group = QGroupBox(self.tr("当前代理"))
        status_layout = QFormLayout()
        self.current_proxy_label = QLabel(self.tr("未设置"))
        self.current_proxy_label.setStyleSheet("font-weight: bold;")
        status_layout.addRow(self.tr("HTTP 代理:"), self.current_proxy_label)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # ---- 设置代理 (Set proxy) ----
        set_group = QGroupBox(self.tr("设置代理"))
        set_layout = QFormLayout()

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(
            self.tr("例如 192.168.1.100 或 proxy.example.com")
        )
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText(self.tr("例如 8080"))
        self.port_edit.setMaximumWidth(100)
        set_layout.addRow(self.tr("主机:"), self.host_edit)
        set_layout.addRow(self.tr("端口:"), self.port_edit)

        btn_layout = QHBoxLayout()
        self.set_btn = QPushButton(self.tr("应用代理"))
        self.set_btn.clicked.connect(self.set_proxy)
        self.clear_btn = QPushButton(self.tr("清除代理"))
        self.clear_btn.clicked.connect(self.clear_proxy)
        btn_layout.addWidget(self.set_btn)
        btn_layout.addWidget(self.clear_btn)
        set_layout.addRow(btn_layout)

        set_group.setLayout(set_layout)
        layout.addWidget(set_group)

        # ---- 状态消息 (Status message) ----
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    # ========== 代理状态 (Proxy Status) ==========

    def load_proxy_status(self):
        """读取设备当前代理并显示 (Read and display current proxy)"""
        try:
            out = self.adb_client.shell_sync("settings get global http_proxy", self.serial, timeout=3)
            proxy = out.strip()
            if proxy and proxy != ":0" and proxy != "null":
                self.current_proxy_label.setText(proxy)
            else:
                self.current_proxy_label.setText(self.tr("未设置"))
        except Exception:
            self.current_proxy_label.setText(self.tr("读取失败"))

    # ========== 设置与清除 (Set & Clear) ==========

    def set_proxy(self):
        """设置设备全局 HTTP 代理 (Set global HTTP proxy on device)"""
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        if not host or not port:
            QMessageBox.warning(
                self,
                self.tr("输入不完整"),
                self.tr("请填写主机和端口。")
            )
            return
        if not port.isdigit():
            QMessageBox.warning(
                self,
                self.tr("无效端口"),
                self.tr("端口必须是数字。")
            )
            return

        proxy_value = f"{host}:{port}"
        self.status_label.setText(self.tr("正在设置代理..."))
        self.adb_client.shell_sync(
            f"settings put global http_proxy {proxy_value}",
            self.serial,
            timeout=3
        )
        self.load_proxy_status()
        self.status_label.setText(self.tr("代理已设置"))
        QTimer.singleShot(3000, lambda: self.status_label.clear())
        QMessageBox.information(
            self,
            self.tr("设置成功"),
            self.tr("代理已设置为 {proxy}").format(proxy=proxy_value)
        )

    def clear_proxy(self):
        """清除设备全局 HTTP 代理 (Clear global HTTP proxy)"""
        reply = QMessageBox.question(
            self,
            self.tr("确认"),
            self.tr("确定要清除代理设置吗？"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.status_label.setText(self.tr("正在清除代理..."))
        # 使用 :0 表示禁用代理 (Use :0 to disable proxy)
        self.adb_client.shell_sync(
            "settings put global http_proxy :0",
            self.serial,
            timeout=3
        )
        self.load_proxy_status()
        self.status_label.setText(self.tr("代理已清除"))
        QTimer.singleShot(3000, lambda: self.status_label.clear())
        QMessageBox.information(
            self,
            self.tr("已清除"),
            self.tr("代理设置已清除。")
        )
