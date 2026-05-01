"""
ui/device_window.py - 设备控制窗口
"""

import sys
from datetime import datetime
from typing import Optional

from ui.proxy_tab import ProxyTab
from ui.broadcast_dialog import BroadcastDialog

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QTextEdit, QMessageBox, QProgressBar,
    QStatusBar, QToolBar, QAction, QGroupBox, QFormLayout,
    QLineEdit, QGridLayout, QFileDialog, QFrame, QSizePolicy,
    QShortcut
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QProcess
from PyQt5.QtGui import QIcon, QPixmap, QFont, QKeySequence

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
        self.load_device_info_async()
        self.status_message.connect(self.show_status_message)
        # 以下两个变量原在录制功能中，保留初始化
        self.recording_process = None
        self.recording_file = None
        self.recording_pid = None
        self.setup_shortcuts()

    def init_ui(self):
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
        toolbar = self.addToolBar("设备操作")
        toolbar.setMovable(False)

        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

        # 飞行模式切换
        self.airplane_action = QAction("飞行模式", self)
        self.airplane_action.setCheckable(True)
        self.airplane_action.triggered.connect(self.toggle_airplane_mode)
        toolbar.addAction(self.airplane_action)

        # 旋转屏幕
        self.rotate_action = QAction("旋转屏幕", self)
        self.rotate_action.triggered.connect(self.rotate_screen)
        toolbar.addAction(self.rotate_action)

        # 录制按钮
        self.record_action = QAction("开始录制", self)
        self.record_action.triggered.connect(self.start_recording)
        toolbar.addAction(self.record_action)

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
        root_action = QAction("提权 (root)", self)
        root_action.triggered.connect(self.enable_root)
        toolbar.addAction(root_action)
        unroot_action = QAction("解提权 (unroot)", self)
        unroot_action.triggered.connect(self.disable_root)
        toolbar.addAction(unroot_action)

        # 重新挂载 system (需要root)
        self.remount_action = QAction("重新挂载 system", self)
        self.remount_action.triggered.connect(self.remount_system)
        toolbar.addAction(self.remount_action)

        # 查看分区挂载
        self.mounts_action = QAction("查看分区挂载", self)
        self.mounts_action.triggered.connect(self.show_mounts)
        toolbar.addAction(self.mounts_action)

        toolbar.addSeparator()

        refresh_action = QAction("刷新信息", self)
        refresh_action.triggered.connect(self.load_device_info_async)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        monkey_action = QAction("Monkey测试", self)
        monkey_action.triggered.connect(self.open_monkey_dialog)
        toolbar.addAction(monkey_action)

        toolbar.addSeparator()
        tcpdump_action = QAction("tcpdump抓包", self)
        tcpdump_action.triggered.connect(self.open_tcpdump_dialog)
        toolbar.addAction(tcpdump_action)
        
        toolbar.addSeparator()
        keyboard_action = QAction("软键盘", self)
        keyboard_action.triggered.connect(self.open_soft_keyboard)
        toolbar.addAction(keyboard_action)

        toolbar.addSeparator()
        broadcast_action = QAction("发送广播", self)
        broadcast_action.triggered.connect(self.open_broadcast_dialog)
        toolbar.addAction(broadcast_action)

        toolbar.addSeparator()
        self.immersive_status_action = QAction("沉浸状态栏", self, checkable=True)
        self.immersive_status_action.triggered.connect(self.toggle_immersive_status_bar)
        toolbar.addAction(self.immersive_status_action)

        self.immersive_nav_action = QAction("沉浸导航栏", self, checkable=True)
        self.immersive_nav_action.triggered.connect(self.toggle_immersive_navigation)
        toolbar.addAction(self.immersive_nav_action)

    def init_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def show_status_message(self, msg: str):
        self.status_label.setText(msg)

    def setup_shortcuts(self):
        import platform
        defaults = {
            "close": "Ctrl+W",
            "screenshot": "Ctrl+Shift+S",
            "refresh_info": "F5",
            "recording": "Ctrl+Shift+R",
        }
        # 清除已有快捷键
        if hasattr(self, '_shortcuts_list'):
            for sc in self._shortcuts_list:
                sc.setEnabled(False)
                sc.deleteLater()
        self._shortcuts_list = []
        # 读取配置
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
        """根据当前状态切换录制"""
        if hasattr(self, 'recording_proc') and self.recording_proc is not None:
            self.stop_recording()
        else:
            self.start_recording()

    def create_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        def make_label(text="未知", align_left=False):
            label = QLabel(text)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            if align_left:
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return label

        # ---------- 基本信息 ----------
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

        # ---------- 硬件信息（限制最大高度，禁止拉伸）----------
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
        self.imei_label = make_label(align_left=True)
        self.mac_label = make_label(align_left=True)
        self.bluetooth_label = make_label(align_left=True)
        self.network_label = make_label(align_left=True)
        self.uptime_label = make_label(align_left=True)
        self.cpu_label = make_label(align_left=True)

        # what can i say
        # 内存信息 - 无边框文本框，防止截断
        self.memory_label = QTextEdit()
        self.memory_label.setReadOnly(True)
        self.memory_label.setStyleSheet("background: transparent; border: none;")
        self.memory_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.memory_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.memory_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.memory_label.setFixedHeight(24)   # 单行高度
        self.memory_label.document().setDocumentMargin(0)
        from PyQt5.QtGui import QTextOption
        self.memory_label.setWordWrapMode(QTextOption.WrapAnywhere)

        # 存储信息 - 无边框文本框
        self.storage_label = QTextEdit()
        self.storage_label.setReadOnly(True)
        self.storage_label.setStyleSheet("background: transparent; border: none;")
        self.storage_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.storage_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.storage_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.storage_label.setFixedHeight(24)
        self.storage_label.document().setDocumentMargin(0)
        self.storage_label.setWordWrapMode(QTextOption.WrapAnywhere)

        self.display_detail_label = QTextEdit()
        self.display_detail_label.setReadOnly(True)
        self.display_detail_label.setStyleSheet("background: transparent; border: none;")
        self.display_detail_label.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.display_detail_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.display_detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.display_detail_label.setMinimumWidth(0)
        self.display_detail_label.document().setDocumentMargin(0)
        from PyQt5.QtGui import QTextOption, QFontDatabase
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
        hardware_group.setMaximumHeight(400)          # ★ 关键：阻止硬件组垂直拉伸
        layout.addWidget(hardware_group, 0)

        # ---------- 详细属性（允许拉伸）----------
        detail_group = QGroupBox("详细属性 (getprop)")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group, 1)             # 占据所有剩余空间

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
        proxy = ProxyTab(self.serial, self.adb_client)
        return proxy

    def load_device_info_async(self):
        """异步加载设备信息，逐步更新UI，避免卡顿"""
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
            ("IMEI", lambda: self._get_imei(),
             lambda val: self.imei_label.setText(val)),
            ("MAC地址", lambda: self._get_mac_address(),
             lambda val: self.mac_label.setText(val)),
            ("蓝牙地址", lambda: self._get_bluetooth_address(),
             lambda val: self.bluetooth_label.setText(val)),
            ("网络状态", lambda: self._get_network_status(),
             lambda val: self.network_label.setText(val)),
            ("开机时间", lambda: self._get_uptime(),
             lambda val: self.uptime_label.setText(val)),
            ("CPU信息", lambda: self._get_cpu_info(),
             lambda val: self.cpu_label.setText(val)),
            ("内存信息", lambda: self._get_memory_info(),
             lambda val: self.memory_label.setPlainText(val)),
            ("存储信息", lambda: self._get_storage_info(),
             lambda val: self.storage_label.setPlainText(val)),
            ("显示屏详情", lambda: self._get_display_detail(),
             lambda val: self.display_detail_label.setText(val)),
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
            res = output.split(":")[1].strip()
            self.resolution_label.setText(res)
        else:
            self.resolution_label.setText("未知")

    def _get_imei(self) -> str:
        # 尝试多种方式获取 IMEI，按成功率排序
        # 方法1：dumpsys iphonesubinfo（Android 8+）
        out = self.adb_client.shell_sync("dumpsys iphonesubinfo", self.serial, timeout=5)
        if out:
            for line in out.splitlines():
                if "Device ID" in line or "IMEI" in line:
                    parts = line.split("=")
                    if len(parts) > 1:
                        return parts[1].strip()
        # 方法2：service call iphonesubinfo 1（需 root 或系统权限）
        out2 = self.adb_client.shell_sync("service call iphonesubinfo 1", self.serial, timeout=5)
        if out2 and "Result" in out2:
            # 简单提取十六进制数字串
            import re
            nums = re.findall(r"'([0-9A-F\s]+)'", out2)
            if nums:
                clean = nums[0].replace(" ", "").strip().lower()
                if clean and clean != "0":
                    # 将十六进制转换为可见字符（可能包含数字）
                    try:
                        return bytes.fromhex(clean).decode("ascii", errors="ignore")
                    except:
                        pass
        # 方法3：需要 root，读取系统文件
        out3 = self.adb_client.shell_sync("cat /proc/imei 2>/dev/null", self.serial, timeout=2)
        if out3 and "error" not in out3.lower():
            return out3.strip()
        out4 = self.adb_client.shell_sync("su -c 'cat /proc/imei' 2>/dev/null", self.serial, timeout=2)
        if out4 and "error" not in out4.lower() and out4.strip():
            return out4.strip()
        return "需权限/不可用"

    def _get_mac_address(self) -> str:
        # 遍历 /sys/class/net 下接口
        out = self.adb_client.shell_sync("for iface in /sys/class/net/*/address; do [ -f $iface ] && addr=$(cat $iface) && [ -n $addr ] && [ $addr != '00:00:00:00:00:00' ] && iface_name=$(dirname $iface | xargs basename) && [ $iface_name != 'lo' ] && echo $iface_name $addr; done", self.serial, timeout=3)
        if out.strip():
            # 取第一个非 loopback 接口
            lines = out.strip().splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    name, addr = parts[0], parts[1]
                    if ":" in addr and name not in ("lo",):
                        return addr
        # 备选：ip link
        out2 = self.adb_client.shell_sync("ip link show", self.serial, timeout=3)
        if out2:
            import re
            # 匹配格式: 3: wlan0: <...> ... link/ether xx:xx:xx:xx:xx:xx
            for m in re.finditer(r"link/ether\s+([0-9a-fA-F:]{17})", out2):
                return m.group(1)
        return "未知"

    def _get_bluetooth_address(self) -> str:
        # 方法1：settings get secure bluetooth_address
        out = self.adb_client.shell_sync("settings get secure bluetooth_address", self.serial, timeout=3)
        if out.strip() and ":" in out.strip():
            return out.strip()
        # 方法2：dumpsys bluetooth_manager
        out2 = self.adb_client.shell_sync("dumpsys bluetooth_manager | grep 'Address'", self.serial, timeout=3)
        if out2:
            # 提取类似 "Address: XX:XX:XX:XX:XX:XX"
            import re
            m = re.search(r"([0-9A-Fa-f:]{17})", out2)
            if m:
                return m.group(1)
        # 方法3：需要 root 读配置文件
        out3 = self.adb_client.shell_sync("cat /data/misc/bluetooth/bt_config.conf 2>/dev/null | grep 'Address'", self.serial, timeout=2)
        if out3:
            import re
            m = re.search(r"([0-9A-Fa-f:]{17})", out3)
            if m:
                return m.group(1)
        return "未知"

    def _get_network_status(self) -> str:
        # 简单判断是否连接 WiFi
        out = self.adb_client.shell_sync("dumpsys connectivity | grep -A 5 'NetworkAgentInfo'", self.serial)
        if "WIFI" in out and "CONNECTED" in out:
            return "WiFi 已连接"
        elif "CELLULAR" in out and "CONNECTED" in out:
            return "移动网络已连接"
        else:
            return "无网络连接"

    def _get_uptime(self) -> str:
        # 读取 /proc/uptime 获取秒数，避免 uptime 命令解析问题
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
        # 回退 uptime
        out2 = self.adb_client.shell_sync("uptime", self.serial, timeout=2)
        if "up time:" in out2:
            import re
            match = re.search(r"up time:\s*([^,]+)", out2)
            if match:
                return match.group(1).strip()
        return "未知"

    def _get_cpu_info(self) -> str:
        out = self.adb_client.shell_sync("cat /proc/cpuinfo", self.serial)
        lines = out.splitlines()
        for line in lines:
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

        avail_mb = "?"  # 默认值
        # 优先使用 MemAvailable
        if "MemAvailable" in mem_data:
            avail = mem_data["MemAvailable"].split()[0]
            if avail.isdigit():
                avail_mb = int(avail) // 1024
        else:
            # 计算近似可用内存：MemFree + Buffers + Cached
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
            parts = lines[1].split()   # 第二行：数据行
            if len(parts) >= 3:
                size = parts[1]        # 第一列是文件系统，第二列 Size
                used = parts[2]        # 第三列 Used
                # 转换为可读格式（KB -> MB 或 GB）
                try:
                    size_int = int(size)
                    used_int = int(used)
                    if size_int >= 1048576:
                        size_str = f"{size_int / 1048576:.1f} GB"
                    else:
                        size_str = f"{size_int / 1024:.1f} MB"
                    if used_int >= 1048576:
                        used_str = f"{used_int / 1048576:.1f} GB"
                    else:
                        used_str = f"{used_int / 1024:.1f} MB"
                    return f"总容量 {size_str}, 已用 {used_str}"
                except ValueError:
                    return f"总容量 {size}, 已用 {used}"
        return "未知"

    def _get_display_detail(self) -> str:
        # 返回所有匹配行，不截断，依赖文本框自动换行和滚动
        out = self.adb_client.shell_sync("dumpsys display | grep -E 'mDisplayInfo|DisplayDeviceInfo|PhysicalDisplayInfo'", self.serial, timeout=3)
        if out.strip():
            return out.strip()
        # 回退方案
        size = self.adb_client.shell_sync("wm size", self.serial, timeout=2).strip()
        density = self.adb_client.shell_sync("wm density", self.serial, timeout=2).strip()
        parts = []
        if "Physical size" in size:
            parts.append(size.split(":")[-1].strip())
        if "Physical density" in density:
            parts.append(density.split(":")[-1].strip())
        return "\n".join(parts) if parts else "未知"

    def create_process_manager_tab(self) -> QWidget:
        from ui.process_manager import ProcessManager
        pm = ProcessManager(self.serial, self.adb_client)
        pm.status_message.connect(self.show_status_message)
        return pm

    #    def _on_model_loaded(self, model: str):
    #        print(f"_on_model_loaded: '{model}'")
    #        self.model_label.setText(model if model else "未知")

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

    def toggle_airplane_mode(self, checked):
        """切换飞行模式"""
        if checked:
            self.adb_client.shell_sync("settings put global airplane_mode_on 1", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText("飞行模式已开启")
        else:
            self.adb_client.shell_sync("settings put global airplane_mode_on 0", self.serial)
            self.adb_client.shell_sync("am broadcast -a android.intent.action.AIRPLANE_MODE", self.serial)
            self.status_label.setText("飞行模式已关闭")
        # 刷新按钮状态（可选）
        self.airplane_action.setChecked(checked)

    def rotate_screen(self):
        """旋转屏幕（0, 90, 180, 270）轮换"""
        # 获取当前旋转角度
        out = self.adb_client.shell_sync("settings get system user_rotation", self.serial)
        try:
            current = int(out.strip())
        except:
            current = 0
        next_rotation = (current + 90) % 360
        self.adb_client.shell_sync(f"settings put system user_rotation {next_rotation//90}", self.serial)
        self.status_label.setText(f"屏幕旋转至 {next_rotation}°")

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
        self.status_label.setText("就绪")

    def start_recording(self):
        from PyQt5.QtWidgets import QFileDialog
        # 保存当前窗口引用
        current_window = self
        default_name = f"screen_record_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存录制文件", default_name, "MP4视频 (*.mp4)")
        if not file_path:
            return
        
        # 重新激活当前窗口
        current_window.raise_()
        current_window.activateWindow()
        
        self.recording_file = file_path
        self.recording_remote_path = "/sdcard/temp_record.mp4"
        self.status_label.setText("正在录制...")
        
        # 删除可能存在的旧文件
        self.adb_client.shell_sync(f"rm {self.recording_remote_path}", self.serial)
        
        # 使用 subprocess.Popen 异步启动 screenrecord，不等待完成
        import subprocess
        self.recording_proc = subprocess.Popen(
            [self.adb_client.adb_path, "-s", self.serial, "shell", "screenrecord", self.recording_remote_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # 等待一秒让进程启动
        import time
        time.sleep(1)
        
        # 获取 screenrecord 的 PID
        pid_out = self.adb_client.shell_sync("pgrep screenrecord", self.serial)
        try:
            self.recording_pid = int(pid_out.strip())
        except:
            self.recording_pid = None
        
        # 修改按钮状态
        self.record_action.setText("停止录制")
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.stop_recording)

    def stop_recording(self):
        if hasattr(self, 'recording_pid') and self.recording_pid:
            self.status_label.setText("正在停止录制...")
            # 发送 SIGINT 信号
            self.adb_client.shell_sync(f"kill -2 {self.recording_pid}", self.serial)
            # 等待文件生成（最多5秒）
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
        
        # 恢复按钮状态
        self.record_action.setText("开始录制")
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.start_recording)
        self.recording_pid = None

    def _on_recording_output(self):
        data = self.recording_process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        if data:
            print(f"[Recording] stdout: {data}")


    def _on_recording_error(self):
        """录制过程中的错误输出"""
        err = self.recording_process.readAllStandardError().data().decode('utf-8', errors='ignore')
        if "WARNING" in err:
            # 忽略警告（如设备不支持某些功能）
            pass
        else:
            print(f"[Recording] stderr: {err}")

        #    def _on_recording_finished(self, exit_code, exit_status):
        #        """录制完成，拉取文件到本地"""
        #        if exit_code == 0:
        #            self.status_label.setText("录制完成，正在拉取文件...")
        #            # 拉取录制的文件
        #            self.adb_client.pull_sync(self.recording_remote_path, self.recording_file, self.serial, timeout=60)
        #            # 删除设备上的临时文件
        #            self.adb_client.shell_sync(f"rm {self.recording_remote_path}", self.serial)
        #            self.status_label.setText(f"录制完成: {self.recording_file}")
        #            QMessageBox.information(self, "录制成功", f"屏幕录制已保存到:\n{self.recording_file}")
        #        else:
        #            self.status_label.setText("录制失败")
        #            QMessageBox.warning(self, "录制失败", "屏幕录制失败，请检查设备是否支持 screenrecord 命令。")
        
        # 恢复按钮状态
        self.record_action.setText("开始录制")
        self.record_action.triggered.disconnect()
        self.record_action.triggered.connect(self.start_recording)
        self.recording_process = None

    def open_monkey_dialog(self):
        """打开 Monkey 测试设置对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QPushButton, QDialogButtonBox, QTextEdit, QCheckBox
        dialog = QDialog(self)
        dialog.setWindowTitle("Monkey 压力测试")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        # 包名输入（可选，留空则测试所有应用）
        self.monkey_package = QLineEdit()
        self.monkey_package.setPlaceholderText("留空则测试所有应用")
        form.addRow("目标包名:", self.monkey_package)
        # 事件数量
        self.monkey_events = QSpinBox()
        self.monkey_events.setRange(100, 100000)
        self.monkey_events.setValue(1000)
        form.addRow("事件数量:", self.monkey_events)
        # 延时（毫秒）
        self.monkey_throttle = QSpinBox()
        self.monkey_throttle.setRange(0, 1000)
        self.monkey_throttle.setValue(100)
        form.addRow("事件延时(ms):", self.monkey_throttle)
        # 随机种子
        self.monkey_seed = QSpinBox()
        self.monkey_seed.setRange(1, 10000)
        self.monkey_seed.setValue(1234)
        form.addRow("随机种子:", self.monkey_seed)
        # 是否忽略崩溃
        self.monkey_ignore_crashes = QCheckBox("忽略崩溃")
        self.monkey_ignore_crashes.setChecked(True)
        form.addRow("", self.monkey_ignore_crashes)
        # 是否忽略超时
        self.monkey_ignore_timeouts = QCheckBox("忽略超时")
        self.monkey_ignore_timeouts.setChecked(True)
        form.addRow("", self.monkey_ignore_timeouts)
        
        layout.addLayout(form)
        
        # 日志输出区域
        self.monkey_log = QTextEdit()
        self.monkey_log.setReadOnly(True)
        layout.addWidget(self.monkey_log)
        
        # 按钮
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
        """启动 monkey 测试进程，并实时显示日志"""
        pkg = self.monkey_package.text().strip()
        events = self.monkey_events.value()
        throttle = self.monkey_throttle.value()
        seed = self.monkey_seed.value()
        ignore_crashes = self.monkey_ignore_crashes.isChecked()
        ignore_timeouts = self.monkey_ignore_timeouts.isChecked()
        
        # 构建 monkey 命令
        cmd = ["monkey"]
        if pkg:
            cmd.extend(["-p", pkg])
        cmd.extend(["-v", "-v", "-v"])  # 详细日志级别
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
        # 禁用开始按钮，启用停止按钮
        for child in dialog.findChildren(QPushButton):
            if child.text() == "开始测试":
                child.setEnabled(False)
            elif child.text() == "停止":
                child.setEnabled(True)

    def _on_monkey_output(self):
        """读取 monkey 输出并显示"""
        data = self.monkey_process.readAllStandardOutput().data()
        text = data.decode('utf-8', errors='ignore')
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(text)

    def _on_monkey_finished(self, exit_code, exit_status):
        """monkey 测试结束"""
        if hasattr(self, 'monkey_log'):
            self.monkey_log.append(f">>> 测试结束，退出码: {exit_code}")
            # 重新启用对话框中的开始按钮（需要找到对话框实例，简化处理：关闭对话框时重新创建）
            # 这里我们不需要动态查找，因为对话框会自己处理

    def stop_monkey_test(self):
        """停止 monkey 测试"""
        if hasattr(self, 'monkey_process') and self.monkey_process.state() == QProcess.Running:
            self.monkey_process.kill()
            self.monkey_process.waitForFinished(2000)
            if hasattr(self, 'monkey_log'):
                self.monkey_log.append(">>> 用户手动停止测试")

    def reboot_device(self, mode: str = ""):
        mode_text = {"": "重启", "recovery": "重启到 Recovery", "bootloader": "重启到 Bootloader"}.get(mode, "重启")
        reply = QMessageBox.question(self, "确认操作", f"确定要{mode_text}设备 {self.serial} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText(f"正在{mode_text}...")
            self.adb_client.reboot(self.serial, mode,callback=lambda code, out, err: self._on_reboot_finished(code, mode_text))

    def _on_reboot_finished(self, exit_code, mode_text):
        if exit_code == 0:
            self.status_label.setText(f"{mode_text}命令已发送")
            QMessageBox.information(self, "操作成功", f"{mode_text}命令已发送，设备将开始重启。")
        else:
            self.status_label.setText(f"{mode_text}失败")
            QMessageBox.warning(self, "错误", f"{mode_text}失败，请检查设备连接。")
        self.status_label.setText("就绪")

    def shutdown_device(self):
        reply = QMessageBox.question(self, "确认操作", f"确定要关闭设备 {self.serial} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.status_label.setText("正在关机...")
            self.adb_client.shell("reboot -p", self.serial,callback=lambda code, out, err: self._on_shutdown_finished(code))

    def _on_shutdown_finished(self, exit_code):
        if exit_code == 0:
            self.status_label.setText("关机命令已发送")
            QMessageBox.information(self, "操作成功", "关机命令已发送，设备将关闭。")
        else:
            self.status_label.setText("关机失败")
            QMessageBox.warning(self, "错误", "关机失败，请检查设备权限。")
        self.status_label.setText("就绪")

    def closeEvent(self, event):
        self.closed.emit(self.serial)
        event.accept()
    #    def enable_root(self):
    #        """尝试以 root 权限重启 adbd"""
    #        self.status_label.setText("正在提权...")
    #        # 直接在主机端执行 adb root
    #        proc = QProcess(self)
    #        proc.setProcessChannelMode(QProcess.MergedChannels)
    #        proc.finished.connect(lambda code, exit_status: self._on_root_finished(code, exit_status, proc))
    #        proc.start(self.adb_client.adb_path, ["-s", self.serial, "root"])
    #
    #    def _on_root_finished(self, exit_code, exit_status, proc):
    #        output = proc.readAllStandardOutput().data().decode('utf-8', errors='ignore')
    #        output_lower = output.lower()
    #        # 只要输出包含成功或已存在的提示，就认为提权成功或已处于 root 状态
    #        if "restarting adbd as root" in output_lower or "already running as root" in output_lower:
    #            if "already running as root" in output_lower:
    #                self.status_label.setText("已经是 root 模式")
    #                QMessageBox.information(self, "提权提示", "adbd 已经以 root 权限运行。")
    #            else:
    #                self.status_label.setText("提权成功，adbd 已重启为 root 模式")
    #                QMessageBox.information(self, "提权成功", "adbd 已以 root 权限运行。\n注意：设备可能短暂断开后重连。")
    #            QTimer.singleShot(2000, self.load_device_info_async)
    #        else:
    #            self.status_label.setText("提权失败")
    #            QMessageBox.warning(self, "提权失败", f"设备不支持 adb root 或操作失败:\n{output}")
    #
    #    def disable_root(self):
    #        """恢复 adbd 为非 root 模式"""
    #        self.status_label.setText("正在解除提权...")
    #        proc = QProcess(self)
    #        proc.setProcessChannelMode(QProcess.MergedChannels)
    #        proc.finished.connect(lambda code, exit_status: self._on_unroot_finished(code, exit_status, proc))
    #        proc.start(self.adb_client.adb_path, ["-s", self.serial, "unroot"])
    #
    #    def _on_unroot_finished(self, exit_code, exit_status, proc):
    #        output = proc.readAllStandardOutput().data().decode('utf-8', errors='ignore')
    #        output_lower = output.lower()
    #        if exit_code == 0 and ("restarting adbd as non root" in output_lower or "already running as non root" in output_lower):
    #            if "already running as non root" in output_lower:
    #                self.status_label.setText("已经是非 root 模式")
    #                QMessageBox.information(self, "解提权提示", "adbd 已经以非 root 权限运行。")
    #            else:
    #                self.status_label.setText("已解除 root 模式")
    #                QMessageBox.information(self, "解提权成功", "adbd 已恢复为非 root 模式。")
    #            QTimer.singleShot(2000, self.load_device_info_async)
    #        else:
    #            self.status_label.setText("解提权失败")
    #            QMessageBox.warning(self, "解提权失败", output)
    def enable_root(self):
        """尝试以 root 权限重启 adbd"""
        self.status_label.setText("正在提权...")
        # 先执行 adb root
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self._on_root_command_finished)
        proc.start(self.adb_client.adb_path, ["-s", self.serial, "root"])

    def _on_root_command_finished(self, exit_code, exit_status):
        """adb root 命令执行完成，开始轮询检查是否真正成为 root"""
        self.status_label.setText("提权命令已发送，等待设备重新连接...")
        QTimer.singleShot(1000, lambda: self._check_root_status(0))
        self.status_label.setText("就绪")

    def _check_root_status(self, retry):
        """检查设备是否已处于 root 状态，最多重试 10 次"""
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
        """恢复 adbd 为非 root 模式"""
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

    def open_tcpdump_dialog(self):
        """打开 tcpdump 抓包设置对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QPushButton, QDialogButtonBox, QTextEdit, QCheckBox, QFileDialog
        
        dialog = QDialog(self)
        dialog.setWindowTitle("tcpdump 抓包")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        # 抓包时长（秒），0 表示无限制（需要手动停止）
        self.dump_duration = QSpinBox()
        self.dump_duration.setRange(0, 3600)
        self.dump_duration.setValue(30)
        self.dump_duration.setSpecialValueText("无限制")
        form.addRow("持续时间(秒):", self.dump_duration)
        
        # 包数量限制
        self.dump_count = QSpinBox()
        self.dump_count.setRange(0, 100000)
        self.dump_count.setValue(1000)
        self.dump_count.setSpecialValueText("无限制")
        form.addRow("包数量限制:", self.dump_count)
        
        # 过滤表达式
        self.dump_filter = QLineEdit()
        self.dump_filter.setPlaceholderText("例如: host 192.168.1.1 or port 80")
        form.addRow("过滤表达式:", self.dump_filter)
        
        # 输出文件名（设备上的临时文件）
        self.remote_file = QLineEdit("/sdcard/capture.pcap")
        form.addRow("设备临时文件:", self.remote_file)
        
        layout.addLayout(form)
        
        # 日志输出
        self.dump_log = QTextEdit()
        self.dump_log.setReadOnly(True)
        layout.addWidget(self.dump_log)
        
        # 按钮
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
        """启动 tcpdump 进程"""
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
            cmd.extend([filter_exp])  # 注意：tcpdump 过滤器需要放在最后
        
        self.dump_log.append(f">>> 开始抓包: {' '.join(cmd)}")
        self.tcpdump_process = QProcess(self)
        self.tcpdump_process.setProcessChannelMode(QProcess.MergedChannels)
        self.tcpdump_process.readyReadStandardOutput.connect(lambda: self._on_tcpdump_output())
        self.tcpdump_process.finished.connect(lambda: self._on_tcpdump_finished(dialog))
        # 在设备上执行，需要 root 权限
        full_cmd = ["-s", self.serial, "shell", "su", "-c"] + cmd
        self.tcpdump_process.start(self.adb_client.adb_path, full_cmd)
        
        dialog.setWindowTitle("tcpdump 抓包中...")
        # 禁用开始按钮，启用停止按钮
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
        # 恢复按钮状态
        for child in dialog.findChildren(QPushButton):
            if child.text() == "开始抓包":
                child.setEnabled(True)
            elif child.text() == "停止":
                child.setEnabled(False)

    def stop_tcpdump(self, dialog):
        """停止 tcpdump 进程"""
        if hasattr(self, 'tcpdump_process') and self.tcpdump_process.state() == QProcess.Running:
            self.tcpdump_process.terminate()
            self.tcpdump_process.waitForFinished(2000)
            self.dump_log.append(">>> 用户手动停止抓包")

    def save_tcpdump(self, dialog):
        """将设备上的 pcap 文件拉取到本地"""
        remote_file = self.remote_file.text().strip()
        local_path, _ = QFileDialog.getSaveFileName(dialog, "保存抓包文件", "capture.pcap", "PCAP文件 (*.pcap)")
        if not local_path:
            return
        self.dump_log.append(f">>> 正在拉取文件: {remote_file} -> {local_path}")
        try:
            self.adb_client.pull_sync(remote_file, local_path, self.serial)
            self.dump_log.append(">>> 拉取成功")
            QMessageBox.information(dialog, "成功", f"抓包文件已保存到:\n{local_path}")
            # 可选：删除设备上的临时文件
            self.adb_client.shell_sync(f"rm {remote_file}", self.serial)
            dialog.accept()
        except Exception as e:
            self.dump_log.append(f">>> 拉取失败: {str(e)}")
            QMessageBox.warning(dialog, "失败", f"拉取文件失败:\n{str(e)}")

    def create_terminal_tab(self) -> QWidget:
        from ui.terminal import TerminalWidget
        terminal = TerminalWidget(self.serial, self.adb_client)
        terminal.status_message.connect(self.show_status_message)
        return terminal

    def open_soft_keyboard(self):
        from ui.soft_keyboard import SoftKeyboardWindow
        dlg = SoftKeyboardWindow(self.serial, self.adb_client, self)
        dlg.exec_()

    def remount_system(self):
        """重新挂载 /system 分区为可读写（需要 root）"""
        # 检查是否有 root 权限
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
        """显示分区挂载信息"""
        self.status_label.setText("正在获取分区挂载信息...")
        out = self.adb_client.shell_sync("cat /proc/mounts", self.serial)
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        from PyQt5.QtGui import QFontDatabase
        dialog = QDialog(self)
        dialog.setWindowTitle("分区挂载信息")
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(out)
        # 使用系统等宽字体
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        text_edit.setFont(fixed_font)
        layout.addWidget(text_edit)
        btn = QPushButton("关闭")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        dialog.resize(800, 600)
        dialog.exec_()
        self.status_label.setText("就绪")

    def toggle_immersive_status_bar(self, checked):
        self._set_immersive("status", checked)
        self.immersive_status_action.setChecked(checked)

    def toggle_immersive_navigation(self, checked):
        self._set_immersive("navigation", checked)
        self.immersive_nav_action.setChecked(checked)

    def _set_immersive(self, target: str, enable: bool):
        """target: 'status' 或 'navigation'"""
        if enable:
            cmd = f"settings put global policy_control immersive.{target}=*"
            desc = f"沉浸{ '状态栏' if target == 'status' else '导航栏' }已开启"
        else:
            cmd = "settings put global policy_control null*"
            desc = f"沉浸{ '状态栏' if target == 'status' else '导航栏' }已关闭"
        self.status_label.setText(f"正在设置{ '状态栏' if target == 'status' else '导航栏' }...")
        self.adb_client.shell(cmd, self.serial,
                              callback=lambda code, out, err: self._on_immersive_done(desc))
        self.status_label.setText("就绪")

    def _on_immersive_done(self, desc):
        self.status_label.setText(desc)
        QTimer.singleShot(3000, lambda: self.status_label.setText("就绪"))

    def open_broadcast_dialog(self):
        dlg = BroadcastDialog(self.serial, self.adb_client, self)
        dlg.exec_()
