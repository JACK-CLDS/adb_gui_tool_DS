"""
ui/process_manager.py - 进程管理控件

显示设备当前运行的进程列表，支持杀死进程、过滤、刷新频率设置。
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
    status_message = pyqtSignal(str)

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.processes = []
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_processes)
        self.refresh_interval = 3000  # 默认3秒
        self.init_ui()
        self.load_processes()
        self.refresh_timer.start(self.refresh_interval)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部控制栏
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

        # 刷新频率设置
        control_layout.addWidget(QLabel("刷新间隔(ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1000, 10000)
        self.interval_spin.setValue(self.refresh_interval)
        self.interval_spin.valueChanged.connect(self.set_refresh_interval)
        control_layout.addWidget(self.interval_spin)

        layout.addLayout(control_layout)

        # 进程列表表格
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

    def load_processes(self):
        """同步加载进程列表（使用 ps -A）"""
        self.status_message.emit("正在获取进程列表...")
        out = self.adb_client.shell_sync("ps -A -o PID,NAME,RSS,STAT", self.serial, timeout=5)
        self.processes = self._parse_ps_output(out)
        self.filter_processes()

    def _parse_ps_output(self, output: str) -> List[Dict]:
        """解析 ps 输出，返回进程列表"""
        processes = []
        lines = output.splitlines()
        # 跳过第一行标题
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=3)
            if len(parts) >= 4:
                pid = parts[0]
                name = parts[1]
                rss = parts[2]  # 内存占用（KB）
                state = parts[3]
                # 格式化内存显示
                try:
                    rss_int = int(rss)
                    if rss_int < 1024:
                        mem_display = f"{rss_int} KB"
                    else:
                        mem_display = f"{rss_int/1024:.1f} MB"
                except:
                    mem_display = rss
                processes.append({
                    "pid": pid,
                    "name": name,
                    "memory": mem_display,
                    "state": state,
                    "raw_memory": rss
                })
        return processes

    def filter_processes(self):
        """根据过滤文本刷新表格显示"""
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
            # 根据状态着色
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

    def kill_selected_process(self):
        """杀死选中的进程"""
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
        reply = QMessageBox.question(self, "确认杀死", f"确定要杀死 {len(pids)} 个进程吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for pid in pids:
                out = self.adb_client.shell_sync(f"kill -9 {pid}", self.serial, timeout=2)
                self.status_message.emit(f"已杀死进程 {pid}")
            # 刷新列表
            self.load_processes()

    def show_context_menu(self, position):
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
        selected = self.table.selectedItems()
        if not selected:
            return
        pids = []
        for item in selected:
            row = item.row()
            pid_item = self.table.item(row, 0)
            if pid_item:
                pids.append(pid_item.text())
        if pids:
            QApplication.clipboard().setText("\n".join(pids))
            self.status_message.emit(f"已复制 {len(pids)} 个 PID")

    def copy_selected_name(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        names = []
        for item in selected:
            row = item.row()
            name_item = self.table.item(row, 1)
            if name_item:
                names.append(name_item.text())
        if names:
            QApplication.clipboard().setText("\n".join(names))
            self.status_message.emit(f"已复制 {len(names)} 个进程名")

    def set_refresh_interval(self, interval):
        self.refresh_interval = interval
        self.refresh_timer.start(interval)
        self.status_message.emit(f"刷新间隔已设为 {interval} ms")

    def closeEvent(self, event):
        self.refresh_timer.stop()
        event.accept()