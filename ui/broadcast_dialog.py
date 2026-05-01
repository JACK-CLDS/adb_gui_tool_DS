"""
ui/broadcast_dialog.py - 发送广播对话框
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt

from core.adb_client import AdbClient


class BroadcastDialog(QDialog):
    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client

        self.setWindowTitle("发送广播")
        self.setMinimumWidth(500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.action_edit = QLineEdit()
        self.action_edit.setPlaceholderText("例如：android.intent.action.AIRPLANE_MODE")
        form.addRow("Action:", self.action_edit)

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

        self.send_btn = QPushButton("发送广播")
        self.send_btn.clicked.connect(self.send_broadcast)
        layout.addWidget(self.send_btn)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)

    def send_broadcast(self):
        action = self.action_edit.text().strip()
        if not action:
            QMessageBox.warning(self, "输入不完整", "请输入 Action")
            return

        cmd = f"am broadcast -a {action}"
        extra_key = self.extra_key_edit.text().strip()
        extra_value = self.extra_value_edit.text().strip()
        if extra_key and extra_value:
            extra_type = self.extra_type_combo.currentText()
            cmd += f" --es {extra_key} {extra_value}" if extra_type == "string" else \
                   f" --ei {extra_key} {int(extra_value)}" if extra_type == "int" and extra_value.isdigit() else \
                   f" --ez {extra_key} {extra_value.lower() == 'true'}" if extra_type == "boolean" else \
                   f" --ef {extra_key} {extra_value}"

        self.output_text.append(f">>> 执行: {cmd}")
        out = self.adb_client.shell_sync(cmd, self.serial, timeout=5)
        self.output_text.append(out)