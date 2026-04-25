"""
ui/settings_dialog.py - 全局设置对话框

允许用户修改：
    - adb 可执行文件路径
    - scrcpy 可执行文件路径
    - 语言
    - 自动刷新间隔
"""

import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QDialogButtonBox, QMessageBox, QLabel
)
from PyQt5.QtCore import Qt

from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置")
        self.setMinimumWidth(550)
        self.settings = ConfigManager.get_settings()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # ADB 路径
        self.adb_path_edit = QLineEdit()
        self.adb_browse_btn = QPushButton("浏览...")
        self.adb_browse_btn.clicked.connect(lambda: self.browse_file(self.adb_path_edit))
        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_path_edit)
        adb_layout.addWidget(self.adb_browse_btn)
        form.addRow("ADB 路径:", adb_layout)

        # 检测 ADB 按钮
        self.test_adb_btn = QPushButton("检测 ADB")
        self.test_adb_btn.clicked.connect(self.test_adb)
        form.addRow("", self.test_adb_btn)

        # scrcpy 路径
        self.scrcpy_path_edit = QLineEdit()
        self.scrcpy_browse_btn = QPushButton("浏览...")
        self.scrcpy_browse_btn.clicked.connect(lambda: self.browse_file(self.scrcpy_path_edit))
        scrcpy_layout = QHBoxLayout()
        scrcpy_layout.addWidget(self.scrcpy_path_edit)
        scrcpy_layout.addWidget(self.scrcpy_browse_btn)
        form.addRow("scrcpy 路径:", scrcpy_layout)

        # 语言
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("自动 (跟随系统)", "auto")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("简体中文", "zh_CN")
        form.addRow("语言:", self.lang_combo)

        # 自动刷新间隔
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1000, 10000)
        self.refresh_spin.setSuffix(" 毫秒")
        form.addRow("设备列表刷新间隔:", self.refresh_spin)

        layout.addLayout(form)

        # 提示信息
        info_label = QLabel("提示：修改 ADB 路径后需要重新启动程序才能生效。")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)

        # 按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def browse_file(self, line_edit):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件")
        if file_path:
            line_edit.setText(file_path)

    def test_adb(self):
        path = self.adb_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "测试 ADB", "请先选择 ADB 路径")
            return
        ok, version = SystemUtils.check_adb_version(path)
        if ok:
            QMessageBox.information(self, "测试成功", f"ADB 版本: {version}")
        else:
            QMessageBox.warning(self, "测试失败", f"无法执行 ADB:\n{version}")

    def load_settings(self):
        self.adb_path_edit.setText(self.settings.get("adb_path", ""))
        self.scrcpy_path_edit.setText(self.settings.get("scrcpy_path", ""))
        lang = self.settings.get("language", "auto")
        index = self.lang_combo.findData(lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        self.refresh_spin.setValue(self.settings.get("auto_refresh_interval", 3000))

    def save_settings(self):
        new_adb_path = self.adb_path_edit.text().strip()
        new_scrcpy_path = self.scrcpy_path_edit.text().strip()
        new_lang = self.lang_combo.currentData()
        new_refresh = self.refresh_spin.value()

        old_adb = self.settings.get("adb_path", "")
        old_scrcpy = self.settings.get("scrcpy_path", "")
        old_lang = self.settings.get("language", "auto")
        old_refresh = self.settings.get("auto_refresh_interval", 3000)

        # 保存设置
        ConfigManager.set_setting("adb_path", new_adb_path)
        ConfigManager.set_setting("scrcpy_path", new_scrcpy_path)
        ConfigManager.set_setting("language", new_lang)
        ConfigManager.set_setting("auto_refresh_interval", new_refresh)

        # 只有关键路径发生变化时才提示重启
        if new_adb_path != old_adb or new_scrcpy_path != old_scrcpy:
            QMessageBox.information(self, "设置已保存", "ADB 或 scrcpy 路径已修改，请重启程序以使更改生效。")
        else:
            QMessageBox.information(self, "设置已保存", "设置已保存。")
        self.accept()
