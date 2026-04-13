"""
ui/device_window.py - 设备控制窗口（调试版）
"""

import sys
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QTextEdit, QMessageBox, QProgressBar,
    QStatusBar, QToolBar, QAction, QGroupBox, QFormLayout,
    QLineEdit, QGridLayout, QFileDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QProcess
from PyQt5.QtGui import QIcon, QPixmap

from core.adb_client import AdbClient
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class DeviceWindow(QMainWindow):
    status_message = pyqtSignal(str)
    closed = pyqtSignal(str)

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.device_info = {}

        self.setWindowTitle(f"设备控制 - {serial}")
        self.setMinimumSize(900, 700)

        self.init_ui()
        self.init_toolbar()
        self.init_statusbar()
        self.status_message.connect(self.show_status_message)
        self.load_device_info()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.info_tab = self.create_info_tab()
        self.tab_widget.addTab(self.info_tab, "设备信息")

        self.apps_tab = self.create_apps_tab()
        self.tab_widget.addTab(self.apps_tab, "应用管理")

        self.file_tab = self.create_file_manager_tab()
        self.tab_widget.addTab(self.file_tab, "文件管理")

        self.log_tab = self.create_placeholder_tab("日志查看\n(待实现)")
        self.tab_widget.addTab(self.log_tab, "日志")

        self.advanced_tab = self.create_placeholder_tab("高级功能\n(待实现)")
        self.tab_widget.addTab(self.advanced_tab, "高级")

    def init_toolbar(self):
        toolbar = self.addToolBar("设备操作")
        toolbar.setMovable(False)

        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

        toolbar.addSeparator()

        reboot_action = QAction("重启", self)
        reboot_action.triggered.connect(lambda: self.reboot_device(""))
        toolbar.addAction(reboot_action)

        recovery_action = QAction("重启到 Recovery", self)
        recovery_action.triggered.connect(lambda: self.reboot_device("recovery"))
        toolbar.addAction(recovery_action)

        bootloader_action = QAction("重启到 Bootloader", self)
        bootloader_action.triggered.connect(lambda: self.reboot_device("bootloader"))
        toolbar.addAction(bootloader_action)

        toolbar.addSeparator()

        shutdown_action = QAction("关机", self)
        shutdown_action.triggered.connect(self.shutdown_device)
        toolbar.addAction(shutdown_action)

        toolbar.addSeparator()

        refresh_action = QAction("刷新信息", self)
        refresh_action.triggered.connect(self.load_device_info)
        toolbar.addAction(refresh_action)

    def init_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def show_status_message(self, msg: str):
        self.status_label.setText(msg)

    def create_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_group = QGroupBox("基本信息")
        form_layout = QFormLayout()
        self.model_label = QLabel("未知")
        self.android_version_label = QLabel("未知")
        self.battery_label = QLabel("未知")
        self.resolution_label = QLabel("未知")
        self.serial_label = QLabel(self.serial)

        form_layout.addRow("设备型号:", self.model_label)
        form_layout.addRow("Android 版本:", self.android_version_label)
        form_layout.addRow("电池状态:", self.battery_label)
        form_layout.addRow("屏幕分辨率:", self.resolution_label)
        form_layout.addRow("序列号:", self.serial_label)
        info_group.setLayout(form_layout)
        layout.addWidget(info_group)

        detail_group = QGroupBox("详细信息")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        return widget

    def create_placeholder_tab(self, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: gray;")
        layout.addWidget(label)
        return widget

    def create_apps_tab(self) -> QWidget:
        from ui.apps_tab import AppsTab
        return AppsTab(self.serial, self.adb_client)

    def create_file_manager_tab(self) -> QWidget:
        from ui.file_manager import FileManager
        return FileManager(self.serial, self.adb_client, parent=self)

    def load_device_info(self):
        self.status_label.setText("正在获取设备信息...")
        print(f"[DeviceWindow] Loading device info for {self.serial}")
        
        model = self.adb_client.shell_sync("getprop ro.product.model", self.serial)
        self._on_model_loaded(model.strip())
        
        version = self.adb_client.shell_sync("getprop ro.build.version.release", self.serial)
        self._on_android_version_loaded(version.strip())
        
        battery_out = self.adb_client.shell_sync("dumpsys battery", self.serial)
        self._on_battery_loaded(battery_out)
        
        resolution_out = self.adb_client.shell_sync("wm size", self.serial)
        self._on_resolution_loaded(resolution_out)
        
        props_out = self.adb_client.shell_sync("getprop", self.serial)
        self._on_props_loaded(props_out)
        
        self.status_label.setText("设备信息已更新")

    def _on_model_loaded(self, model: str):
        print(f"_on_model_loaded: '{model}'")
        self.model_label.setText(model if model else "未知")

    def _on_android_version_loaded(self, version: str):
        print(f"_on_android_version_loaded: '{version}'")
        self.android_version_label.setText(version if version else "未知")

    def _on_battery_loaded(self, output: str):
        print(f"_on_battery_loaded: output length {len(output)}")
        # 打印前几行用于调试
        lines = output.splitlines()
        for i, line in enumerate(lines[:5]):
            print(f"  battery line {i}: {line}")
        level = "未知"
        status = "未知"
        for line in output.splitlines():
            if "level:" in line:
                level = line.split(":")[1].strip()
            if "status:" in line:
                status_code = line.split(":")[1].strip()
                status_map = {"1": "未知", "2": "充电中", "3": "放电中", "4": "未充电", "5": "已满"}
                status = status_map.get(status_code, status_code)
        self.battery_label.setText(f"{level}% ({status})")

    def _on_resolution_loaded(self, output: str):
        print(f"_on_resolution_loaded: '{output}'")
        if "Physical size:" in output:
            res = output.split(":")[1].strip()
            self.resolution_label.setText(res)
        else:
            self.resolution_label.setText("未知")

    def _on_props_loaded(self, output: str):
        print(f"_on_props_loaded: output length {len(output)}")
        self.detail_text.setText(output)
        self.status_label.setText("设备信息已更新")

    def take_screenshot(self):
        default_name = f"screenshot_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存截图", default_name, "PNG图片 (*.png)")
        if not file_path:
            return
        self.status_label.setText("正在截图...")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(lambda code: self._on_screenshot_finished(code, proc, file_path))
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "exec-out", "screencap", "-p"])

    def _on_screenshot_finished(self, exit_code, proc, file_path):
        if exit_code == 0:
            data = proc.readAllStandardOutput()
            try:
                with open(file_path, "wb") as f:
                    f.write(data.data())
                self.status_label.setText(f"截图已保存: {file_path}")
                QMessageBox.information(self, "截图成功", f"截图已保存到:\n{file_path}")
            except Exception as e:
                self.status_label.setText("保存截图失败")
                QMessageBox.warning(self, "错误", f"保存截图失败: {str(e)}")
        else:
            self.status_label.setText("截图失败")
            QMessageBox.warning(self, "错误", "截图失败，请确保设备已解锁且支持 screencap 命令。")

    def reboot_device(self, mode: str = ""):
        mode_text = {"": "重启", "recovery": "重启到 Recovery", "bootloader": "重启到 Bootloader"}.get(mode, "重启")
        reply = QMessageBox.question(self, "确认操作", f"确定要{mode_text}设备 {self.serial} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText(f"正在{mode_text}...")
            self.adb_client.reboot(self.serial, mode,
                                   callback=lambda code, out, err: self._on_reboot_finished(code, mode_text))

    def _on_reboot_finished(self, exit_code, mode_text):
        if exit_code == 0:
            self.status_label.setText(f"{mode_text}命令已发送")
            QMessageBox.information(self, "操作成功", f"{mode_text}命令已发送，设备将开始重启。")
        else:
            self.status_label.setText(f"{mode_text}失败")
            QMessageBox.warning(self, "错误", f"{mode_text}失败，请检查设备连接。")

    def shutdown_device(self):
        reply = QMessageBox.question(self, "确认操作", f"确定要关闭设备 {self.serial} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText("正在关机...")
            self.adb_client.shell("reboot -p", self.serial,
                                  callback=lambda code, out, err: self._on_shutdown_finished(code))

    def _on_shutdown_finished(self, exit_code):
        if exit_code == 0:
            self.status_label.setText("关机命令已发送")
            QMessageBox.information(self, "操作成功", "关机命令已发送，设备将关闭。")
        else:
            self.status_label.setText("关机失败")
            QMessageBox.warning(self, "错误", "关机失败，请检查设备权限。")

    def closeEvent(self, event):
        self.closed.emit(self.serial)
        event.accept()
