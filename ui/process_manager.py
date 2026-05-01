"""
ui/process_manager.py - 进程管理控件 (Process Manager)

功能 (Features):
    - 显示设备当前运行的进程列表 (Display running process list)
    - 按进程名过滤 (Filter by process name)
    - 杀死选中进程 (Kill selected processes)
    - 复制 PID 或进程名 (Copy PID or process name)
    - 可调整刷新间隔 (Adjustable refresh interval)
    - 根据进程状态着色 (Color-coded process states)

依赖 (Dependencies): PyQt5, core.adb_client
"""

from typing import List, Dict
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QPushButton, QMenu, QAction, QMessageBox,
    QSpinBox, QLabel, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor

from core.adb_client import AdbClient


class ProcessManager(QWidget):
    """进程管理控件 (Process manager widget)"""

    status_message = pyqtSignal(str)   # 状态栏消息信号

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.processes: List[Dict] = []
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_processes)
        self.refresh_interval = 3000   # 默认刷新间隔 3 秒
        self.init_ui()

        # 延迟加载和启动定时器，避免阻塞窗口打开 (Defer loading to avoid UI freeze)
        QTimer.singleShot(100, self._start_monitoring)

    # ========== 监控控制 (Monitoring Control) ==========

    def _start_monitoring(self):
        """首次加载并启动自动刷新 (Initial load and start auto-refresh)"""
        self.load_processes()
        self.refresh_timer.start(self.refresh_interval)

    def set_refresh_interval(self, interval: int):
        """
        设置自动刷新间隔 (Set auto-refresh interval)
        :param interval: 毫秒 (milliseconds)
        """
        self.refresh_interval = interval
        self.refresh_timer.start(interval)
        self.status_message.emit(f"刷新间隔已设为 {interval} ms")

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建界面布局 (Create UI layout)"""
        layout = QVBoxLayout(self)

        # ---- 顶部控制栏 (Top control bar) ----
        control_layout = QHBoxLayout()

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("过滤进程名...")
        self.filter_input.textChanged.connect(self.filter_processes)
        control_layout.addWidget(QLabel("过滤:"))
        control_layout.addWidget(self.filter_input)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_processes)
        control_layout.addWidget(self.refresh_btn)

        self.kill_btn = QPushButton("杀死选中进程")
        self.kill_btn.clicked.connect(self.kill_selected_process)
        control_layout.addWidget(self.kill_btn)

        # 刷新频率设置 (Refresh interval spin box)
        control_layout.addWidget(QLabel("刷新间隔(ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1000, 10000)
        self.interval_spin.setValue(self.refresh_interval)
        self.interval_spin.valueChanged.connect(self.set_refresh_interval)
        control_layout.addWidget(self.interval_spin)

        layout.addLayout(control_layout)

        # ---- 进程列表表格 (Process table) ----
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["PID", "进程名", "内存占用", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)

    # ========== 进程加载与解析 (Process Loading & Parsing) ==========

    def load_processes(self):
        """从设备获取进程列表 (Fetch process list from device)"""
        self.status_message.emit("正在获取进程列表...")
        # 使用基础 ps 命令，兼容所有 Android 版本
        out = self.adb_client.shell_sync("ps", self.serial, timeout=5)
        self.processes = self._parse_ps_output_old(out)
        self.filter_processes()

    def filter_processes(self):
        """根据过滤文本刷新表格显示 (Filter and refresh the table)"""
        filter_text = self.filter_input.text().strip().lower()
        filtered = self.processes
        if filter_text:
            filtered = [p for p in self.processes if filter_text in p["name"].lower()]

        self.table.setRowCount(len(filtered))
        for row, proc in enumerate(filtered):
            pid_item = QTableWidgetItem(proc["pid"])
            name_item = QTableWidgetItem(proc["name"])
            mem_item = QTableWidgetItem(proc["memory"])
            state_item = QTableWidgetItem(proc["state"])

            # 根据状态着色 (Color by state)
            if proc["state"] == 'R':
                state_item.setForeground(QColor("green"))
            elif proc["state"] == 'S':
                state_item.setForeground(QColor("blue"))
            elif proc["state"] == 'D':
                state_item.setForeground(QColor("orange"))
            elif proc["state"] == 'Z':
                state_item.setForeground(QColor("red"))

            self.table.setItem(row, 0, pid_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, mem_item)
            self.table.setItem(row, 3, state_item)

        self.status_message.emit(f"已加载 {len(filtered)} 个进程")

    # ========== 进程操作 (Process Operations) ==========

    def kill_selected_process(self):
        """杀死选中的进程 (Kill selected processes)"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选中要杀死的进程")
            return

        pids = []
        for row in selected_rows:
            pid_item = self.table.item(row, 0)
            if pid_item:
                pids.append(pid_item.text())
        if not pids:
            return

        reply = QMessageBox.question(
            self, "确认杀死", f"确定要杀死 {len(pids)} 个进程吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for pid in pids:
                self.adb_client.shell_sync(f"kill -9 {pid}", self.serial, timeout=2)
                self.status_message.emit(f"已杀死进程 {pid}")
            self.load_processes()   # 刷新列表

    def show_context_menu(self, position):
        """显示右键菜单 (Show context menu)"""
        menu = QMenu()
        copy_pid = QAction("复制 PID", self)
        copy_pid.triggered.connect(self.copy_selected_pid)
        menu.addAction(copy_pid)

        copy_name = QAction("复制进程名", self)
        copy_name.triggered.connect(self.copy_selected_name)
        menu.addAction(copy_name)

        kill_action = QAction("杀死进程", self)
        kill_action.triggered.connect(self.kill_selected_process)
        menu.addAction(kill_action)

        menu.exec_(self.table.viewport().mapToGlobal(position))

    def copy_selected_pid(self):
        """复制选中行的 PID 到剪贴板 (Copy selected PIDs to clipboard)"""
        selected = self.table.selectedItems()
        if not selected:
            return
        pids = [self.table.item(item.row(), 0).text() for item in selected if self.table.item(item.row(), 0)]
        if pids:
            QApplication.clipboard().setText("\n".join(pids))
            self.status_message.emit(f"已复制 {len(pids)} 个 PID")

    def copy_selected_name(self):
        """复制选中行的进程名到剪贴板 (Copy selected process names to clipboard)"""
        selected = self.table.selectedItems()
        if not selected:
            return
        names = [self.table.item(item.row(), 1).text() for item in selected if self.table.item(item.row(), 1)]
        if names:
            QApplication.clipboard().setText("\n".join(names))
            self.status_message.emit(f"已复制 {len(names)} 个进程名")

    # ========== PS 输出解析 (PS Output Parsers) ==========

    def _parse_ps_output_old(self, output: str) -> List[Dict]:
        """
        解析旧版 ps 输出 (Android 7 及以下)
        Parse old ps output format (Android 7 and below).
        格式: USER PID PPID VSZ RSS WCHAN ADDR S NAME
        """
        processes = []
        lines = output.splitlines()
        for line in lines[1:]:   # 跳过标题行
            parts = line.split()
            if len(parts) >= 9:
                pid = parts[1]
                rss = parts[4]       # RSS 列
                state = parts[7]     # S 列
                name = parts[8]      # NAME 列
                processes.append({
                    "pid": pid,
                    "name": name,
                    "memory": f"{rss} KB",
                    "state": state,
                    "raw_memory": rss
                })
        return processes

    def _parse_ps_output_new(self, output: str) -> List[Dict]:
        """
        解析新版 ps 输出（带 -o 选项）
        Parse new ps output format (with -o option).
        预留实现。
        """
        processes = []
        lines = output.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                processes.append({
                    "pid": parts[0],
                    "name": parts[1],
                    "memory": parts[2],
                    "state": parts[3],
                    "raw_memory": parts[2]
                })
        return processes

    # 兼容方法，实际调用旧版解析器 (Alias for the actual parser)
    _parse_ps_output = _parse_ps_output_old

    # ========== 窗口关闭 (Window Close) ==========

    def closeEvent(self, event):
        """关闭时停止刷新定时器 (Stop refresh timer on close)"""
        self.refresh_timer.stop()
        event.accept()
