"""
ui/settings_dialog.py - 全局设置对话框 (Global Settings Dialog)

功能 (Features):
    - 配置 ADB 和 scrcpy 路径 (Configure ADB & scrcpy paths)
    - 语言选择 (Language selection)
    - 设备列表刷新间隔 (Device list refresh interval)
    - 自定义快捷键 (Customizable shortcuts)
    - 清除缓存 (Clear cache)
    - 恢复默认设置 (Reset to default settings)

多语言 (i18n):
    所有用户可见字符串均使用 self.tr() 包裹，可通过翻译文件切换语言。
    All user-visible strings are wrapped with self.tr() for translation.

依赖 (Dependencies): PyQt5, utils.config_manager, utils.system_utils
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
    """全局设置对话框 (Global settings dialog)"""

    # 默认配置常量 (Default configuration constants)
    DEFAULTS = {
        "adb_path": "",
        "scrcpy_path": "",
        "language": "auto",                     # 语言 (Language)
        "auto_refresh_interval": 3000,          # 毫秒 (milliseconds)
        "shortcut_close": "Ctrl+W",
        "shortcut_screenshot": "Ctrl+Shift+S",
        "shortcut_refresh_info": "F5",
        "shortcut_recording": "Ctrl+Shift+R",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("全局设置"))
        self.setMinimumWidth(550)

        # 当前已保存的设置快照，用于检测语言是否变更
        # Snapshot of currently saved settings, used to detect language change
        self.settings = ConfigManager.get_settings()
        self._old_language = self.settings.get("language", "auto")
        self._has_changes = False

        self.init_ui()
        self.load_settings()
        self.connect_signals()

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建设置对话框界面 (Create settings dialog UI)"""
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # ADB 路径 (ADB path)
        self.adb_path_edit = QLineEdit()
        self.adb_browse_btn = QPushButton(self.tr("浏览..."))
        self.adb_browse_btn.clicked.connect(lambda: self.browse_file(self.adb_path_edit))
        adb_layout = QHBoxLayout()
        adb_layout.addWidget(self.adb_path_edit)
        adb_layout.addWidget(self.adb_browse_btn)
        form.addRow(self.tr("ADB 路径:"), adb_layout)

        self.test_adb_btn = QPushButton(self.tr("检测 ADB"))
        self.test_adb_btn.clicked.connect(self.test_adb)
        form.addRow("", self.test_adb_btn)

        # scrcpy 路径 (scrcpy path)
        self.scrcpy_path_edit = QLineEdit()
        self.scrcpy_browse_btn = QPushButton(self.tr("浏览..."))
        self.scrcpy_browse_btn.clicked.connect(lambda: self.browse_file(self.scrcpy_path_edit))
        scrcpy_layout = QHBoxLayout()
        scrcpy_layout.addWidget(self.scrcpy_path_edit)
        scrcpy_layout.addWidget(self.scrcpy_browse_btn)
        form.addRow(self.tr("scrcpy 路径:"), scrcpy_layout)

        # 语言选择 (Language selection)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(self.tr("自动 (跟随系统)"), "auto")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("简体中文", "zh_CN")
        form.addRow(self.tr("语言:"), self.lang_combo)

        # 刷新间隔 (Refresh interval)
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1000, 10000)
        self.refresh_spin.setSuffix(self.tr(" 毫秒"))
        form.addRow(self.tr("设备列表刷新间隔:"), self.refresh_spin)

        layout.addLayout(form)

        # ---- 快捷键设置 (Shortcuts) ----
        shortcut_group = QGroupBox(self.tr("快捷键 (部分修改需重新打开设备窗口)"))
        shortcut_form = QFormLayout()

        self.shortcut_edits = {}
        # 快捷键描述映射 (Shortcut description mapping)
        shortcut_descriptions = {
            "close": self.tr("关闭设备窗口"),
            "screenshot": self.tr("截图"),
            "refresh_info": self.tr("刷新设备信息"),
            "recording": self.tr("开始/停止录制"),
        }
        for key in self.DEFAULTS:
            if key.startswith("shortcut_"):
                short_key = key[len("shortcut_"):]
                editor = QKeySequenceEdit()
                self.shortcut_edits[short_key] = editor
                shortcut_form.addRow(shortcut_descriptions.get(short_key, short_key), editor)

        shortcut_group.setLayout(shortcut_form)
        layout.addWidget(shortcut_group)

        # ---- 清除缓存 (Clear cache) ----
        self.clear_cache_btn = QPushButton(self.tr("清除缓存"))
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        layout.addWidget(self.clear_cache_btn)

        # ---- 恢复默认设置 (Reset to defaults) ----
        self.reset_defaults_btn = QPushButton(self.tr("恢复默认设置"))
        self.reset_defaults_btn.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self.reset_defaults_btn)

        # 提示信息 (Hint label)
        info_label = QLabel(
            self.tr("提示：修改 ADB 路径后需要重新启动程序才能生效。部分快捷键修改后需要重新打开设备窗口。")
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info_label)

        # 确定 / 取消按钮 (OK / Cancel buttons)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    # ========== 辅助操作 (Helper Actions) ==========

    def browse_file(self, line_edit):
        """
        打开文件选择对话框，将所选文件路径填入文本框。
        Open a file dialog and insert the selected path into the given line edit.
        """
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择可执行文件"))
        if path:
            line_edit.setText(path)

    def test_adb(self):
        """
        检测当前 ADB 路径是否有效并显示版本 (Test ADB and show version).
        """
        path = self.adb_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, self.tr("测试 ADB"), self.tr("请先选择 ADB 路径"))
            return
        ok, version = SystemUtils.check_adb_version(path)
        if ok:
            QMessageBox.information(
                self,
                self.tr("测试成功"),
                self.tr("ADB 版本: {version}").format(version=version)
            )
        else:
            QMessageBox.warning(
                self,
                self.tr("测试失败"),
                self.tr("无法执行 ADB:\n{error}").format(error=version)
            )

    # ========== 加载与保存 (Load & Save) ==========

    def load_settings(self):
        """
        将已保存的设置加载到界面控件。
        Load saved settings into the UI controls.
        """
        # 阻断信号，避免触发修改标记 (Block signals to avoid marking changes during load)
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

        # 加载快捷键 (Load shortcuts)
        for key, editor in self.shortcut_edits.items():
            default = self.DEFAULTS.get(f"shortcut_{key}", "")
            saved = self.settings.get(f"shortcut_{key}", default)
            editor.setKeySequence(QKeySequence(saved))

        # 恢复信号 (Restore signals)
        self.adb_path_edit.blockSignals(False)
        self.scrcpy_path_edit.blockSignals(False)
        self.lang_combo.blockSignals(False)
        self.refresh_spin.blockSignals(False)

    def connect_signals(self):
        """
        连接控件变更信号，用于标记设置已修改。
        Connect widget change signals to flag unsaved changes.
        """
        self.adb_path_edit.textChanged.connect(self._on_setting_changed)
        self.scrcpy_path_edit.textChanged.connect(self._on_setting_changed)
        self.lang_combo.currentIndexChanged.connect(self._on_setting_changed)
        self.refresh_spin.valueChanged.connect(self._on_setting_changed)

    def _on_setting_changed(self):
        """任一设置项变化时调用，标记存在未保存修改 (Mark that settings have been changed)."""
        self._has_changes = True

    def save_settings(self):
        """
        保存当前所有设置到配置文件，若语言变更则弹出重启提示。
        Save all settings to config files; if language changed, show restart prompt.
        """
        # 保存各项设置 (Save each setting)
        ConfigManager.set_setting("adb_path", self.adb_path_edit.text().strip())
        ConfigManager.set_setting("scrcpy_path", self.scrcpy_path_edit.text().strip())
        ConfigManager.set_setting("language", self.lang_combo.currentData())
        ConfigManager.set_setting("auto_refresh_interval", self.refresh_spin.value())

        for key, editor in self.shortcut_edits.items():
            value = editor.keySequence().toString()
            ConfigManager.set_setting(f"shortcut_{key}", value)

        # 检查语言是否改变 (Check if language has changed)
        new_language = self.lang_combo.currentData()
        if new_language != self._old_language:
            QMessageBox.information(
                self,
                self.tr("语言设置已更改"),
                self.tr("语言设置已更新，请重新启动程序以使新语言生效。")
            )
            self._old_language = new_language  # 更新快照，避免重复提示
        elif self._has_changes:
            QMessageBox.information(
                self,
                self.tr("设置已保存"),
                self.tr("部分设置需要重启程序或重新打开设备窗口才能完全生效。")
            )

        self.accept()

    # ========== 恢复默认设置 (Reset to Defaults) ==========

    def reset_to_defaults(self):
        """
        将所有设置恢复为程序默认值，并清空用户数据（别名、排序、收藏、历史等）。
        Reset all settings to defaults, clear user data (aliases, order, favorites, history).
        """
        reply = QMessageBox.question(
            self,
            self.tr("确认恢复默认设置"),
            self.tr(
                "确定要将所有设置恢复为默认值吗？\n\n"
                "这将重置 ADB 路径、scrcpy 路径、语言、刷新间隔、快捷键，\n"
                "并清空设备别名、排序、收藏、历史记录和窗口布局。"
            ),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 重置 settings.json 中的各项 (Reset settings.json entries)
        for key, default_val in self.DEFAULTS.items():
            ConfigManager.set_setting(key, default_val)

        # 重置窗口几何 (Reset window geometry)
        ConfigManager.set_setting("window_geometry", {})

        # 清空其他数据 (Clear other data)
        ConfigManager.save_device_aliases({})
        ConfigManager.set_device_order([])
        ConfigManager.save_favorites({})
        ConfigManager.save_history([])

        # 刷新界面显示并重置状态 (Refresh UI and reset state)
        self.load_settings()
        self._has_changes = False
        self._old_language = self.DEFAULTS["language"]
        QMessageBox.information(
            self,
            self.tr("已恢复"),
            self.tr("所有设置已恢复为默认值。")
        )

    # ========== 清除缓存 (Clear Cache) ==========

    def clear_cache(self):
        """
        删除项目 cache 目录下的所有文件。
        Delete all files under the project cache directory.
        """
        reply = QMessageBox.question(
            self,
            self.tr("确认清除缓存"),
            self.tr("确定要删除所有缓存数据吗？\n这包括应用图标等缓存文件。"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        cache_dir = Path(__file__).resolve().parent.parent / "cache"
        try:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            QMessageBox.information(self, self.tr("缓存已清除"), self.tr("缓存数据已被删除。"))
        except Exception as e:
            QMessageBox.warning(
                self,
                self.tr("清除失败"),
                self.tr("清除缓存时发生错误：{error}").format(error=str(e))
            )
