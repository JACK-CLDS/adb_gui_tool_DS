"""
ui/device_window.py - 设备控制窗口

功能：
    - 为每个设备提供一个独立的控制窗口
    - 显示设备基本信息（型号、Android版本、电池状态等）
    - 提供常用操作按钮（截图、重启、重启到recovery、关机等）
    - 预留选项卡：应用管理、文件管理、日志查看、高级功能
    - 与 DeviceManager 集成，支持 ADB 服务重启时关闭窗口

依赖：PyQt5, core.adb_client, utils.config_manager
"""

import sys
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QTextEdit, QMessageBox, QProgressBar,
    QStatusBar, QToolBar, QAction, QGroupBox, QFormLayout,
    QLineEdit, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QProcess
from PyQt5.QtGui import QIcon, QPixmap

from core.adb_client import AdbClient
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class DeviceWindow(QMainWindow):
    """单个设备的控制窗口"""

    # 窗口关闭时发出信号，供 DeviceManager 清理引用
    closed = pyqtSignal(str)

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.device_info = {}  # 存储设备详细信息

        self.setWindowTitle(f"设备控制 - {serial}")
        self.setMinimumSize(900, 700)

        self.init_ui()
        self.init_toolbar()
        self.init_statusbar()
        self.load_device_info()  # 异步加载设备信息

    def init_ui(self):
        """初始化中央部件和选项卡"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 创建选项卡
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 设备信息选项卡
        self.info_tab = self.create_info_tab()
        self.tab_widget.addTab(self.info_tab, "设备信息")

        # 应用管理选项卡（占位）
        self.apps_tab = self.create_apps_tab()
        self.tab_widget.addTab(self.apps_tab, "应用管理")

        # 文件管理选项卡（占位）
        self.file_tab = self.create_placeholder_tab("文件管理\n(待实现)")
        self.tab_widget.addTab(self.file_tab, "文件管理")

        # 日志查看选项卡（占位）
        self.log_tab = self.create_placeholder_tab("日志查看\n(待实现)")
        self.tab_widget.addTab(self.log_tab, "日志")

        # 高级功能选项卡（占位）
        self.advanced_tab = self.create_placeholder_tab("高级功能\n(待实现)")
        self.tab_widget.addTab(self.advanced_tab, "高级")

    def init_toolbar(self):
        """创建顶部工具栏"""
        toolbar = self.addToolBar("设备操作")
        toolbar.setMovable(False)

        # 截图按钮
        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

        toolbar.addSeparator()

        # 重启按钮
        reboot_action = QAction("重启", self)
        reboot_action.triggered.connect(lambda: self.reboot_device(""))
        toolbar.addAction(reboot_action)

        # 重启到 Recovery
        recovery_action = QAction("重启到 Recovery", self)
        recovery_action.triggered.connect(lambda: self.reboot_device("recovery"))
        toolbar.addAction(recovery_action)

        # 重启到 Bootloader
        bootloader_action = QAction("重启到 Bootloader", self)
        bootloader_action.triggered.connect(lambda: self.reboot_device("bootloader"))
        toolbar.addAction(bootloader_action)

        toolbar.addSeparator()

        # 关机
        shutdown_action = QAction("关机", self)
        shutdown_action.triggered.connect(self.shutdown_device)
        toolbar.addAction(shutdown_action)

        toolbar.addSeparator()

        # 刷新设备信息
        refresh_action = QAction("刷新信息", self)
        refresh_action.triggered.connect(self.load_device_info)
        toolbar.addAction(refresh_action)

    def init_statusbar(self):
        """初始化状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def create_info_tab(self) -> QWidget:
        """创建设备信息选项卡（显示基本信息和详细信息）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 基本信息区域（网格布局）
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

        # 详细信息文本框（用于显示 getprop 等长文本）
        detail_group = QGroupBox("详细信息")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        return widget

    def create_placeholder_tab(self, text: str) -> QWidget:
        """创建一个占位选项卡，显示“待实现”文字"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: gray;")
        layout.addWidget(label)
        return widget

    def load_device_info(self):
        """异步加载设备信息（型号、Android版本、电池等）"""
        self.status_label.setText("正在获取设备信息...")
        # 获取设备型号
        self.adb_client.shell("getprop ro.product.model", self.serial,
                              callback=lambda code, out, err: self._on_model_loaded(out.strip()))
        # 获取 Android 版本
        self.adb_client.shell("getprop ro.build.version.release", self.serial,
                              callback=lambda code, out, err: self._on_android_version_loaded(out.strip()))
        # 获取电池信息
        self.adb_client.shell("dumpsys battery", self.serial,
                              callback=lambda code, out, err: self._on_battery_loaded(out))
        # 获取屏幕分辨率
        self.adb_client.shell("wm size", self.serial,
                              callback=lambda code, out, err: self._on_resolution_loaded(out))
        # 获取所有属性（详细信息）
        self.adb_client.shell("getprop", self.serial,
                              callback=lambda code, out, err: self._on_props_loaded(out))

    def _on_model_loaded(self, model: str):
        self.model_label.setText(model if model else "未知")

    def _on_android_version_loaded(self, version: str):
        self.android_version_label.setText(version if version else "未知")

    def _on_battery_loaded(self, output: str):
        # 解析 dumpsys battery 输出，提取 level 和 status
        level = "未知"
        status = "未知"
        for line in output.splitlines():
            if "level:" in line:
                level = line.split(":")[1].strip()
            if "status:" in line:
                status_code = line.split(":")[1].strip()
                # 状态码映射：1=未知, 2=充电中, 3=放电中, 4=未充电, 5=已满
                status_map = {"1": "未知", "2": "充电中", "3": "放电中", "4": "未充电", "5": "已满"}
                status = status_map.get(status_code, status_code)
        self.battery_label.setText(f"{level}% ({status})")

    def _on_resolution_loaded(self, output: str):
        # 输出格式: Physical size: 1080x1920
        if "Physical size:" in output:
            res = output.split(":")[1].strip()
            self.resolution_label.setText(res)
        else:
            self.resolution_label.setText("未知")

    def _on_props_loaded(self, output: str):
        self.detail_text.setText(output)
        self.status_label.setText("设备信息已更新")

    def take_screenshot(self):
        """截图并保存到本地（弹出保存对话框）"""
        from PyQt5.QtWidgets import QFileDialog
        default_name = f"screenshot_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存截图", default_name, "PNG图片 (*.png)")
        if not file_path:
            return
        self.status_label.setText("正在截图...")
        # 使用 exec-out screencap -p 获取原始 PNG 数据
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
        """重启设备，mode: ""(普通重启), "recovery", "bootloader" """
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
        """关机"""
        reply = QMessageBox.question(self, "确认操作", f"确定要关闭设备 {self.serial} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText("正在关机...")
            # 使用 adb shell reboot -p 关机
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
        """窗口关闭时发出信号，并执行清理"""
        self.closed.emit(self.serial)
        event.accept()


# 注意：AdbClient 需要增加 shell 和 reboot 方法，我们将在后续补全 adb_client.py
    # 在 DeviceWindow 类中添加方法
    def create_apps_tab(self) -> QWidget:
        """创建应用管理选项卡"""
        from ui.apps_tab import AppsTab
        return AppsTab(self.serial, self.adb_client)
