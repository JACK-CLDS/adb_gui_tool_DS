"""
ui/settings_dialog.py - 全局设置对话框
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QDialogButtonBox, QMessageBox, QLabel
)
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置")
        self.setMinimumWidth(550)
        self.settings = ConfigManager.get_settings()
        self._has_changes = False
        self.init_ui()
        self.load_settings()
        self.connect_signals()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.adb_path_edit = QLineEdit()
        self.adb_browse_btn = QPushButton("浏览...")
        self.adb_browse_btn.clicked.connect(lambda: self.browse_file(self.adb_path_edit))
        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_path_edit)
        adb_layout.addWidget(self.adb_browse_btn)
        form.addRow("ADB 路径:", adb_layout)

        self.test_adb_btn = QPushButton("检测 ADB")
        self.test_adb_btn.clicked.connect(self.test_adb)
        form.addRow("", self.test_adb_btn)

        self.scrcpy_path_edit = QLineEdit()
        self.scrcpy_browse_btn = QPushButton("浏览...")
        self.scrcpy_browse_btn.clicked.connect(lambda: self.browse_file(self.scrcpy_path_edit))
        scrcpy_layout = QHBoxLayout()
        scrcpy_layout.addWidget(self.scrcpy_path_edit)
        scrcpy_layout.addWidget(self.scrcpy_browse_btn)
        form.addRow("scrcpy 路径:", scrcpy_layout)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("自动 (跟随系统)", "auto")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("简体中文", "zh_CN")
        form.addRow("语言:", self.lang_combo)

        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1000, 10000)
        self.refresh_spin.setSuffix(" 毫秒")
        form.addRow("设备列表刷新间隔:", self.refresh_spin)

        layout.addLayout(form)

        info_label = QLabel("提示：修改 ADB 路径后需要重新启动程序才能生效。")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件")
        if path:
            line_edit.setText(path)

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
        # 断开信号避免触发修改标记
        self.adb_path_edit.blockSignals(True)
        self.scrcpy_path_edit.blockSignals(True)
        self.lang_combo.blockSignals(True)
        self.refresh_spin.blockSignals(True)

        self.adb_path_edit.setText(self.settings.get("adb_path", ""))
        self.scrcpy_path_edit.setText(self.settings.get("scrcpy_path", ""))
        lang = self.settings.get("language", "auto")
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.refresh_spin.setValue(self.settings.get("auto_refresh_interval", 3000))

        # 恢复信号
        self.adb_path_edit.blockSignals(False)
        self.scrcpy_path_edit.blockSignals(False)
        self.lang_combo.blockSignals(False)
        self.refresh_spin.blockSignals(False)

    def connect_signals(self):
        self.adb_path_edit.textChanged.connect(self._on_setting_changed)
        self.scrcpy_path_edit.textChanged.connect(self._on_setting_changed)
        self.lang_combo.currentIndexChanged.connect(self._on_setting_changed)
        self.refresh_spin.valueChanged.connect(self._on_setting_changed)

    def _on_setting_changed(self):
        self._has_changes = True

    def save_settings(self):
        new_adb = self.adb_path_edit.text().strip()
        new_scrcpy = self.scrcpy_path_edit.text().strip()
        new_lang = self.lang_combo.currentData()
        new_refresh = self.refresh_spin.value()

        ConfigManager.set_setting("adb_path", new_adb)
        ConfigManager.set_setting("scrcpy_path", new_scrcpy)
        ConfigManager.set_setting("language", new_lang)
        ConfigManager.set_setting("auto_refresh_interval", new_refresh)

        if self._has_changes:
            QMessageBox.information(self, "设置已保存", "部分设置需要重启程序才能完全生效。")
        self.accept()
