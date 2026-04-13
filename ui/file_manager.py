"""
ui/file_manager.py - 文件管理控件

功能：
    - 浏览设备文件系统（树形目录 + 文件列表）
    - 支持上传（本地 -> 设备）、下载（设备 -> 本地）
    - 支持删除、重命名、新建文件夹
    - 显示隐藏文件（可切换）
    - 路径收藏夹（储存在设备偏好中）
    - 后续扩展：拖拽传输、压缩/解压

依赖：PyQt5, core.adb_client, utils.config_manager
"""

import os
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QPushButton, QToolBar, QAction, QFileDialog,
    QMessageBox, QInputDialog, QProgressDialog, QMenu, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QDir
from PyQt5.QtGui import QIcon

from core.adb_client import AdbClient
from utils.config_manager import ConfigManager


class FileManager(QWidget):
    """文件管理控件，可嵌入设备窗口的选项卡"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.current_path = "/sdcard"  # 默认路径
        self.show_hidden = False        # 是否显示隐藏文件（以.开头）
        self.file_list = []             # 当前目录下的文件列表 [{name, is_dir, size, modified}, ...]

        self.init_ui()
        self.load_path(self.current_path)

    def init_ui(self):
        """初始化界面布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 顶部工具栏
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.back_btn = QAction("返回", self)
        self.back_btn.triggered.connect(self.go_back)
        toolbar.addAction(self.back_btn)

        self.forward_btn = QAction("前进", self)
        self.forward_btn.triggered.connect(self.go_forward)
        toolbar.addAction(self.forward_btn)

        self.up_btn = QAction("上级目录", self)
        self.up_btn.triggered.connect(self.go_up)
        toolbar.addAction(self.up_btn)

        toolbar.addSeparator()

        self.refresh_btn = QAction("刷新", self)
        self.refresh_btn.triggered.connect(lambda: self.load_path(self.current_path))
        toolbar.addAction(self.refresh_btn)

        self.home_btn = QAction("Home (/sdcard)", self)
        self.home_btn.triggered.connect(lambda: self.load_path("/sdcard"))
        toolbar.addAction(self.home_btn)

        toolbar.addSeparator()

        self.show_hidden_btn = QAction("显示隐藏文件", self)
        self.show_hidden_btn.setCheckable(True)
        self.show_hidden_btn.toggled.connect(self.toggle_hidden)
        toolbar.addAction(self.show_hidden_btn)

        self.mkdir_btn = QAction("新建文件夹", self)
        self.mkdir_btn.triggered.connect(self.create_directory)
        toolbar.addAction(self.mkdir_btn)

        layout.addWidget(toolbar)

        # 地址栏
        address_layout = QHBoxLayout()
        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self.go_to_address)
        self.go_btn = QPushButton("前往")
        self.go_btn.clicked.connect(self.go_to_address)
        address_layout.addWidget(QLabel("路径:"))
        address_layout.addWidget(self.address_bar)
        address_layout.addWidget(self.go_btn)
        layout.addLayout(address_layout)

        # 分割器：左侧目录树，右侧文件列表
        splitter = QSplitter(Qt.Horizontal)
        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderLabel("目录")
        self.dir_tree.setIndentation(10)
        self.dir_tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        splitter.addWidget(self.dir_tree)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "类型"])
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_table.itemDoubleClicked.connect(self.on_file_double_clicked)
        splitter.addWidget(self.file_table)

        splitter.setSizes([250, 650])
        layout.addWidget(splitter)

    def load_path(self, path: str):
        """加载指定路径的内容（异步）"""
        if not path:
            return
        path = path.rstrip('/')
        if not path:
            path = "/"
        self.current_path = path
        self.address_bar.setText(path)
        self.status_message(f"正在加载 {path} ...")
        # 使用 ls -la 获取文件列表
        self.adb_client.shell(f"ls -la {path}", self.serial,
                              callback=lambda code, out, err: self._on_ls_finished(code, out, err))

    def _on_ls_finished(self, exit_code, stdout, stderr):
        if exit_code != 0:
            self.status_message(f"加载失败: {stderr}")
            QMessageBox.warning(self, "错误", f"无法读取目录 {self.current_path}\n{stderr}")
            return
        # 解析 ls -la 输出
        self.file_list = self._parse_ls_output(stdout)
        self.populate_file_table()
        self.status_message(f"已加载 {len(self.file_list)} 个项目")
        # 刷新目录树（简单起见，先不实现树形结构，只显示当前目录下的子目录）
        self.update_dir_tree()

    def _parse_ls_output(self, output: str) -> List[dict]:
        """解析 ls -la 输出，返回文件列表"""
        files = []
        lines = output.splitlines()
        # 跳过第一行 "total X"
        for line in lines:
            line = line.strip()
            if not line or line.startswith("total"):
                continue
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                continue
            # 权限、链接数、所有者、组、大小、月份、日期、时间/年份、文件名
            permissions = parts[0]
            size_str = parts[4]
            month = parts[5]
            day = parts[6]
            time_or_year = parts[7]
            name = parts[8]
            # 是否为目录
            is_dir = permissions.startswith('d')
            # 是否隐藏文件（以.开头）
            if not self.show_hidden and name.startswith('.'):
                continue
            # 大小格式化
            try:
                size = int(size_str)
                if size < 1024:
                    size_display = f"{size} B"
                elif size < 1024*1024:
                    size_display = f"{size/1024:.1f} KB"
                else:
                    size_display = f"{size/(1024*1024):.1f} MB"
            except:
                size_display = size_str
            # 修改时间
            modified = f"{month} {day} {time_or_year}"
            files.append({
                "name": name,
                "is_dir": is_dir,
                "size": size_display,
                "size_bytes": size_str,
                "modified": modified,
                "full_path": self.current_path.rstrip('/') + '/' + name
            })
        # 排序：目录在前，文件在后，按名称排序
        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return files

    def populate_file_table(self):
        """填充文件列表表格"""
        self.file_table.setRowCount(len(self.file_list))
        for row, item in enumerate(self.file_list):
            name_item = QTableWidgetItem(item["name"])
            name_item.setData(Qt.UserRole, item["full_path"])
            if item["is_dir"]:
                name_item.setForeground(Qt.blue)
            self.file_table.setItem(row, 0, name_item)
            self.file_table.setItem(row, 1, QTableWidgetItem(item["size"]))
            self.file_table.setItem(row, 2, QTableWidgetItem(item["modified"]))
            file_type = "文件夹" if item["is_dir"] else "文件"
            self.file_table.setItem(row, 3, QTableWidgetItem(file_type))

    def update_dir_tree(self):
        """更新目录树（简化：只显示当前路径下的子目录）"""
        self.dir_tree.clear()
        root_item = QTreeWidgetItem([self.current_path])
        root_item.setData(0, Qt.UserRole, self.current_path)
        self.dir_tree.addTopLevelItem(root_item)
        # 获取当前目录下的子目录
        subdirs = [item for item in self.file_list if item["is_dir"]]
        for sub in subdirs:
            child = QTreeWidgetItem([sub["name"]])
            child.setData(0, Qt.UserRole, sub["full_path"])
            root_item.addChild(child)
        root_item.setExpanded(True)

    def on_tree_item_double_clicked(self, item, column):
        """双击目录树节点，加载对应路径"""
        path = item.data(0, Qt.UserRole)
        if path:
            self.load_path(path)

    def on_file_double_clicked(self, item):
        """双击文件列表项：如果是目录则进入，如果是文件则下载（或打开提示）"""
        row = item.row()
        file_info = self.file_list[row]
        if file_info["is_dir"]:
            self.load_path(file_info["full_path"])
        else:
            # 文件：询问下载
            reply = QMessageBox.question(self, "下载文件", f"是否下载文件 {file_info['name']} 到本地？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.download_file(file_info["full_path"], file_info["name"])

    def show_file_context_menu(self, position):
        """文件列表右键菜单"""
        selected = self.file_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        file_info = self.file_list[row]
        menu = QMenu()
        download_action = QAction("下载", self)
        download_action.triggered.connect(lambda: self.download_file(file_info["full_path"], file_info["name"]))
        menu.addAction(download_action)
        if not file_info["is_dir"]:
            rename_action = QAction("重命名", self)
            rename_action.triggered.connect(lambda: self.rename_file(file_info["full_path"]))
            menu.addAction(rename_action)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self.delete_file(file_info["full_path"], file_info["name"]))
        menu.addAction(delete_action)
        menu.exec_(self.file_table.viewport().mapToGlobal(position))

    def download_file(self, remote_path: str, filename: str):
        """下载文件到本地（弹出保存对话框）"""
        local_path, _ = QFileDialog.getSaveFileName(self, "保存文件", filename)
        if not local_path:
            return
        self.status_message(f"正在下载 {filename} ...")
        self.adb_client.pull(remote_path, local_path, self.serial,
                              callback=lambda code, out, err: self._on_download_finished(code, out, err, filename, local_path))

    def _on_download_finished(self, exit_code, stdout, stderr, filename, local_path):
        if exit_code == 0:
            self.status_message(f"下载完成: {filename}")
            QMessageBox.information(self, "下载成功", f"文件已保存到 {local_path}")
        else:
            self.status_message(f"下载失败: {filename}")
            QMessageBox.warning(self, "下载失败", f"下载 {filename} 失败\n{stderr}")

    def upload_file(self):
        """上传文件到当前目录"""
        local_paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "所有文件 (*.*)")
        if not local_paths:
            return
        for local_path in local_paths:
            filename = os.path.basename(local_path)
            remote_path = self.current_path.rstrip('/') + '/' + filename
            self.status_message(f"正在上传 {filename} ...")
            self.adb_client.push(local_path, remote_path, self.serial,
                                 callback=lambda code, out, err, fn=filename: self._on_upload_finished(code, out, err, fn))

    def _on_upload_finished(self, exit_code, stdout, stderr, filename):
        if exit_code == 0:
            self.status_message(f"上传完成: {filename}")
            self.load_path(self.current_path)  # 刷新
        else:
            self.status_message(f"上传失败: {filename}")
            QMessageBox.warning(self, "上传失败", f"上传 {filename} 失败\n{stderr}")

    def delete_file(self, remote_path: str, name: str):
        """删除文件或空目录"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除 {name} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.adb_client.shell(f"rm -rf {remote_path}", self.serial,
                              callback=lambda code, out, err: self._on_delete_finished(code, out, err, name))

    def _on_delete_finished(self, exit_code, stdout, stderr, name):
        if exit_code == 0:
            self.status_message(f"已删除: {name}")
            self.load_path(self.current_path)
        else:
            self.status_message(f"删除失败: {name}")
            QMessageBox.warning(self, "删除失败", f"删除 {name} 失败\n{stderr}")

    def rename_file(self, remote_path: str):
        """重命名文件或目录"""
        old_name = remote_path.split('/')[-1]
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        dir_path = remote_path[:remote_path.rfind('/')]
        new_remote_path = dir_path + '/' + new_name
        self.adb_client.shell(f"mv {remote_path} {new_remote_path}", self.serial,
                              callback=lambda code, out, err: self._on_rename_finished(code, out, err, new_name))

    def _on_rename_finished(self, exit_code, stdout, stderr, new_name):
        if exit_code == 0:
            self.status_message(f"重命名成功: {new_name}")
            self.load_path(self.current_path)
        else:
            self.status_message(f"重命名失败: {new_name}")
            QMessageBox.warning(self, "重命名失败", f"重命名失败\n{stderr}")

    def create_directory(self):
        """新建文件夹"""
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:")
        if not ok or not name:
            return
        new_path = self.current_path.rstrip('/') + '/' + name
        self.adb_client.shell(f"mkdir {new_path}", self.serial,
                              callback=lambda code, out, err: self._on_mkdir_finished(code, out, err, name))

    def _on_mkdir_finished(self, exit_code, stdout, stderr, name):
        if exit_code == 0:
            self.status_message(f"已创建文件夹: {name}")
            self.load_path(self.current_path)
        else:
            self.status_message(f"创建文件夹失败: {name}")
            QMessageBox.warning(self, "错误", f"创建文件夹失败\n{stderr}")

    def go_back(self):
        """返回历史（暂不实现历史栈）"""
        # TODO: 实现历史记录
        pass

    def go_forward(self):
        """前进（暂不实现）"""
        pass

    def go_up(self):
        """上级目录"""
        if self.current_path == "/":
            return
        parent = os.path.dirname(self.current_path.rstrip('/'))
        if not parent:
            parent = "/"
        self.load_path(parent)

    def go_to_address(self):
        """跳转到地址栏路径"""
        path = self.address_bar.text().strip()
        if not path:
            return
        self.load_path(path)

    def toggle_hidden(self, checked: bool):
        """切换显示隐藏文件"""
        self.show_hidden = checked
        self.load_path(self.current_path)

    def status_message(self, msg: str):
        """发送状态消息（可被父窗口捕获显示在状态栏）"""
        self.parent().status_message.emit(msg) if hasattr(self.parent(), "status_message") else None
        # 也可以直接 print 调试
        print(f"[FileManager] {msg}")