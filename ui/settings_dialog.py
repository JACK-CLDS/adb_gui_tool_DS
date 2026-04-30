"""
ui/settings_dialog.py - 全局设置对话框（含快捷键设置与恢复默认）
"""

import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QDialogButtonBox, QMessageBox, QLabel,
    QGroupBox, QKeySequenceEdit
)
from PyQt5.QtGui import QKeySequence
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class SettingsDialog(QDialog):
    # 默认配置常量
    DEFAULTS = {
        "adb_path": "",
        "scrcpy_path": "",
        "language": "auto",
        "auto_refresh_interval": 3000,
        "shortcut_close": "Ctrl+W",
        "shortcut_screenshot": "Ctrl+Shift+S",
        "shortcut_refresh_info": "F5",
        "shortcut_recording": "Ctrl+Shift+R",
    }

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

        # ADB 路径
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

        # 刷新间隔
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1000, 10000)
        self.refresh_spin.setSuffix(" 毫秒")
        form.addRow("设备列表刷新间隔:", self.refresh_spin)

        layout.addLayout(form)

        # ---------- 快捷键设置 ----------
        shortcut_group = QGroupBox("快捷键 (部分修改需重新打开设备窗口)")
        shortcut_form = QFormLayout()

        self.shortcut_edits = {}
        shortcut_descriptions = {
            "close": "关闭设备窗口",
            "screenshot": "截图",
            "refresh_info": "刷新设备信息",
            "recording": "开始/停止录制",
        }
        for key in self.DEFAULTS:
            if key.startswith("shortcut_"):
                short_key = key[len("shortcut_"):]
                editor = QKeySequenceEdit()
                self.shortcut_edits[short_key] = editor
                shortcut_form.addRow(shortcut_descriptions.get(short_key, short_key), editor)

        shortcut_group.setLayout(shortcut_form)
        layout.addWidget(shortcut_group)

        # ---------- 清除缓存 ----------
        self.clear_cache_btn = QPushButton("清除缓存")
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        layout.addWidget(self.clear_cache_btn)

        # ---------- 恢复默认设置 ----------
        self.reset_defaults_btn = QPushButton("恢复默认设置")
        self.reset_defaults_btn.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self.reset_defaults_btn)

        # 提示信息
        info_label = QLabel("提示：修改 ADB 路径后需要重新启动程序才能生效。部分快捷键修改后需要重新打开设备窗口。")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)

        # 确定/取消按钮
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
        """加载当前设置到界面控件"""
        self.adb_path_edit.blockSignals(True)
        self.scrcpy_path_edit.blockSignals(True)
        self.lang_combo.blockSignals(True)
        self.refresh_spin.blockSignals(True)

        self.adb_path_edit.setText(self.settings.get("adb_path", self.DEFAULTS["adb_path"]))
        self.scrcpy_path_edit.setText(self.settings.get("scrcpy_path", self.DEFAULTS["scrcpy_path"]))
        lang = self.settings.get("language", self.DEFAULTS["language"])
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.refresh_spin.setValue(self.settings.get("auto_refresh_interval", self.DEFAULTS["auto_refresh_interval"]))

        # 加载快捷键
        for key, editor in self.shortcut_edits.items():
            default = self.DEFAULTS.get(f"shortcut_{key}", "")
            saved = self.settings.get(f"shortcut_{key}", default)
            editor.setKeySequence(QKeySequence(saved))

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
        """保存当前设置"""
        ConfigManager.set_setting("adb_path", self.adb_path_edit.text().strip())
        ConfigManager.set_setting("scrcpy_path", self.scrcpy_path_edit.text().strip())
        ConfigManager.set_setting("language", self.lang_combo.currentData())
        ConfigManager.set_setting("auto_refresh_interval", self.refresh_spin.value())

        for key, editor in self.shortcut_edits.items():
            value = editor.keySequence().toString()
            ConfigManager.set_setting(f"shortcut_{key}", value)

        if self._has_changes:
            QMessageBox.information(self, "设置已保存", "部分设置需要重启程序或重新打开设备窗口才能完全生效。")
        self.accept()

    def reset_to_defaults(self):
        """恢复所有设置为默认值"""
        reply = QMessageBox.question(
            self,
            "确认恢复默认设置",
            "确定要将所有设置恢复为默认值吗？\n\n"
            "这将重置 ADB 路径、scrcpy 路径、语言、刷新间隔、快捷键，\n"
            "并清空设备别名、排序、收藏、历史记录和窗口布局。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 重置 settings.json 中的各项
        for key, default_val in self.DEFAULTS.items():
            ConfigManager.set_setting(key, default_val)

        # 重置窗口几何
        ConfigManager.set_setting("window_geometry", {})

        # 清空设备别名
        ConfigManager.save_device_aliases({})

        # 清空设备排序
        ConfigManager.set_device_order([])

        # 清空收藏
        ConfigManager.save_favorites({})

        # 清空历史记录
        ConfigManager.save_history([])

        # 刷新界面显示
        self.load_settings()
        self._has_changes = False
        QMessageBox.information(self, "已恢复", "所有设置已恢复为默认值。")

    def clear_cache(self):
        """删除项目 cache 目录下的所有文件"""
        reply = QMessageBox.question(
            self,
            "确认清除缓存",
            "确定要删除所有缓存数据吗？\n这包括应用图标等缓存文件。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        cache_dir = Path(__file__).resolve().parent.parent / "cache"
        try:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            QMessageBox.information(self, "缓存已清除", "缓存数据已被删除。")
        except Exception as e:
            QMessageBox.warning(self, "清除失败", f"清除缓存时发生错误：{str(e)}")
