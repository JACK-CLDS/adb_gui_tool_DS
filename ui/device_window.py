"""
ui/device_window.py - 设备控制窗口 (Device Control Window)

为单个 Android 设备提供完整的控制界面，包含设备信息、应用管理、文件管理、
日志查看、进程管理、终端、代理设置等选项卡，以及截图、录制、重启等工具栏操作。
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

    status_message = pyqtSignal(str)   # 状态栏消息信号
    closed = pyqtSignal(str)           # 窗口关闭信号，传递设备序列号

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
        self.load_device_info_async()
        self.status_message.connect(self.show_status_message)

        # 录制相关变量
        self.recording_process = None
        self.recording_file = None
        self.recording_pid = None

        self.setup_shortcuts()

    # ========== 界面初始化 ==========

    def init_ui(self):
        """创建主界面布局 (Create main UI layout)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget, 1)

        self.info_tab = self.create_info_tab()
        self.tab_widget.addTab(self.info_tab, "设备信息")

        self.apps_tab = self.create_apps_tab()
        self.tab_widget.addTab(self.apps_tab, "应用管理")

        self.file_tab = self.create_file_manager_tab()
        self.tab_widget.addTab(self.file_tab, "文件管理")

        self.log_tab = self.create_log_tab()
        self.tab_widget.addTab(self.log_tab, "日志")

        self.advanced_tab = self.create_process_manager_tab()
        self.tab_widget.addTab(self.advanced_tab, "进程管理")

        self.terminal_tab = self.create_terminal_tab()
        self.tab_widget.addTab(self.terminal_tab, "终端")

        self.proxy_tab = self.create_proxy_tab()
        self.tab_widget.addTab(self.proxy_tab, "代理设置")

    def init_toolbar(self):
        """创建设备操作工具栏 (Create device toolbar)"""
        toolbar = self.addToolBar("设备操作")
        toolbar.setMovable(False)

        # 截图 (Screenshot)
        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

        # 飞行模式 (Airplane mode)
        self.airplane_action = QAction("飞行模式", self, checkable=True)
        self.airplane_action.triggered.connect(self.toggle_airplane_mode)
        toolbar.addAction(self.airplane_action)

        # 旋转屏幕 (Rotate screen)
        self.rotate_action = QAction("旋转屏幕", self)
        self.rotate_action.triggered.connect(self.rotate_screen)
        toolbar.addAction(self.rotate_action)

        # 录制 (Record)
        self.record_action = QAction("开始录制", self)
        self.record_action.triggered.connect(self.start_recording)
        toolbar.addAction(self.record_action)

        toolbar.addSeparator()

        # 重启选项 (Reboot options)
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

        # 关机 (Shutdown)
        shutdown_action = QAction("关机", self)
        shutdown_action.triggered.connect(self.shutdown_device)
        toolbar.addAction(shutdown_action)

        toolbar.addSeparator()

        # Root 权限管理 (Root management)
        root_action = QAction("提权 (root)", self)
        root_action.triggered.connect(self.enable_root)
        toolbar.addAction(root_action)
        unroot_action = QAction("解提权 (unroot)", self)
        unroot_action.triggered.connect(self.disable_root)
        toolbar.addAction(unroot_action)

        self.remount_action = QAction("重新挂载 system", self)
        self.remount_action.triggered.connect(self.remount_system)
        toolbar.addAction(self.remount_action)

        self.mounts_action = QAction("查看分区挂载", self)
        self.mounts_action.triggered.connect(self.show_mounts)
        toolbar.addAction(self.mounts_action)

        toolbar.addSeparator()

        # 刷新信息 (Refresh info)
        refresh_action = QAction("刷新信息", self)
        refresh_action.triggered.connect(self.load_device_info_async)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        # Monkey 测试 (Monkey test)
        monkey_action = QAction("Monkey测试", self)
        monkey_action.triggered.connect(self.open_monkey_dialog)
        toolbar.addAction(monkey_action)

        toolbar.addSeparator()

        # tcpdump 抓包 (Packet capture)
        tcpdump_action = QAction("tcpdump抓包", self)
        tcpdump_action.triggered.connect(self.open_tcpdump_dialog)
        toolbar.addAction(tcpdump_action)

        toolbar.addSeparator()

        # 软键盘 (Soft keyboard)
        keyboard_action = QAction("软键盘", self)
        keyboard_action.triggered.connect(self.open_soft_keyboard)
        toolbar.addAction(keyboard_action)

        toolbar.addSeparator()

        # 发送广播 (Send broadcast)
        broadcast_action = QAction("发送广播", self)
        broadcast_action.triggered.connect(self.open_broadcast_dialog)
        toolbar.addAction(broadcast_action)

        toolbar.addSeparator()

        # 沉浸模式 (Immersive mode)
        self.immersive_status_action = QAction("沉浸状态栏", self, checkable=True)
        self.immersive_status_action.triggered.connect(self.toggle_immersive_status_bar)
        toolbar.addAction(self.immersive_status_action)

        self.immersive_nav_action = QAction("沉浸导航栏", self, checkable=True)
        self.immersive_nav_action.triggered.connect(self.toggle_immersive_navigation)
        toolbar.addAction(self.immersive_nav_action)

    def init_statusbar(self):
        """初始化状态栏 (Initialize status bar)"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    # ========== 快捷键设置 ==========

    def setup_shortcuts(self):
        """读取配置中的快捷键并绑定 (Setup keyboard shortcuts from config)"""
        defaults = {
            "close": "Ctrl+W",
            "screenshot": "Ctrl+Shift+S",
            "refresh_info": "F5",
            "recording": "Ctrl+Shift+R",
        }
        # 清除已有的快捷键
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

    # ========== 选项卡片段 ==========

    def create_info_tab(self) -> QWidget:
        """创建设备信息选项卡 (Create device info tab)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        def make_label(text="未知", align_left=False):
            label = QLabel(text)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            if align_left:
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return label

        # ---- 基本信息 (Basic info) ----
        info_group = QGroupBox("基本信息")
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.model_label = make_label()
        self.android_version_label = make_label()
        self.battery_label = make_label()
        self.resolution_label = make_label()
        self.serial_label = make_label(self.serial)

        form_layout.addRow("设备型号:", self.model_label)
        form_layout.addRow("Android 版本:", self.android_version_label)
        form_layout.addRow("电池状态:", self.battery_label)
        form_layout.addRow("屏幕分辨率:", self.resolution_label)
        form_layout.addRow("序列号:", self.serial_label)
        info_group.setLayout(form_layout)
        layout.addWidget(info_group, 0)

        # ---- 硬件与系统信息 (Hardware & system info) ----
        hardware_group = QGroupBox("硬件与系统信息")
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

        # 内存信息 - 无边框文本框，防止文本截断 (Memory info)
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

        hw_layout.addRow("IMEI:", self.imei_label)
        hw_layout.addRow("MAC 地址:", self.mac_label)
        hw_layout.addRow("蓝牙地址:", self.bluetooth_label)
        hw_layout.addRow("网络状态:", self.network_label)
        hw_layout.addRow("开机时间:", self.uptime_label)
        hw_layout.addRow("CPU 信息:", self.cpu_label)
        hw_layout.addRow("内存信息:", self.memory_label)
        hw_layout.addRow("存储信息:", self.storage_label)
        hw_layout.addRow("显示屏详情:", self.display_detail_label)

        hardware_group.setLayout(hw_layout)
        hardware_group.setMaximumHeight(400)   # 阻止硬件组垂直拉伸
        layout.addWidget(hardware_group, 0)

        # ---- 详细属性 (Detailed properties) ----
        detail_group = QGroupBox("详细属性 (getprop)")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group, 1)      # 占据所有剩余空间

        return widget

    def create_apps_tab(self) -> QWidget:
        from ui.apps_tab import AppsTab
        return AppsTab(self.serial, self.adb_client)

    def create_file_manager_tab(self) -> QWidget:
        from ui.file_manager import FileManager
        return FileManager(self.serial, self.adb_client, parent=self)

    def create_log_tab(self) -> QWidget:
        from ui.logcat_tab import LogcatTab
        return LogcatTab(self.serial, self.adb_client)

    def create_process_manager_tab(self) -> QWidget:
        from ui.process_manager import ProcessManager
        pm = ProcessManager(self.serial, self.adb_client)
        pm.status_message.connect(self.show_status_message)
        return pm

    def create_terminal_tab(self) -> QWidget:
        from ui.terminal import TerminalWidget
        terminal = TerminalWidget(self.serial, self.adb_client)
        terminal.status_message.connect(self.show_status_message)
        return terminal

    def create_proxy_tab(self) -> QWidget:
        from ui.proxy_tab import ProxyTab
        return ProxyTab(self.serial, self.adb_client)

    # ========== 设备信息异步加载 ==========

    def load_device_info_async(self):
        """异步加载设备信息，逐步更新 UI 避免卡顿 (Load device info asynchronously)"""
        self.status_label.setText("正在获取设备信息...")
        if hasattr(self, '_loading') and self._loading:
            return
        self._loading = True

        tasks = [
            ("设备型号", lambda: self.adb_client.shell_sync("getprop ro.product.model", self.serial, timeout=2),
             lambda val: self.model_label.setText(val.strip() or "未知")),
            ("Android版本", lambda: self.adb_client.shell_sync("getprop ro.build.version.release", self.serial, timeout=2),
             lambda val: self.android_version_label.setText(val.strip() or "未知")),
            ("电池信息", lambda: self.adb_client.shell_sync("dumpsys battery", self.serial, timeout=5),
             lambda out: self._parse_battery(out)),
            ("屏幕分辨率", lambda: self.adb_client.shell_sync("wm size", self.serial, timeout=2),
             lambda out: self._parse_resolution(out)),
            ("IMEI", lambda: self._get_imei(), lambda val: self.imei_label.setText(val)),
            ("MAC地址", lambda: self._get_mac_address(), lambda val: self.mac_label.setText(val)),
            ("蓝牙地址", lambda: self._get_bluetooth_address(), lambda val: self.bluetooth_label.setText(val)),
            ("网络状态", lambda: self._get_network_status(), lambda val: self.network_label.setText(val)),
            ("开机时间", lambda: self._get_uptime(), lambda val: self.uptime_label.setText(val)),
            ("CPU信息", lambda: self._get_cpu_info(), lambda val: self.cpu_label.setText(val)),
            ("内存信息", lambda: self._get_memory_info(), lambda val: self.memory_label.setPlainText(val)),
            ("存储信息", lambda: self._get_storage_info(), lambda val: self.storage_label.setPlainText(val)),
            ("显示屏详情", lambda: self._get_display_detail(), lambda val: self.display_detail_label.setText(val)),
            ("详细属性", lambda: self.adb_client.shell_sync("getprop", self.serial, timeout=8),
             lambda out: self.detail_text.setText(out)),
        ]

        self._task_index = 0
        self._tasks = tasks
        self._run_next_task()

    def _run_next_task(self):
        """执行下一个任务，使用 QTimer 避免阻塞"""
        if self._task_index >= len(self._tasks):
            self.status_label.setText("设备信息已更新")
            self._loading = False
            return
        desc, func, update_ui = self._tasks[self._task_index]
        self.status_label.setText(f"正在获取 {desc}...")
        try:
            result = func()
            update_ui(result)
        except Exception as e:
            print(f"获取 {desc} 失败: {e}")
            update_ui("获取失败")
        self._task_index += 1
        QTimer.singleShot(10, self._run_next_task)

    # ========== 信息解析函数 ==========

    def _parse_battery(self, output: str):
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

    def _parse_resolution(self, output: str):
        if "Physical size:" in output:
            self.resolution_label.setText(output.split(":")[1].strip())
        else:
            self.resolution_label.setText("未知")

    def _get_imei(self) -> str:
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
        return "需权限/不可用"

    def _get_mac_address(self) -> str:
        import re
        out = self.adb_client.shell_sync("for iface in /sys/class/net/*/address; do [ -f $iface ] && addr=$(cat $iface) && [ -n $addr ] && [ $addr != '00:00:00:00:00:00' ] && iface_name=$(dirname $iface | xargs basename) && [ $iface_name != 'lo' ] && echo $iface_name $addr; done", self.serial, timeout=3)
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
        return "未知"

    def _get_bluetooth_address(self) -> str:
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
        return "未知"

    def _get_network_status(self) -> str:
        out = self.adb_client.shell_sync("dumpsys connectivity | grep -A 5 'NetworkAgentInfo'", self.serial)
        if "WIFI" in out and "CONNECTED" in out:
            return "WiFi 已连接"
        elif "CELLULAR" in out and "CONNECTED" in out:
            return "移动网络已连接"
        else:
            return "无网络连接"

    def _get_uptime(self) -> str:
        import re
        out = self.adb_client.shell_sync("cat /proc/uptime", self.serial, timeout=2)
        if out.strip():
            seconds = float(out.split()[0])
            days, rem = divmod(seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            if days >= 1:
                return f"{int(days)}天 {int(hours)}小时 {int(minutes)}分"
            else:
                return f"{int(hours)}小时 {int(minutes)}分"
        out2 = self.adb_client.shell_sync("uptime", self.serial, timeout=2)
        if "up time:" in out2:
            match = re.search(r"up time:\s*([^,]+)", out2)
            if match:
                return match.group(1).strip()
        return "未知"

    def _get_cpu_info(self) -> str:
        out = self.adb_client.shell_sync("cat /proc/cpuinfo", self.serial)
        for line in out.splitlines():
            if "Hardware" in line:
                return line.split(":")[1].strip()
            if "Processor" in line:
                return line.split(":")[1].strip()
        return "未知"

    def _get_memory_info(self) -> str:
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
        return f"总计 {total_mb} MB, 可用 {avail_mb} MB"

    def _get_storage_info(self) -> str:
        out = self.adb_client.shell_sync("df /data", self.serial, timeout=3)
        if not out:
            return "未知"
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
                    return f"总容量 {size_str}, 已用 {used_str}"
                except ValueError:
                    return f"总容量 {size}, 已用 {used}"
        return "未知"

    def _get_display_detail(self) -> str:
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
        return "\n".join(parts) if parts else "未知"

    # ========== 工具栏操作 ==========

    def toggle_airplane_mode(self, checked):
        """切换飞行模式 (Toggle airplane mode)"""
        if checked:
            self.adb_client.shell_sync("settings put global airplane_mode_on 1", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText("飞行模式已开启")
        else:
            self.adb_client.shell_sync("settings put global airplane_mode_on 0", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText("飞行模式已关闭")
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
        self.status_label.setText(f"屏幕旋转至 {next_rotation}°")

    def take_screenshot(self):
        """截图保存到本地 (Take screenshot and save)"""
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
        self.status_label.setText("就绪")

    def start_recording(self):
        """开始录制屏幕 (Start screen recording)"""
        default_name = f"screen_record_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存录制文件", default_name, "MP4视频 (*.mp4)")
        if not file_path:
            return

        self.raise_()
        self.activateWindow()

        self.recording_file = file_path
        self.recording_remote_path = "/sdcard/temp_record.mp4"
        self.status_label.setText("正在录制...")

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

        self.record_action.setText("停止录制")
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.stop_recording)

    def stop_recording(self):
        """停止录制并拉取文件 (Stop recording and pull file)"""
        if hasattr(self, 'recording_pid') and self.recording_pid:
            self.status_label.setText("正在停止录制...")
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
        out = self.adb_client.shell_sync(f"ls {remote_path}", self.serial)
        return "No such file" not in out and remote_path in out

    def _finish_recording(self):
        self.status_label.setText("正在拉取文件...")
        try:
            self.adb_client.pull_sync(self.recording_remote_path, self.recording_file, self.serial, timeout=60)
            self.adb_client.shell_sync(f"rm {self.recording_remote_path}", self.serial)
            self.status_label.setText(f"录制完成: {self.recording_file}")
            QMessageBox.information(self, "录制成功", f"屏幕录制已保存到:\n{self.recording_file}")
        except Exception as e:
            self.status_label.setText("拉取文件失败")
            QMessageBox.warning(self, "录制失败", f"拉取录制文件失败: {str(e)}")

        self.record_action.setText("开始录制")
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.start_recording)
        self.recording_pid = None

    def reboot_device(self, mode: str = ""):
        """重启设备 (Reboot device)"""
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
        self.status_label.setText("就绪")

    def shutdown_device(self):
        """关闭设备 (Shutdown device)"""
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
        self.status_label.setText("就绪")

    # ========== Root 管理 ==========

    def enable_root(self):
        """尝试以 root 权限重启 adbd (Enable root)"""
        self.status_label.setText("正在提权...")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self._on_root_command_finished)
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "root"])

    def _on_root_command_finished(self, exit_code, exit_status):
        self.status_label.setText("提权命令已发送，等待设备重新连接...")
        QTimer.singleShot(1000, lambda: self._check_root_status(0))
        self.status_label.setText("就绪")

    def _check_root_status(self, retry):
        if retry >= 10:
            self.status_label.setText("提权失败：超时")
            QMessageBox.warning(self, "提权失败", "设备未能在预期时间内切换到 root 模式。")
            return
        out = self.adb_client.shell_sync("id", self.serial, timeout=2)
        if "uid=0" in out:
            self.status_label.setText("提权成功，adbd 已以 root 权限运行")
            QMessageBox.information(self, "提权成功", "adbd 已以 root 权限运行。")
            QTimer.singleShot(1000, self.load_device_info_async)
        else:
            QTimer.singleShot(1000, lambda: self._check_root_status(retry + 1))

    def disable_root(self):
        """解除 root 模式 (Disable root)"""
        self.status_label.setText("正在解除提权...")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self._on_unroot_command_finished)
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "unroot"])

    def _on_unroot_command_finished(self, exit_code, exit_status):
        self.status_label.setText("解提权命令已发送，等待设备重新连接...")
        QTimer.singleShot(1000, lambda: self._check_unroot_status(0))
        self.status_label.setText("就绪")

    def _check_unroot_status(self, retry):
        if retry >= 10:
            self.status_label.setText("解提权失败：超时")
            QMessageBox.warning(self, "解提权失败", "设备未能在预期时间内切换到非 root 模式。")
            return
        out = self.adb_client.shell_sync("id", self.serial, timeout=2)
        if "uid=0" not in out:
            self.status_label.setText("已解除 root 模式")
            QMessageBox.information(self, "解提权成功", "adbd 已恢复为非 root 模式。")
            QTimer.singleShot(1000, self.load_device_info_async)
        else:
            QTimer.singleShot(1000, lambda: self._check_unroot_status(retry + 1))

    def remount_system(self):
        """重新挂载 /system 为可读写 (Remount /system as rw)"""
        out = self.adb_client.shell_sync("id", self.serial)
        if "uid=0" not in out:
            reply = QMessageBox.question(self, "需要 root", "重新挂载 system 需要 root 权限，是否先提权？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.enable_root()
            return
        self.status_label.setText("正在重新挂载 /system ...")
        out = self.adb_client.shell_sync("mount -o remount,rw /system", self.serial)
        if "remount succeeded" in out or "remounted" in out:
            self.status_label.setText("重新挂载成功，/system 现在可读写")
            QMessageBox.information(self, "成功", "/system 已重新挂载为可读写")
        else:
            self.status_label.setText("重新挂载失败")
            QMessageBox.warning(self, "失败", f"重新挂载 /system 失败:\n{out}")

    def show_mounts(self):
        """显示分区挂载信息 (Show mount info)"""
        self.status_label.setText("正在获取分区挂载信息...")
        out = self.adb_client.shell_sync("cat /proc/mounts", self.serial)
        dialog = QDialog(self)
        dialog.setWindowTitle("分区挂载信息")
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(out)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        text_edit.setFont(fixed_font)
        layout.addWidget(text_edit)
        btn = QPushButton("关闭")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        dialog.resize(800, 600)
        dialog.exec_()
        self.status_label.setText("就绪")

    # ========== 沉浸模式 ==========

    def toggle_immersive_status_bar(self, checked):
        self._set_immersive("status", checked)
        self.immersive_status_action.setChecked(checked)

    def toggle_immersive_navigation(self, checked):
        self._set_immersive("navigation", checked)
        self.immersive_nav_action.setChecked(checked)

    def _set_immersive(self, target: str, enable: bool):
        """设置沉浸模式 (Set immersive mode)"""
        if enable:
            cmd = f"settings put global policy_control immersive.{target}=*"
            desc = f"沉浸{'状态栏' if target == 'status' else '导航栏'}已开启"
        else:
            cmd = "settings put global policy_control null*"
            desc = f"沉浸{'状态栏' if target == 'status' else '导航栏'}已关闭"
        self.status_label.setText(f"正在设置{'状态栏' if target == 'status' else '导航栏'}...")
        self.adb_client.shell(cmd, self.serial,
                              callback=lambda code, out, err: self._on_immersive_done(desc))
        self.status_label.setText("就绪")

    def _on_immersive_done(self, desc):
        self.status_label.setText(desc)
        QTimer.singleShot(3000, lambda: self.status_label.setText("就绪"))

    # ========== 其他对话框 ==========

    def open_monkey_dialog(self):
        """打开 Monkey 测试对话框 (Open Monkey test dialog)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QCheckBox
        dialog = QDialog(self)
        dialog.setWindowTitle("Monkey 压力测试")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        self.monkey_package = QLineEdit()
        self.monkey_package.setPlaceholderText("留空则测试所有应用")
        form.addRow("目标包名:", self.monkey_package)
        self.monkey_events = QSpinBox()
        self.monkey_events.setRange(100, 100000)
        self.monkey_events.setValue(1000)
        form.addRow("事件数量:", self.monkey_events)
        self.monkey_throttle = QSpinBox()
        self.monkey_throttle.setRange(0, 1000)
        self.monkey_throttle.setValue(100)
        form.addRow("事件延时(ms):", self.monkey_throttle)
        self.monkey_seed = QSpinBox()
        self.monkey_seed.setRange(1, 10000)
        self.monkey_seed.setValue(1234)
        form.addRow("随机种子:", self.monkey_seed)
        self.monkey_ignore_crashes = QCheckBox("忽略崩溃")
        self.monkey_ignore_crashes.setChecked(True)
        form.addRow("", self.monkey_ignore_crashes)
        self.monkey_ignore_timeouts = QCheckBox("忽略超时")
        self.monkey_ignore_timeouts.setChecked(True)
        form.addRow("", self.monkey_ignore_timeouts)

        layout.addLayout(form)
        self.monkey_log = QTextEdit()
        self.monkey_log.setReadOnly(True)
        layout.addWidget(self.monkey_log)

        btn_box = QDialogButtonBox()
        start_btn = QPushButton("开始测试")
        stop_btn = QPushButton("停止")
        cancel_btn = QPushButton("关闭")
        btn_box.addButton(start_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(stop_btn, QDialogButtonBox.ActionRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        layout.addWidget(btn_box)

        start_btn.clicked.connect(lambda: self.start_monkey_test(dialog))
        stop_btn.clicked.connect(lambda: self.stop_monkey_test())
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec_()

    def start_monkey_test(self, dialog):
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

        self.monkey_log.append(f">>> 开始测试: {' '.join(cmd)}")
        self.monkey_process = QProcess(self)
        self.monkey_process.setProcessChannelMode(QProcess.MergedChannels)
        self.monkey_process.readyReadStandardOutput.connect(lambda: self._on_monkey_output())
        self.monkey_process.finished.connect(self._on_monkey_finished)
        self.monkey_process.start(self.adb_client.adb_path, ["-s", self.serial, "shell"] + cmd)

        dialog.setWindowTitle("Monkey 测试运行中...")
        for child in dialog.findChildren(QPushButton):
            if child.text() == "开始测试":
                child.setEnabled(False)
            elif child.text() == "停止":
                child.setEnabled(True)

    def _on_monkey_output(self):
        data = self.monkey_process.readAllStandardOutput().data()
        text = data.decode('utf-8', errors='ignore')
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(text)

    def _on_monkey_finished(self, exit_code, exit_status):
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(f">>> 测试结束，退出码: {exit_code}")

    def stop_monkey_test(self):
        if hasattr(self, 'monkey_process') and self.monkey_process.state() == QProcess.Running:
            self.monkey_process.kill()
            self.monkey_process.waitForFinished(2000)
            if hasattr(self, 'monkey_log'):
                self.monkey_log.append(">>> 用户手动停止测试")

    def open_tcpdump_dialog(self):
        """打开 tcpdump 抓包对话框 (Open tcpdump dialog)"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QCheckBox
        dialog = QDialog(self)
        dialog.setWindowTitle("tcpdump 抓包")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        form = QFormLayout()
        self.dump_duration = QSpinBox()
        self.dump_duration.setRange(0, 3600)
        self.dump_duration.setValue(30)
        self.dump_duration.setSpecialValueText("无限制")
        form.addRow("持续时间(秒):", self.dump_duration)

        self.dump_count = QSpinBox()
        self.dump_count.setRange(0, 100000)
        self.dump_count.setValue(1000)
        self.dump_count.setSpecialValueText("无限制")
        form.addRow("包数量限制:", self.dump_count)

        self.dump_filter = QLineEdit()
        self.dump_filter.setPlaceholderText("例如: host 192.168.1.1 or port 80")
        form.addRow("过滤表达式:", self.dump_filter)

        self.remote_file = QLineEdit("/sdcard/capture.pcap")
        form.addRow("设备临时文件:", self.remote_file)

        layout.addLayout(form)

        self.dump_log = QTextEdit()
        self.dump_log.setReadOnly(True)
        layout.addWidget(self.dump_log)

        btn_box = QDialogButtonBox()
        start_btn = QPushButton("开始抓包")
        stop_btn = QPushButton("停止")
        save_btn = QPushButton("保存并关闭")
        cancel_btn = QPushButton("取消")
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

        self.dump_log.append(f">>> 开始抓包: {' '.join(cmd)}")
        self.tcpdump_process = QProcess(self)
        self.tcpdump_process.setProcessChannelMode(QProcess.MergedChannels)
        self.tcpdump_process.readyReadStandardOutput.connect(lambda: self._on_tcpdump_output())
        self.tcpdump_process.finished.connect(lambda: self._on_tcpdump_finished(dialog))
        full_cmd = ["-s", self.serial, "shell", "su", "-c"] + cmd
        self.tcpdump_process.start(self.adb_client.adb_path, full_cmd)

        dialog.setWindowTitle("tcpdump 抓包中...")
        for child in dialog.findChildren(QPushButton):
            if child.text() == "开始抓包":
                child.setEnabled(False)
            elif child.text() == "停止":
                child.setEnabled(True)

    def _on_tcpdump_output(self):
        data = self.tcpdump_process.readAllStandardOutput().data()
        text = data.decode('utf-8', errors='ignore')
        if hasattr(self, 'dump_log'):
            self.dump_log.append(text)

    def _on_tcpdump_finished(self, dialog):
        if hasattr(self, 'dump_log'):
            self.dump_log.append(">>> 抓包进程结束")
        for child in dialog.findChildren(QPushButton):
            if child.text() == "开始抓包":
                child.setEnabled(True)
            elif child.text() == "停止":
                child.setEnabled(False)

    def stop_tcpdump(self, dialog):
        if hasattr(self, 'tcpdump_process') and self.tcpdump_process.state() == QProcess.Running:
            self.tcpdump_process.terminate()
            self.tcpdump_process.waitForFinished(2000)
            self.dump_log.append(">>> 用户手动停止抓包")

    def save_tcpdump(self, dialog):
        remote_file = self.remote_file.text().strip()
        local_path, _ = QFileDialog.getSaveFileName(dialog, "保存抓包文件", "capture.pcap", "PCAP文件 (*.pcap)")
        if not local_path:
            return
        self.dump_log.append(f">>> 正在拉取文件: {remote_file} -> {local_path}")
        try:
            self.adb_client.pull_sync(remote_file, local_path, self.serial)
            self.dump_log.append(">>> 拉取成功")
            QMessageBox.information(dialog, "成功", f"抓包文件已保存到:\n{local_path}")
            self.adb_client.shell_sync(f"rm {remote_file}", self.serial)
            dialog.accept()
        except Exception as e:
            self.dump_log.append(f">>> 拉取失败: {str(e)}")
            QMessageBox.warning(dialog, "失败", f"拉取文件失败:\n{str(e)}")

    def open_soft_keyboard(self):
        from ui.soft_keyboard import SoftKeyboardWindow
        dlg = SoftKeyboardWindow(self.serial, self.adb_client, self)
        dlg.exec_()

    def open_broadcast_dialog(self):
        from ui.broadcast_dialog import BroadcastDialog
        dlg = BroadcastDialog(self.serial, self.adb_client, self)
        dlg.exec_()

    # ========== 辅助方法 ==========

    def show_status_message(self, msg: str):
        self.status_label.setText(msg)

    def closeEvent(self, event):
        self.closed.emit(self.serial)
        event.accept()
