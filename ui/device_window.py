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
        self.load_device_info_async()
        self.status_message.connect(self.show_status_message)
        self.load_device_info_async()
        self.recording_process = None  # 录制进程
        self.recording_file = None     # 录制文件路径
        self.recording_pid = None

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        #uni style
        #        self.tab_widget.setDocumentMode(True)
        #        self.tab_widget.setStyleSheet("""
        #            QTabBar::tab {
        #                padding: 6px 12px;
        #                margin: 2px;
        #            }
        #            QTabBar::tab:selected {
        #                background: palette(highlight);
        #                color: palette(highlighted-text);
        #            }
        #        """)

        self.info_tab = self.create_info_tab()
        self.tab_widget.addTab(self.info_tab, "设备信息")

        self.apps_tab = self.create_apps_tab()
        self.tab_widget.addTab(self.apps_tab, "应用管理")

        self.file_tab = self.create_file_manager_tab()
        self.tab_widget.addTab(self.file_tab, "文件管理")

        #        self.log_tab = self.create_placeholder_tab("日志查看\n(待实现)")
        #        self.tab_widget.addTab(self.log_tab, "日志")
        self.log_tab = self.create_log_tab()
        self.tab_widget.addTab(self.log_tab, "日志")

        self.advanced_tab = self.create_process_manager_tab()
        self.tab_widget.addTab(self.advanced_tab, "进程管理")

    def init_toolbar(self):
        toolbar = self.addToolBar("设备操作")
        toolbar.setMovable(False)

        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(self.take_screenshot)
        toolbar.addAction(screenshot_action)

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

        refresh_action = QAction("刷新信息", self)
        #refresh_action.triggered.connect(self.load_device_info)
        refresh_action.triggered.connect(self.load_device_info_async)
        toolbar.addAction(refresh_action)
        
        # 在 shutdown_action 后面或工具栏末尾添加
        toolbar.addSeparator()
        monkey_action = QAction("Monkey测试", self)
        monkey_action.triggered.connect(self.open_monkey_dialog)
        toolbar.addAction(monkey_action)

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

    def load_device_info_async(self):
        """异步加载设备信息，逐步更新UI，避免卡顿"""
        self.status_label.setText("正在获取设备信息...")
        if hasattr(self, '_loading') and self._loading:
            return
        self._loading = True
        
        # 定义任务列表：每个任务包含 (描述, 获取函数, 更新UI的lambda)
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
             lambda val: self.memory_label.setText(val)),
            ("存储信息", lambda: self._get_storage_info(),
             lambda val: self.storage_label.setText(val)),
            ("显示屏详情", lambda: self._get_display_detail(),
             lambda val: self.display_detail_label.setText(val)),
            ("详细属性", lambda: self.adb_client.shell_sync("getprop", self.serial, timeout=8),
             lambda out: self.detail_text.setText(out)),
        ]
        
        self._task_index = 0
        self._tasks = tasks
        self._run_next_task()

    def create_log_tab(self) -> QWidget:
        from ui.logcat_tab import LogcatTab
        return LogcatTab(self.serial, self.adb_client)

    def _run_next_task(self):
        """执行下一个任务，使用 QTimer 避免阻塞"""
        if self._task_index >= len(self._tasks):
            self.status_label.setText("设备信息已更新")
            return
        desc, func, update_ui = self._tasks[self._task_index]
        self.status_label.setText(f"正在获取 {desc}...")
        # 在单独的线程中执行同步命令？为了简单，仍用同步但通过 QTimer 延迟执行
        # 注意：同步命令仍会短暂阻塞，但每个命令很快，且 UI 会在间隙刷新
        try:
            result = func()
            update_ui(result)
        except Exception as e:
            print(f"获取 {desc} 失败: {e}")
            update_ui("获取失败")
        self._task_index += 1
        # 延迟 10ms 执行下一个任务，让 UI 有机会刷新
        from PyQt5.QtCore import QTimer
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
        # 方法1：通过 service call
        out = self.adb_client.shell_sync("service call iphonesubinfo 1", self.serial)
        # 解析输出中的数字，简单提取（较复杂，先尝试另一种）
        # 方法2：dumpsys iphonesubinfo
        out2 = self.adb_client.shell_sync("dumpsys iphonesubinfo | grep 'Device ID'", self.serial)
        if "Device ID" in out2:
            parts = out2.split("=")
            if len(parts) > 1:
                return parts[1].strip()
        # 方法3：读取 /proc/imei（需要root）
        return "未获取到"

    def _get_mac_address(self) -> str:
        out = self.adb_client.shell_sync("cat /sys/class/net/wlan0/address", self.serial)
        if out and ":" in out:
            return out.strip()
        out2 = self.adb_client.shell_sync("ip link show wlan0 | grep ether", self.serial)
        if "ether" in out2:
            parts = out2.split()
            for i, p in enumerate(parts):
                if p == "ether" and i+1 < len(parts):
                    return parts[i+1].strip()
        return "未知"

    def _get_bluetooth_address(self) -> str:
        out = self.adb_client.shell_sync("settings get secure bluetooth_address", self.serial)
        if out and ":" in out:
            return out.strip()
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
        out = self.adb_client.shell_sync("uptime", self.serial)
        # 输出格式: up time: 1 day, 2:34,  idle time: ...
        if "up time:" in out:
            import re
            match = re.search(r"up time:\s*([^,]+)", out)
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
        out = self.adb_client.shell_sync("cat /proc/meminfo", self.serial)
        total = "?"
        available = "?"
        for line in out.splitlines():
            if "MemTotal:" in line:
                total = line.split()[1]
                total = f"{int(total)//1024} MB"
            if "MemAvailable:" in line:
                available = line.split()[1]
                available = f"{int(available)//1024} MB"
        return f"总计 {total}, 可用 {available}"

    def _get_storage_info(self) -> str:
        out = self.adb_client.shell_sync("df /data", self.serial)
        lines = out.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                size = parts[1]
                used = parts[2]
                return f"总容量 {size}, 已用 {used}"
        return "未知"

    def _get_display_detail(self) -> str:
        out = self.adb_client.shell_sync("dumpsys display | grep mDisplayInfo", self.serial)
        if "mDisplayInfo" in out:
            # 提取分辨率、密度等信息
            import re
            # 例如: mDisplayInfo=DisplayInfo{"..."}
            # 简单返回整行
            return out.strip()
        return "未知"



    def create_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 基本信息区域
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

        # 硬件与系统信息区域（新增）
        hardware_group = QGroupBox("硬件与系统信息")
        hw_layout = QFormLayout()
        self.imei_label = QLabel("未知")
        self.mac_label = QLabel("未知")
        self.bluetooth_label = QLabel("未知")
        self.network_label = QLabel("未知")
        self.uptime_label = QLabel("未知")
        self.cpu_label = QLabel("未知")
        self.memory_label = QLabel("未知")
        self.storage_label = QLabel("未知")
        self.display_detail_label = QLabel("未知")

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
        layout.addWidget(hardware_group)

        # 详细信息文本框（getprop 输出）
        detail_group = QGroupBox("详细属性 (getprop)")
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        return widget

    def create_process_manager_tab(self) -> QWidget:
        from ui.process_manager import ProcessManager
        pm = ProcessManager(self.serial, self.adb_client)
        pm.status_message.connect(self.show_status_message)
        return pm

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
