"""
ui/broadcast_dialog.py - 发送广播对话框 (Send Broadcast Dialog)

功能 (Features):
    - 输入 Android broadcast action (Enter broadcast action)
    - 可选附加 extra 键值对 (Optional extra key-value pair)
    - 执行 adb shell am broadcast 并显示输出 (Execute and display output)

依赖 (Dependencies): PyQt5, core.adb_client
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QMessageBox,
    QComboBox
)
from PyQt5.QtCore import Qt

from core.adb_client import AdbClient


class BroadcastDialog(QDialog):
    """发送广播对话框 (Broadcast dialog)"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client

        self.setWindowTitle("发送广播")
        self.setMinimumWidth(500)
        self.init_ui()

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建对话框界面 (Create dialog UI)"""
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Action 输入 (Action input)
        self.action_edit = QLineEdit()
        self.action_edit.setPlaceholderText("例如：android.intent.action.AIRPLANE_MODE")
        form.addRow("Action:", self.action_edit)

        # Extra 参数 (Extra parameters)
        self.extra_key_edit = QLineEdit()
        self.extra_key_edit.setPlaceholderText("键名")
        self.extra_type_combo = QComboBox()
        self.extra_type_combo.addItems(["string", "int", "boolean", "float"])
        self.extra_value_edit = QLineEdit()
        self.extra_value_edit.setPlaceholderText("值")

        extra_layout = QHBoxLayout()
        extra_layout.addWidget(QLabel("键:"))
        extra_layout.addWidget(self.extra_key_edit)
        extra_layout.addWidget(QLabel("类型:"))
        extra_layout.addWidget(self.extra_type_combo)
        extra_layout.addWidget(QLabel("值:"))
        extra_layout.addWidget(self.extra_value_edit)
        form.addRow("Extra:", extra_layout)

        layout.addLayout(form)

        # 发送按钮 (Send button)
        self.send_btn = QPushButton("发送广播")
        self.send_btn.clicked.connect(self.send_broadcast)
        layout.addWidget(self.send_btn)

        # 输出区域 (Output area)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)

    # ========== 发送逻辑 (Send Logic) ==========

    def send_broadcast(self):
        """构建并发送广播命令 (Build and send broadcast command)"""
        action = self.action_edit.text().strip()
        if not action:
            QMessageBox.warning(self, "输入不完整", "请输入 Action")
            return

        # 基础命令 (Base command)
        cmd = f"am broadcast -a {action}"

        # 处理 extra 参数 (Handle extra)
        extra_key = self.extra_key_edit.text().strip()
        extra_value = self.extra_value_edit.text().strip()
        if extra_key and extra_value:
            extra_type = self.extra_type_combo.currentText()
            if extra_type == "string":
                cmd += f" --es {extra_key} {extra_value}"
            elif extra_type == "int" and extra_value.isdigit():
                cmd += f" --ei {extra_key} {int(extra_value)}"
            elif extra_type == "boolean":
                val = "true" if extra_value.lower() == "true" else "false"
                cmd += f" --ez {extra_key} {val}"
            elif extra_type == "float":
                cmd += f" --ef {extra_key} {extra_value}"

        # 执行命令并显示结果 (Execute and display)
        self.output_text.append(f">>> 执行: {cmd}")
        out = self.adb_client.shell_sync(cmd, self.serial, timeout=5)
        self.output_text.append(out)
