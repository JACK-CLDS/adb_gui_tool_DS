"""
ui/device_window.py - 设备控制窗口 (Device Control Window)

为单个 Android 设备提供完整的控制界面，包含设备信息、应用管理、文件管理、
日志查看、进程管理、终端、代理设置等选项卡，以及截图、录制、重启等工具栏操作。
Provides a full control panel for a single Android device, including tabs for device info,
app management, file manager, logcat, process manager, terminal, proxy settings,
and toolbar actions for screenshot, recording, reboot, etc.

多语言 (i18n):
    所有用户可见字符串均已使用 self.tr() 包裹，可通过翻译文件切换语言。
    All user-visible strings are wrapped with self.tr() for translation.
"""

import sys
import subprocess
import time
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QTextEdit, QMessageBox, QProgressBar,
    QStatusBar, QToolBar, QAction, QGroupBox, QFormLayout,
    QLineEdit, QGridLayout, QFileDialog, QFrame, QSizePolicy,
    QShortcut
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QProcess
from PyQt5.QtGui import (
    QIcon, QPixmap, QFont, QKeySequence, QTextOption, QFontDatabase
)

from core.adb_client import AdbClient
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class DeviceWindow(QMainWindow):
    """设备控制窗口 (Device control window)"""

    status_message = pyqtSignal(str)   # 状态栏消息信号 (Status bar message signal)
    closed = pyqtSignal(str)           # 窗口关闭信号，携带设备序列号 (Emitted on close, with serial)

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.device_info = {}

        # 窗口标题 (Window title)
        self.setWindowTitle(self.tr("设备控制 - {serial}").format(serial=serial))
        self.setMinimumSize(900, 700)

        self.init_ui()
        self.init_toolbar()
        self.init_statusbar()
        self.load_device_info_async()
        self.status_message.connect(self.show_status_message)

        # 录制相关变量 (Recording state variables)
        self.recording_process = None
        self.recording_file = None
        self.recording_pid = None

        self.setup_shortcuts()

    # ========== 界面初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建主界面布局 (Create main UI layout)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget, 1)

        # 设备信息选项卡 (Device info tab)
        self.info_tab = self.create_info_tab()
        self.tab_widget.addTab(self.info_tab, self.tr("设备信息"))

        # 应用管理选项卡 (App management tab)
        self.apps_tab = self.create_apps_tab()
        self.tab_widget.addTab(self.apps_tab, self.tr("应用管理"))

        # 文件管理选项卡 (File manager tab)
        self.file_tab = self.create_file_manager_tab()
        self.tab_widget.addTab(self.file_tab, self.tr("文件管理"))

        # 日志选项卡 (Logcat tab)
        self.log_tab = self.create_log_tab()
        self.tab_widget.addTab(self.log_tab, self.tr("日志"))

        # 进程管理选项卡 (Process manager tab)
        self.advanced_tab = self.create_process_manager_tab()
        self.tab_widget.addTab(self.advanced_tab, self.tr("进程管理"))

        # 终端选项卡 (Terminal tab)
        self.terminal_tab = self.create_terminal_tab()
        self.tab_widget.addTab(self.terminal_tab, self.tr("终端"))

        # 代理设置选项卡 (Proxy settings tab)
        self.proxy_tab = self.create_proxy_tab()
        self.tab_widget.addTab(self.proxy_tab, self.tr("代理设置"))

    def init_toolbar(self):
        """创建设备操作工具栏 (Create device operation toolbar)"""
        toolbar = self.addToolBar(self.tr("设备操作"))
        toolbar.setMovable(False)

        # 截图 (Screenshot)
        screenshot_action = QAction(self.tr("截图"), self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

        # 飞行模式 (Airplane mode)
        self.airplane_action = QAction(self.tr("飞行模式"), self, checkable=True)
        self.airplane_action.triggered.connect(self.toggle_airplane_mode)
        toolbar.addAction(self.airplane_action)

        # 旋转屏幕 (Rotate screen)
        self.rotate_action = QAction(self.tr("旋转屏幕"), self)
        self.rotate_action.triggered.connect(self.rotate_screen)
        toolbar.addAction(self.rotate_action)

        # 录制 (Record)
        self.record_action = QAction(self.tr("开始录制"), self)
        self.record_action.triggered.connect(self.start_recording)
        toolbar.addAction(self.record_action)

        toolbar.addSeparator()

        # 重启选项 (Reboot options)
        reboot_action = QAction(self.tr("重启"), self)
        reboot_action.triggered.connect(lambda: self.reboot_device(""))
        toolbar.addAction(reboot_action)

        recovery_action = QAction(self.tr("重启到 Recovery"), self)
        recovery_action.triggered.connect(lambda: self.reboot_device("recovery"))
        toolbar.addAction(recovery_action)

        bootloader_action = QAction(self.tr("重启到 Bootloader"), self)
        bootloader_action.triggered.connect(lambda: self.reboot_device("bootloader"))
        toolbar.addAction(bootloader_action)

        toolbar.addSeparator()

        # 关机 (Shutdown)
        shutdown_action = QAction(self.tr("关机"), self)
        shutdown_action.triggered.connect(self.shutdown_device)
        toolbar.addAction(shutdown_action)

        toolbar.addSeparator()

        # Root 权限管理 (Root management)
        root_action = QAction(self.tr("提权 (root)"), self)
        root_action.triggered.connect(self.enable_root)
        toolbar.addAction(root_action)
        unroot_action = QAction(self.tr("解提权 (unroot)"), self)
        unroot_action.triggered.connect(self.disable_root)
        toolbar.addAction(unroot_action)

        self.remount_action = QAction(self.tr("重新挂载 system"), self)
        self.remount_action.triggered.connect(self.remount_system)
        toolbar.addAction(self.remount_action)

        self.mounts_action = QAction(self.tr("查看分区挂载"), self)
        self.mounts_action.triggered.connect(self.show_mounts)
        toolbar.addAction(self.mounts_action)

        toolbar.addSeparator()

        # 刷新信息 (Refresh info)
        refresh_action = QAction(self.tr("刷新信息"), self)
        refresh_action.triggered.connect(self.load_device_info_async)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        # Monkey 测试 (Monkey test)
        monkey_action = QAction(self.tr("Monkey测试"), self)
        monkey_action.triggered.connect(self.open_monkey_dialog)
        toolbar.addAction(monkey_action)

        toolbar.addSeparator()

        # tcpdump 抓包 (Packet capture)
        tcpdump_action = QAction(self.tr("tcpdump抓包"), self)
        tcpdump_action.triggered.connect(self.open_tcpdump_dialog)
        toolbar.addAction(tcpdump_action)

        toolbar.addSeparator()

        # 软键盘 (Soft keyboard)
        keyboard_action = QAction(self.tr("软键盘"), self)
        keyboard_action.triggered.connect(self.open_soft_keyboard)
        toolbar.addAction(keyboard_action)

        toolbar.addSeparator()

        # 发送广播 (Send broadcast)
        broadcast_action = QAction(self.tr("发送广播"), self)
        broadcast_action.triggered.connect(self.open_broadcast_dialog)
        toolbar.addAction(broadcast_action)

        toolbar.addSeparator()

        # 沉浸模式 (Immersive mode)
        self.immersive_status_action = QAction(self.tr("沉浸状态栏"), self, checkable=True)
        self.immersive_status_action.triggered.connect(self.toggle_immersive_status_bar)
        toolbar.addAction(self.immersive_status_action)

        self.immersive_nav_action = QAction(self.tr("沉浸导航栏"), self, checkable=True)
        self.immersive_nav_action.triggered.connect(self.toggle_immersive_navigation)
        toolbar.addAction(self.immersive_nav_action)

    def init_statusbar(self):
        """初始化状态栏 (Initialize status bar)"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel(self.tr("就绪"))
        self.status_bar.addWidget(self.status_label)

    # ========== 快捷键设置 (Shortcuts) ==========

    def setup_shortcuts(self):
        """读取配置中的快捷键并绑定 (Setup keyboard shortcuts from config)"""
        defaults = {
            "close": "Ctrl+W",
            "screenshot": "Ctrl+Shift+S",
            "refresh_info": "F5",
            "recording": "Ctrl+Shift+R",
        }
        # 清除已有的快捷键 (Clear existing shortcuts)
        if hasattr(self, '_shortcuts_list'):
            for sc in self._shortcuts_list:
                sc.setEnabled(False)
                sc.deleteLater()
        self._shortcuts_list = []

        close_key = ConfigManager.get_setting("shortcut_close", defaults["close"])
        screenshot_key = ConfigManager.get_setting("shortcut_screenshot", defaults["screenshot"])
        refresh_key = ConfigManager.get_setting("shortcut_refresh_info", defaults["refresh_info"])
        recording_key = ConfigManager.get_setting("shortcut_recording", defaults["recording"])

        sc1 = QShortcut(QKeySequence(close_key), self, self.close)
        sc2 = QShortcut(QKeySequence(screenshot_key), self, self.take_screenshot)
        sc3 = QShortcut(QKeySequence(refresh_key), self, self.load_device_info_async)
        sc4 = QShortcut(QKeySequence(recording_key), self, self._toggle_recording)

        self._shortcuts_list = [sc1, sc2, sc3, sc4]

    def _toggle_recording(self):
        """根据当前状态切换录制 (Toggle recording start/stop)"""
        if hasattr(self, 'recording_proc') and self.recording_proc is not None:
            self.stop_recording()
        else:
            self.start_recording()

    # ========== 选项卡片段 (Tab Widgets) ==========

    def create_info_tab(self) -> QWidget:
        """创建设备信息选项卡 (Create device info tab)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        def make_label(text="", align_left=False):
            """创建可选择的标签，默认显示“未知” (Create selectable label, default to 'Unknown')"""
            if not text:
                text = self.tr("未知")
            label = QLabel(text)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            if align_left:
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return label

        # ---- 基本信息 (Basic info) ----
        info_group = QGroupBox(self.tr("基本信息"))
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.model_label = make_label()
        self.android_version_label = make_label()
        self.battery_label = make_label()
        self.resolution_label = make_label()
        self.serial_label = make_label(self.serial)

        form_layout.addRow(self.tr("设备型号:"), self.model_label)
        form_layout.addRow(self.tr("Android 版本:"), self.android_version_label)
        form_layout.addRow(self.tr("电池状态:"), self.battery_label)
        form_layout.addRow(self.tr("屏幕分辨率:"), self.resolution_label)
        form_layout.addRow(self.tr("序列号:"), self.serial_label)
        info_group.setLayout(form_layout)
        layout.addWidget(info_group, 0)

        # ---- 硬件与系统信息 (Hardware & system info) ----
        hardware_group = QGroupBox(self.tr("硬件与系统信息"))
        hw_layout = QFormLayout()
        hw_layout.setLabelAlignment(Qt.AlignLeft)
        hw_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        hw_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        hw_layout.setContentsMargins(15, 10, 10, 10)

        self.imei_label = make_label(align_left=True)
        self.mac_label = make_label(align_left=True)
        self.bluetooth_label = make_label(align_left=True)
        self.network_label = make_label(align_left=True)
        self.uptime_label = make_label(align_left=True)
        self.cpu_label = make_label(align_left=True)

        # 内存信息 - 无边框文本框，防止文本截断 (Memory info - borderless text edit to avoid truncation)
        self.memory_label = QTextEdit()
        self.memory_label.setReadOnly(True)
        self.memory_label.setStyleSheet("background: transparent; border: none;")
        self.memory_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.memory_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.memory_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.memory_label.setFixedHeight(24)
        self.memory_label.document().setDocumentMargin(0)
        self.memory_label.setWordWrapMode(QTextOption.WrapAnywhere)

        # 存储信息 - 无边框文本框 (Storage info)
        self.storage_label = QTextEdit()
        self.storage_label.setReadOnly(True)
        self.storage_label.setStyleSheet("background: transparent; border: none;")
        self.storage_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.storage_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.storage_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.storage_label.setFixedHeight(24)
        self.storage_label.document().setDocumentMargin(0)
        self.storage_label.setWordWrapMode(QTextOption.WrapAnywhere)

        # 显示屏详情 (Display detail)
        self.display_detail_label = QTextEdit()
        self.display_detail_label.setReadOnly(True)
        self.display_detail_label.setStyleSheet("background: transparent; border: none;")
        self.display_detail_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.display_detail_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.display_detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.display_detail_label.setMinimumWidth(0)
        self.display_detail_label.document().setDocumentMargin(0)
        self.display_detail_label.setWordWrapMode(QTextOption.WrapAnywhere)
        self.display_detail_label.setLineWrapMode(QTextEdit.WidgetWidth)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.display_detail_label.setFont(fixed_font)

        hw_layout.addRow(self.tr("IMEI:"), self.imei_label)
        hw_layout.addRow(self.tr("MAC 地址:"), self.mac_label)
        hw_layout.addRow(self.tr("蓝牙地址:"), self.bluetooth_label)
        hw_layout.addRow(self.tr("网络状态:"), self.network_label)
        hw_layout.addRow(self.tr("开机时间:"), self.uptime_label)
        hw_layout.addRow(self.tr("CPU 信息:"), self.cpu_label)
        hw_layout.addRow(self.tr("内存信息:"), self.memory_label)
        hw_layout.addRow(self.tr("存储信息:"), self.storage_label)
        hw_layout.addRow(self.tr("显示屏详情:"), self.display_detail_label)

        hardware_group.setLayout(hw_layout)
        hardware_group.setMaximumHeight(400)   # 阻止硬件组垂直拉伸 (Prevent vertical stretch)
        layout.addWidget(hardware_group, 0)

        # ---- 详细属性 (Detailed properties) ----
        detail_group = QGroupBox(self.tr("详细属性 (getprop)"))
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group, 1)      # 占据所有剩余空间 (Take remaining space)

        return widget

    def create_apps_tab(self) -> QWidget:
        """创建应用管理选项卡 (Create app management tab)"""
        from ui.apps_tab import AppsTab
        return AppsTab(self.serial, self.adb_client)

    def create_file_manager_tab(self) -> QWidget:
        """创建文件管理选项卡 (Create file manager tab)"""
        from ui.file_manager import FileManager
        return FileManager(self.serial, self.adb_client, parent=self)

    def create_log_tab(self) -> QWidget:
        """创建日志选项卡 (Create logcat tab)"""
        from ui.logcat_tab import LogcatTab
        return LogcatTab(self.serial, self.adb_client)

    def create_process_manager_tab(self) -> QWidget:
        """创建进程管理选项卡 (Create process manager tab)"""
        from ui.process_manager import ProcessManager
        pm = ProcessManager(self.serial, self.adb_client)
        pm.status_message.connect(self.show_status_message)
        return pm

    def create_terminal_tab(self) -> QWidget:
        """创建终端选项卡 (Create terminal tab)"""
        from ui.terminal import TerminalWidget
        terminal = TerminalWidget(self.serial, self.adb_client)
        terminal.status_message.connect(self.show_status_message)
        return terminal

    def create_proxy_tab(self) -> QWidget:
        """创建代理设置选项卡 (Create proxy settings tab)"""
        from ui.proxy_tab import ProxyTab
        return ProxyTab(self.serial, self.adb_client)

    # ========== 设备信息异步加载 (Async Device Info Loading) ==========

    def load_device_info_async(self):
        """异步加载设备信息，逐步更新 UI 避免卡顿 (Load device info asynchronously)"""
        self.status_label.setText(self.tr("正在获取设备信息..."))
        if hasattr(self, '_loading') and self._loading:
            return
        self._loading = True

        # 定义一系列加载任务 (Define a series of loading tasks)
        tasks = [
            (self.tr("设备型号"), lambda: self.adb_client.shell_sync("getprop ro.product.model", self.serial, timeout=2),
             lambda val: self.model_label.setText(val.strip() or self.tr("未知"))),
            (self.tr("Android版本"), lambda: self.adb_client.shell_sync("getprop ro.build.version.release", self.serial, timeout=2),
             lambda val: self.android_version_label.setText(val.strip() or self.tr("未知"))),
            (self.tr("电池信息"), lambda: self.adb_client.shell_sync("dumpsys battery", self.serial, timeout=5),
             lambda out: self._parse_battery(out)),
            (self.tr("屏幕分辨率"), lambda: self.adb_client.shell_sync("wm size", self.serial, timeout=2),
             lambda out: self._parse_resolution(out)),
            (self.tr("IMEI"), lambda: self._get_imei(), lambda val: self.imei_label.setText(val)),
            (self.tr("MAC地址"), lambda: self._get_mac_address(), lambda val: self.mac_label.setText(val)),
            (self.tr("蓝牙地址"), lambda: self._get_bluetooth_address(), lambda val: self.bluetooth_label.setText(val)),
            (self.tr("网络状态"), lambda: self._get_network_status(), lambda val: self.network_label.setText(val)),
            (self.tr("开机时间"), lambda: self._get_uptime(), lambda val: self.uptime_label.setText(val)),
            (self.tr("CPU信息"), lambda: self._get_cpu_info(), lambda val: self.cpu_label.setText(val)),
            (self.tr("内存信息"), lambda: self._get_memory_info(), lambda val: self.memory_label.setPlainText(val)),
            (self.tr("存储信息"), lambda: self._get_storage_info(), lambda val: self.storage_label.setPlainText(val)),
            (self.tr("显示屏详情"), lambda: self._get_display_detail(), lambda val: self.display_detail_label.setText(val)),
            (self.tr("详细属性"), lambda: self.adb_client.shell_sync("getprop", self.serial, timeout=8),
             lambda out: self.detail_text.setText(out)),
        ]

        self._task_index = 0
        self._tasks = tasks
        self._run_next_task()

    def _run_next_task(self):
        """执行下一个任务，使用 QTimer 避免阻塞 (Execute next task with QTimer to prevent blocking)"""
        if self._task_index >= len(self._tasks):
            self.status_label.setText(self.tr("设备信息已更新"))
            self._loading = False
            return
        desc, func, update_ui = self._tasks[self._task_index]
        self.status_label.setText(self.tr("正在获取 {description}...").format(description=desc))
        try:
            result = func()
            update_ui(result)
        except Exception as e:
            print(f"获取 {desc} 失败: {e}")
            update_ui(self.tr("获取失败"))
        self._task_index += 1
        QTimer.singleShot(10, self._run_next_task)

    # ========== 信息解析函数 (Info Parsing Functions) ==========

    def _parse_battery(self, output: str):
        """解析电池信息 (Parse battery info)"""
        level = self.tr("未知")
        status = self.tr("未知")
        # 电池状态码映射 (Battery status code mapping)
        status_map = {
            "1": self.tr("未知"),
            "2": self.tr("充电中"),
            "3": self.tr("放电中"),
            "4": self.tr("未充电"),
            "5": self.tr("已满")
        }
        for line in output.splitlines():
            if "level:" in line:
                level = line.split(":")[1].strip()
            if "status:" in line:
                status_code = line.split(":")[1].strip()
                status = status_map.get(status_code, status_code)
        self.battery_label.setText(self.tr("{level}% ({status})").format(level=level, status=status))

    def _parse_resolution(self, output: str):
        """解析屏幕分辨率 (Parse screen resolution)"""
        if "Physical size:" in output:
            self.resolution_label.setText(output.split(":")[1].strip())
        else:
            self.resolution_label.setText(self.tr("未知"))

    def _get_imei(self) -> str:
        """获取设备 IMEI (Retrieve device IMEI)"""
        import re
        out = self.adb_client.shell_sync("dumpsys iphonesubinfo", self.serial, timeout=5)
        if out:
            for line in out.splitlines():
                if "Device ID" in line or "IMEI" in line:
                    parts = line.split("=")
                    if len(parts) > 1:
                        return parts[1].strip()
        out2 = self.adb_client.shell_sync("service call iphonesubinfo 1", self.serial, timeout=5)
        if out2 and "Result" in out2:
            nums = re.findall(r"'([0-9A-F\s]+)'", out2)
            if nums:
                clean = nums[0].replace(" ", "").strip().lower()
                if clean and clean != "0":
                    try:
                        return bytes.fromhex(clean).decode("ascii", errors="ignore")
                    except:
                        pass
        out3 = self.adb_client.shell_sync("cat /proc/imei 2>/dev/null", self.serial, timeout=2)
        if out3 and "error" not in out3.lower():
            return out3.strip()
        out4 = self.adb_client.shell_sync("su -c 'cat /proc/imei' 2>/dev/null", self.serial, timeout=2)
        if out4 and "error" not in out4.lower() and out4.strip():
            return out4.strip()
        return self.tr("需权限/不可用")

    def _get_mac_address(self) -> str:
        """获取 MAC 地址 (Retrieve MAC address)"""
        import re
        out = self.adb_client.shell_sync(
            "for iface in /sys/class/net/*/address; do [ -f $iface ] && addr=$(cat $iface) && [ -n $addr ] && [ $addr != '00:00:00:00:00:00' ] && iface_name=$(dirname $iface | xargs basename) && [ $iface_name != 'lo' ] && echo $iface_name $addr; done",
            self.serial, timeout=3)
        if out.strip():
            lines = out.strip().splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    name, addr = parts[0], parts[1]
                    if ":" in addr and name not in ("lo",):
                        return addr
        out2 = self.adb_client.shell_sync("ip link show", self.serial, timeout=3)
        if out2:
            for m in re.finditer(r"link/ether\s+([0-9a-fA-F:]{17})", out2):
                return m.group(1)
        return self.tr("未知")

    def _get_bluetooth_address(self) -> str:
        """获取蓝牙地址 (Retrieve Bluetooth address)"""
        import re
        out = self.adb_client.shell_sync("settings get secure bluetooth_address", self.serial, timeout=3)
        if out.strip() and ":" in out.strip():
            return out.strip()
        out2 = self.adb_client.shell_sync("dumpsys bluetooth_manager | grep 'Address'", self.serial, timeout=3)
        if out2:
            m = re.search(r"([0-9A-Fa-f:]{17})", out2)
            if m:
                return m.group(1)
        out3 = self.adb_client.shell_sync("cat /data/misc/bluetooth/bt_config.conf 2>/dev/null | grep 'Address'", self.serial, timeout=2)
        if out3:
            m = re.search(r"([0-9A-Fa-f:]{17})", out3)
            if m:
                return m.group(1)
        return self.tr("未知")

    def _get_network_status(self) -> str:
        """获取网络连接状态 (Retrieve network status)"""
        out = self.adb_client.shell_sync("dumpsys connectivity | grep -A 5 'NetworkAgentInfo'", self.serial)
        if "WIFI" in out and "CONNECTED" in out:
            return self.tr("WiFi 已连接")
        elif "CELLULAR" in out and "CONNECTED" in out:
            return self.tr("移动网络已连接")
        else:
            return self.tr("无网络连接")

    def _get_uptime(self) -> str:
        """获取设备开机时间 (Retrieve device uptime)"""
        import re
        out = self.adb_client.shell_sync("cat /proc/uptime", self.serial, timeout=2)
        if out.strip():
            seconds = float(out.split()[0])
            days, rem = divmod(seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            if days >= 1:
                return self.tr("{days}天 {hours}小时 {minutes}分").format(
                    days=int(days), hours=int(hours), minutes=int(minutes))
            else:
                return self.tr("{hours}小时 {minutes}分").format(
                    hours=int(hours), minutes=int(minutes))
        out2 = self.adb_client.shell_sync("uptime", self.serial, timeout=2)
        if "up time:" in out2:
            match = re.search(r"up time:\s*([^,]+)", out2)
            if match:
                return match.group(1).strip()
        return self.tr("未知")

    def _get_cpu_info(self) -> str:
        """获取 CPU 信息 (Retrieve CPU info)"""
        out = self.adb_client.shell_sync("cat /proc/cpuinfo", self.serial)
        for line in out.splitlines():
            if "Hardware" in line:
                return line.split(":")[1].strip()
            if "Processor" in line:
                return line.split(":")[1].strip()
        return self.tr("未知")

    def _get_memory_info(self) -> str:
        """获取内存信息 (Retrieve memory info)"""
        out = self.adb_client.shell_sync("cat /proc/meminfo", self.serial, timeout=3)
        mem_data = {}
        for line in out.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                mem_data[key.strip()] = val.strip()

        total = mem_data.get("MemTotal", "0").split()[0]
        total_mb = int(total) // 1024 if total.isdigit() else "?"
        avail_mb = "?"

        if "MemAvailable" in mem_data:
            avail = mem_data["MemAvailable"].split()[0]
            if avail.isdigit():
                avail_mb = int(avail) // 1024
        else:
            free = mem_data.get("MemFree", "0").split()[0]
            buffers = mem_data.get("Buffers", "0").split()[0]
            cached = mem_data.get("Cached", "0").split()[0]
            if free.isdigit() and buffers.isdigit() and cached.isdigit():
                avail_mb = (int(free) + int(buffers) + int(cached)) // 1024
        return self.tr("总计 {total} MB, 可用 {avail} MB").format(total=total_mb, avail=avail_mb)

    def _get_storage_info(self) -> str:
        """获取存储信息 (Retrieve storage info)"""
        out = self.adb_client.shell_sync("df /data", self.serial, timeout=3)
        if not out:
            return self.tr("未知")
        lines = out.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                size = parts[1]
                used = parts[2]
                try:
                    size_int = int(size)
                    used_int = int(used)
                    size_str = f"{size_int / 1048576:.1f} GB" if size_int >= 1048576 else f"{size_int / 1024:.1f} MB"
                    used_str = f"{used_int / 1048576:.1f} GB" if used_int >= 1048576 else f"{used_int / 1024:.1f} MB"
                    return self.tr("总容量 {size_str}, 已用 {used_str}").format(
                        size_str=size_str, used_str=used_str)
                except ValueError:
                    return self.tr("总容量 {size}, 已用 {used}").format(size=size, used=used)
        return self.tr("未知")

    def _get_display_detail(self) -> str:
        """获取显示屏详情 (Retrieve display detail)"""
        out = self.adb_client.shell_sync("dumpsys display | grep -E 'mDisplayInfo|DisplayDeviceInfo|PhysicalDisplayInfo'", self.serial, timeout=3)
        if out.strip():
            return out.strip()
        size = self.adb_client.shell_sync("wm size", self.serial, timeout=2).strip()
        density = self.adb_client.shell_sync("wm density", self.serial, timeout=2).strip()
        parts = []
        if "Physical size" in size:
            parts.append(size.split(":")[-1].strip())
        if "Physical density" in density:
            parts.append(density.split(":")[-1].strip())
        return "\n".join(parts) if parts else self.tr("未知")

    # ========== 工具栏操作 (Toolbar Actions) ==========

    def toggle_airplane_mode(self, checked):
        """切换飞行模式 (Toggle airplane mode)"""
        if checked:
            self.adb_client.shell_sync("settings put global airplane_mode_on 1", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText(self.tr("飞行模式已开启"))
        else:
            self.adb_client.shell_sync("settings put global airplane_mode_on 0", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText(self.tr("飞行模式已关闭"))
        self.airplane_action.setChecked(checked)

    def rotate_screen(self):
        """旋转屏幕 (Rotate screen)"""
        out = self.adb_client.shell_sync("settings get system user_rotation", self.serial)
        try:
            current = int(out.strip())
        except:
            current = 0
        next_rotation = (current + 90) % 360
        self.adb_client.shell_sync(f"settings put system user_rotation {next_rotation//90}", self.serial)
        self.status_label.setText(self.tr("屏幕旋转至 {degree}°").format(degree=next_rotation))

    def take_screenshot(self):
        """截图保存到本地 (Take screenshot and save)"""
        default_name = f"screenshot_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存截图"), default_name, self.tr("PNG图片 (*.png)")
        )
        if not file_path:
            return
        self.status_label.setText(self.tr("正在截图..."))
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(lambda code: self._on_screenshot_finished(code, proc, file_path))
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "exec-out", "screencap", "-p"])

    def _on_screenshot_finished(self, exit_code, proc, file_path):
        """截图完成回调 (Screenshot finished callback)"""
        if exit_code == 0:
            data = proc.readAllStandardOutput()
            try:
                with open(file_path, "wb") as f:
                    f.write(data.data())
                self.status_label.setText(self.tr("截图已保存: {path}").format(path=file_path))
                QMessageBox.information(
                    self,
                    self.tr("截图成功"),
                    self.tr("截图已保存到:\n{path}").format(path=file_path)
                )
            except Exception as e:
                self.status_label.setText(self.tr("保存截图失败"))
                QMessageBox.warning(self, self.tr("错误"), self.tr("保存截图失败: {error}").format(error=str(e)))
        else:
            self.status_label.setText(self.tr("截图失败"))
            QMessageBox.warning(self, self.tr("错误"), self.tr("截图失败，请确保设备已解锁且支持 screencap 命令。"))
        self.status_label.setText(self.tr("就绪"))

    def start_recording(self):
        """开始录制屏幕 (Start screen recording)"""
        default_name = f"screen_record_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存录制文件"), default_name, self.tr("MP4视频 (*.mp4)")
        )
        if not file_path:
            return

        self.raise_()
        self.activateWindow()

        self.recording_file = file_path
        self.recording_remote_path = "/sdcard/temp_record.mp4"
        self.status_label.setText(self.tr("正在录制..."))

        self.adb_client.shell_sync(f"rm {self.recording_remote_path}", self.serial)

        self.recording_proc = subprocess.Popen(
            [self.adb_client.adb_path, "-s", self.serial, "shell", "screenrecord", self.recording_remote_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(1)

        pid_out = self.adb_client.shell_sync("pgrep screenrecord", self.serial)
        try:
            self.recording_pid = int(pid_out.strip())
        except:
            self.recording_pid = None

        self.record_action.setText(self.tr("停止录制"))
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.stop_recording)

    def stop_recording(self):
        """停止录制并拉取文件 (Stop recording and pull file)"""
        if hasattr(self, 'recording_pid') and self.recording_pid:
            self.status_label.setText(self.tr("正在停止录制..."))
            self.adb_client.shell_sync(f"kill -2 {self.recording_pid}", self.serial)
            import time
            for _ in range(10):
                time.sleep(0.5)
                if self._check_file_exists(self.recording_remote_path):
                    break
            self._finish_recording()
        else:
            self._finish_recording()

    def _check_file_exists(self, remote_path):
        """检查设备上文件是否存在 (Check if file exists on device)"""
        out = self.adb_client.shell_sync(f"ls {remote_path}", self.serial)
        return "No such file" not in out and remote_path in out

    def _finish_recording(self):
        """完成录制并拉取文件到本地 (Finish recording and pull file)"""
        self.status_label.setText(self.tr("正在拉取文件..."))
        try:
            self.adb_client.pull_sync(self.recording_remote_path, self.recording_file, self.serial, timeout=60)
            self.adb_client.shell_sync(f"rm {self.recording_remote_path}", self.serial)
            self.status_label.setText(self.tr("录制完成: {path}").format(path=self.recording_file))
            QMessageBox.information(
                self,
                self.tr("录制成功"),
                self.tr("屏幕录制已保存到:\n{path}").format(path=self.recording_file)
            )
        except Exception as e:
            self.status_label.setText(self.tr("拉取文件失败"))
            QMessageBox.warning(
                self,
                self.tr("录制失败"),
                self.tr("拉取录制文件失败: {error}").format(error=str(e))
            )

        self.record_action.setText(self.tr("开始录制"))
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.start_recording)
        self.recording_pid = None

    def reboot_device(self, mode: str = ""):
        """重启设备 (Reboot device)"""
        mode_text_map = {
            "": self.tr("重启"),
            "recovery": self.tr("重启到 Recovery"),
            "bootloader": self.tr("重启到 Bootloader")
        }
        mode_text = mode_text_map.get(mode, self.tr("重启"))
        reply = QMessageBox.question(
            self,
            self.tr("确认操作"),
            self.tr("确定要{mode_text}设备 {serial} 吗？").format(mode_text=mode_text, serial=self.serial),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText(self.tr("正在{mode_text}...").format(mode_text=mode_text))
            self.adb_client.reboot(self.serial, mode,
                                   callback=lambda code, out, err: self._on_reboot_finished(code, mode_text))

    def _on_reboot_finished(self, exit_code, mode_text):
        """重启操作完成回调 (Reboot finished callback)"""
        if exit_code == 0:
            self.status_label.setText(self.tr("{mode_text}命令已发送").format(mode_text=mode_text))
            QMessageBox.information(
                self,
                self.tr("操作成功"),
                self.tr("{mode_text}命令已发送，设备将开始重启。").format(mode_text=mode_text)
            )
        else:
            self.status_label.setText(self.tr("{mode_text}失败").format(mode_text=mode_text))
            QMessageBox.warning(
                self,
                self.tr("错误"),
                self.tr("{mode_text}失败，请检查设备连接。").format(mode_text=mode_text)
            )
        self.status_label.setText(self.tr("就绪"))

    def shutdown_device(self):
        """关闭设备 (Shutdown device)"""
        reply = QMessageBox.question(
            self,
            self.tr("确认操作"),
            self.tr("确定要关闭设备 {serial} 吗？").format(serial=self.serial),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText(self.tr("正在关机..."))
            self.adb_client.shell("reboot -p", self.serial,
                                  callback=lambda code, out, err: self._on_shutdown_finished(code))

    def _on_shutdown_finished(self, exit_code):
        """关机操作完成回调 (Shutdown finished callback)"""
        if exit_code == 0:
            self.status_label.setText(self.tr("关机命令已发送"))
            QMessageBox.information(self, self.tr("操作成功"), self.tr("关机命令已发送，设备将关闭。"))
        else:
            self.status_label.setText(self.tr("关机失败"))
            QMessageBox.warning(self, self.tr("错误"), self.tr("关机失败，请检查设备权限。"))
        self.status_label.setText(self.tr("就绪"))

    # ========== Root 管理 (Root Management) ==========

    def enable_root(self):
        """尝试以 root 权限重启 adbd (Enable root via adbd restart)"""
        self.status_label.setText(self.tr("正在提权..."))
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self._on_root_command_finished)
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "root"])

    def _on_root_command_finished(self, exit_code, exit_status):
        """提权命令完成回调 (Root command finished callback)"""
        self.status_label.setText(self.tr("提权命令已发送，等待设备重新连接..."))
        QTimer.singleShot(1000, lambda: self._check_root_status(0))
        self.status_label.setText(self.tr("就绪"))

    def _check_root_status(self, retry):
        """检查 root 状态是否生效 (Check if root is active)"""
        if retry >= 10:
            self.status_label.setText(self.tr("提权失败：超时"))
            QMessageBox.warning(self, self.tr("提权失败"), self.tr("设备未能在预期时间内切换到 root 模式。"))
            return
        out = self.adb_client.shell_sync("id", self.serial, timeout=2)
        if "uid=0" in out:
            self.status_label.setText(self.tr("提权成功，adbd 已以 root 权限运行"))
            QMessageBox.information(self, self.tr("提权成功"), self.tr("adbd 已以 root 权限运行。"))
            QTimer.singleShot(1000, self.load_device_info_async)
        else:
            QTimer.singleShot(1000, lambda: self._check_root_status(retry + 1))

    def disable_root(self):
        """解除 root 模式 (Disable root)"""
        self.status_label.setText(self.tr("正在解除提权..."))
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self._on_unroot_command_finished)
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "unroot"])

    def _on_unroot_command_finished(self, exit_code, exit_status):
        """解提权命令完成回调 (Unroot command finished callback)"""
        self.status_label.setText(self.tr("解提权命令已发送，等待设备重新连接..."))
        QTimer.singleShot(1000, lambda: self._check_unroot_status(0))
        self.status_label.setText(self.tr("就绪"))

    def _check_unroot_status(self, retry):
        """检查 root 是否已解除 (Check if root is disabled)"""
        if retry >= 10:
            self.status_label.setText(self.tr("解提权失败：超时"))
            QMessageBox.warning(self, self.tr("解提权失败"), self.tr("设备未能在预期时间内切换到非 root 模式。"))
            return
        out = self.adb_client.shell_sync("id", self.serial, timeout=2)
        if "uid=0" not in out:
            self.status_label.setText(self.tr("已解除 root 模式"))
            QMessageBox.information(self, self.tr("解提权成功"), self.tr("adbd 已恢复为非 root 模式。"))
            QTimer.singleShot(1000, self.load_device_info_async)
        else:
            QTimer.singleShot(1000, lambda: self._check_unroot_status(retry + 1))

    def remount_system(self):
        """重新挂载 /system 为可读写 (Remount /system as read-write)"""
        out = self.adb_client.shell_sync("id", self.serial)
        if "uid=0" not in out:
            reply = QMessageBox.question(
                self,
                self.tr("需要 root"),
                self.tr("重新挂载 system 需要 root 权限，是否先提权？"),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.enable_root()
            return
        self.status_label.setText(self.tr("正在重新挂载 /system ..."))
        out = self.adb_client.shell_sync("mount -o remount,rw /system", self.serial)
        if "remount succeeded" in out or "remounted" in out:
            self.status_label.setText(self.tr("重新挂载成功，/system 现在可读写"))
            QMessageBox.information(self, self.tr("成功"), self.tr("/system 已重新挂载为可读写"))
        else:
            self.status_label.setText(self.tr("重新挂载失败"))
            QMessageBox.warning(self, self.tr("失败"), self.tr("重新挂载 /system 失败:\n{output}").format(output=out))

    def show_mounts(self):
        """显示分区挂载信息 (Show mount info)"""
        self.status_label.setText(self.tr("正在获取分区挂载信息..."))
        out = self.adb_client.shell_sync("cat /proc/mounts", self.serial)
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("分区挂载信息"))
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(out)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        text_edit.setFont(fixed_font)
        layout.addWidget(text_edit)
        btn = QPushButton(self.tr("关闭"))
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        dialog.resize(800, 600)
        dialog.exec_()
        self.status_label.setText(self.tr("就绪"))

    # ========== 沉浸模式 (Immersive Mode) ==========

    def toggle_immersive_status_bar(self, checked):
        """切换状态栏沉浸 (Toggle status bar immersive)"""
        self._set_immersive("status", checked)
        self.immersive_status_action.setChecked(checked)

    def toggle_immersive_navigation(self, checked):
        """切换导航栏沉浸 (Toggle navigation bar immersive)"""
        self._set_immersive("navigation", checked)
        self.immersive_nav_action.setChecked(checked)

    def _set_immersive(self, target: str, enable: bool):
        """设置沉浸模式 (Set immersive mode)"""
        if enable:
            cmd = f"settings put global policy_control immersive.{target}=*"
            desc = self.tr("沉浸{target_name}已开启").format(
                target_name=self.tr("状态栏") if target == "status" else self.tr("导航栏")
            )
        else:
            cmd = "settings put global policy_control null*"
            desc = self.tr("沉浸{target_name}已关闭").format(
                target_name=self.tr("状态栏") if target == "status" else self.tr("导航栏")
            )
        self.status_label.setText(self.tr("正在设置{target_name}...").format(
            target_name=self.tr("状态栏") if target == "status" else self.tr("导航栏")
        ))
        self.adb_client.shell(cmd, self.serial,
                              callback=lambda code, out, err: self._on_immersive_done(desc))
        self.status_label.setText(self.tr("就绪"))

    def _on_immersive_done(self, desc):
        """沉浸模式设置完成 (Immersive setting done)"""
        self.status_label.setText(desc)
        QTimer.singleShot(3000, lambda: self.status_label.setText(self.tr("就绪")))

    # ========== 其他对话框 (Other Dialogs) ==========

    def open_monkey_dialog(self):
        """打开 Monkey 测试对话框 (Open Monkey test dialog)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QCheckBox
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Monkey 压力测试"))
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        self.monkey_package = QLineEdit()
        self.monkey_package.setPlaceholderText(self.tr("留空则测试所有应用"))
        form.addRow(self.tr("目标包名:"), self.monkey_package)
        self.monkey_events = QSpinBox()
        self.monkey_events.setRange(100, 100000)
        self.monkey_events.setValue(1000)
        form.addRow(self.tr("事件数量:"), self.monkey_events)
        self.monkey_throttle = QSpinBox()
        self.monkey_throttle.setRange(0, 1000)
        self.monkey_throttle.setValue(100)
        form.addRow(self.tr("事件延时(ms):"), self.monkey_throttle)
        self.monkey_seed = QSpinBox()
        self.monkey_seed.setRange(1, 10000)
        self.monkey_seed.setValue(1234)
        form.addRow(self.tr("随机种子:"), self.monkey_seed)
        self.monkey_ignore_crashes = QCheckBox(self.tr("忽略崩溃"))
        self.monkey_ignore_crashes.setChecked(True)
        form.addRow("", self.monkey_ignore_crashes)
        self.monkey_ignore_timeouts = QCheckBox(self.tr("忽略超时"))
        self.monkey_ignore_timeouts.setChecked(True)
        form.addRow("", self.monkey_ignore_timeouts)

        layout.addLayout(form)
        self.monkey_log = QTextEdit()
        self.monkey_log.setReadOnly(True)
        layout.addWidget(self.monkey_log)

        btn_box = QDialogButtonBox()
        start_btn = QPushButton(self.tr("开始测试"))
        stop_btn = QPushButton(self.tr("停止"))
        cancel_btn = QPushButton(self.tr("关闭"))
        btn_box.addButton(start_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(stop_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        layout.addWidget(btn_box)

        start_btn.clicked.connect(lambda: self.start_monkey_test(dialog))
        stop_btn.clicked.connect(lambda: self.stop_monkey_test())
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec_()

    def start_monkey_test(self, dialog):
        """启动 Monkey 测试 (Start monkey test)"""
        pkg = self.monkey_package.text().strip()
        events = self.monkey_events.value()
        throttle = self.monkey_throttle.value()
        seed = self.monkey_seed.value()
        ignore_crashes = self.monkey_ignore_crashes.isChecked()
        ignore_timeouts = self.monkey_ignore_timeouts.isChecked()

        cmd = ["monkey"]
        if pkg:
            cmd.extend(["-p", pkg])
        cmd.extend(["-v", "-v", "-v"])
        cmd.extend(["--throttle", str(throttle)])
        cmd.extend(["-s", str(seed)])
        if ignore_crashes:
            cmd.append("--ignore-crashes")
        if ignore_timeouts:
            cmd.append("--ignore-timeouts")
        cmd.append(str(events))

        self.monkey_log.append(self.tr(">>> 开始测试: {cmd}").format(cmd=' '.join(cmd)))
        self.monkey_process = QProcess(self)
        self.monkey_process.setProcessChannelMode(QProcess.MergedChannels)
        self.monkey_process.readyReadStandardOutput.connect(lambda: self._on_monkey_output())
        self.monkey_process.finished.connect(self._on_monkey_finished)
        self.monkey_process.start(self.adb_client.adb_path, ["-s", self.serial, "shell"] + cmd)

        dialog.setWindowTitle(self.tr("Monkey 测试运行中..."))
        for child in dialog.findChildren(QPushButton):
            if child.text() == self.tr("开始测试"):
                child.setEnabled(False)
            elif child.text() == self.tr("停止"):
                child.setEnabled(True)

    def _on_monkey_output(self):
        """Monkey 输出回调 (Monkey output callback)"""
        data = self.monkey_process.readAllStandardOutput().data()
        text = data.decode('utf-8', errors='ignore')
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(text)

    def _on_monkey_finished(self, exit_code, exit_status):
        """Monkey 测试结束回调 (Monkey finished callback)"""
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(self.tr(">>> 测试结束，退出码: {exit_code}").format(exit_code=exit_code))

    def stop_monkey_test(self):
        """停止 Monkey 测试 (Stop monkey test)"""
        if hasattr(self, 'monkey_process') and self.monkey_process.state() == QProcess.Running:
            self.monkey_process.kill()
            self.monkey_process.waitForFinished(2000)
            if hasattr(self, 'monkey_log'):
                self.monkey_log.append(self.tr(">>> 用户手动停止测试"))

    def open_tcpdump_dialog(self):
        """打开 tcpdump 抓包对话框 (Open tcpdump dialog)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QCheckBox
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("tcpdump 抓包"))
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        self.dump_duration = QSpinBox()
        self.dump_duration.setRange(0, 3600)
        self.dump_duration.setValue(30)
        self.dump_duration.setSpecialValueText(self.tr("无限制"))
        form.addRow(self.tr("持续时间(秒):"), self.dump_duration)

        self.dump_count = QSpinBox()
        self.dump_count.setRange(0, 100000)
        self.dump_count.setValue(1000)
        self.dump_count.setSpecialValueText(self.tr("无限制"))
        form.addRow(self.tr("包数量限制:"), self.dump_count)

        self.dump_filter = QLineEdit()
        self.dump_filter.setPlaceholderText(self.tr("例如: host 192.168.1.1 or port 80"))
        form.addRow(self.tr("过滤表达式:"), self.dump_filter)

        self.remote_file = QLineEdit("/sdcard/capture.pcap")
        form.addRow(self.tr("设备临时文件:"), self.remote_file)

        layout.addLayout(form)

        self.dump_log = QTextEdit()
        self.dump_log.setReadOnly(True)
        layout.addWidget(self.dump_log)

        btn_box = QDialogButtonBox()
        start_btn = QPushButton(self.tr("开始抓包"))
        stop_btn = QPushButton(self.tr("停止"))
        save_btn = QPushButton(self.tr("保存并关闭"))
        cancel_btn = QPushButton(self.tr("取消"))
        btn_box.addButton(start_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(stop_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(save_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        layout.addWidget(btn_box)

        start_btn.clicked.connect(lambda: self.start_tcpdump(dialog))
        stop_btn.clicked.connect(lambda: self.stop_tcpdump(dialog))
        save_btn.clicked.connect(lambda: self.save_tcpdump(dialog))
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def start_tcpdump(self, dialog):
        """启动 tcpdump 抓包 (Start tcpdump)"""
        duration = self.dump_duration.value()
        count = self.dump_count.value()
        filter_exp = self.dump_filter.text().strip()
        remote_file = self.remote_file.text().strip()

        cmd = ["tcpdump", "-i", "any", "-w", remote_file]
        if duration > 0:
            cmd.extend(["-G", str(duration), "-W", "1"])
        if count > 0:
            cmd.extend(["-c", str(count)])
        if filter_exp:
            cmd.extend([filter_exp])

        self.dump_log.append(self.tr(">>> 开始抓包: {cmd}").format(cmd=' '.join(cmd)))
        self.tcpdump_process = QProcess(self)
        self.tcpdump_process.setProcessChannelMode(QProcess.MergedChannels)
        self.tcpdump_process.readyReadStandardOutput.connect(lambda: self._on_tcpdump_output())
        self.tcpdump_process.finished.connect(lambda: self._on_tcpdump_finished(dialog))
        full_cmd = ["-s", self.serial, "shell", "su", "-c"] + cmd
        self.tcpdump_process.start(self.adb_client.adb_path, full_cmd)

        dialog.setWindowTitle(self.tr("tcpdump 抓包中..."))
        for child in dialog.findChildren(QPushButton):
            if child.text() == self.tr("开始抓包"):
                child.setEnabled(False)
            elif child.text() == self.tr("停止"):
                child.setEnabled(True)

    def _on_tcpdump_output(self):
        """tcpdump 输出回调 (tcpdump output callback)"""
        data = self.tcpdump_process.readAllStandardOutput().data()
        text = data.decode('utf-8', errors='ignore')
        if hasattr(self, 'dump_log'):
            self.dump_log.append(text)

    def _on_tcpdump_finished(self, dialog):
        """tcpdump 结束回调 (tcpdump finished callback)"""
        if hasattr(self, 'dump_log'):
            self.dump_log.append(self.tr(">>> 抓包进程结束"))
        for child in dialog.findChildren(QPushButton):
            if child.text() == self.tr("开始抓包"):
                child.setEnabled(True)
            elif child.text() == self.tr("停止"):
                child.setEnabled(False)

    def stop_tcpdump(self, dialog):
        """停止 tcpdump 抓包 (Stop tcpdump)"""
        if hasattr(self, 'tcpdump_process') and self.tcpdump_process.state() == QProcess.Running:
            self.tcpdump_process.terminate()
            self.tcpdump_process.waitForFinished(2000)
            self.dump_log.append(self.tr(">>> 用户手动停止抓包"))

    def save_tcpdump(self, dialog):
        """保存抓包文件并关闭对话框 (Save capture and close dialog)"""
        remote_file = self.remote_file.text().strip()
        local_path, _ = QFileDialog.getSaveFileName(
            dialog, self.tr("保存抓包文件"), "capture.pcap", self.tr("PCAP文件 (*.pcap)")
        )
        if not local_path:
            return
        self.dump_log.append(self.tr(">>> 正在拉取文件: {remote} -> {local}").format(
            remote=remote_file, local=local_path))
        try:
            self.adb_client.pull_sync(remote_file, local_path, self.serial)
            self.dump_log.append(self.tr(">>> 拉取成功"))
            QMessageBox.information(
                dialog,
                self.tr("成功"),
                self.tr("抓包文件已保存到:\n{path}").format(path=local_path)
            )
            self.adb_client.shell_sync(f"rm {remote_file}", self.serial)
            dialog.accept()
        except Exception as e:
            self.dump_log.append(self.tr(">>> 拉取失败: {error}").format(error=str(e)))
            QMessageBox.warning(
                dialog,
                self.tr("失败"),
                self.tr("拉取文件失败:\n{error}").format(error=str(e))
            )

    def open_soft_keyboard(self):
        """打开软键盘对话框 (Open soft keyboard dialog)"""
        from ui.soft_keyboard import SoftKeyboardWindow
        dlg = SoftKeyboardWindow(self.serial, self.adb_client, self)
        dlg.exec_()

    def open_broadcast_dialog(self):
        """打开发送广播对话框 (Open broadcast dialog)"""
        from ui.broadcast_dialog import BroadcastDialog
        dlg = BroadcastDialog(self.serial, self.adb_client, self)
        dlg.exec_()

    # ========== 辅助方法 (Helper Methods) ==========

    def show_status_message(self, msg: str):
        """更新状态栏消息 (Update status bar message)"""
        self.status_label.setText(msg)

    def closeEvent(self, event):
        """窗口关闭事件，发出 closed 信号 (Window close event, emit closed signal)"""
        self.closed.emit(self.serial)
        event.accept()
