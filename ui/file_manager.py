"""
ui/file_manager.py - 文件管理控件（同步版）
"""

import os
from typing import List, Dict
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QPushButton, QToolBar, QAction, QFileDialog,
    QMessageBox, QInputDialog, QProgressDialog, QMenu, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon

from core.adb_client import AdbClient


class FileManager(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.current_path = "/sdcard"
        self.show_hidden = False
        self.file_list = []

        self.init_ui()
        self.load_path(self.current_path)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
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

        self.home_btn = QAction("Home", self)
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

        self.upload_btn = QAction("上传文件", self)
        self.upload_btn.triggered.connect(self.upload_file)
        toolbar.addAction(self.upload_btn)

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

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderLabel("目录")
        self.dir_tree.setIndentation(10)
        self.dir_tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        splitter.addWidget(self.dir_tree)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "类型"])
        # 允许用户手动调整列宽
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        # 设置初始列宽
        self.file_table.setColumnWidth(0, 200)  # 名称列
        self.file_table.setColumnWidth(1, 100)  # 大小列
        self.file_table.setColumnWidth(2, 150)  # 修改时间列
        self.file_table.setColumnWidth(3, 80)   # 类型列
        # 启用排序（点击表头排序）
        self.file_table.setSortingEnabled(True)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_table.itemDoubleClicked.connect(self.on_file_double_clicked)
#        self.file_table = QTableWidget()
#        self.file_table.setColumnCount(4)
#        self.file_table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "类型"])
#        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
#        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
#        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)
#        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
#        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)
#        self.file_table.itemDoubleClicked.connect(self.on_file_double_clicked)
        splitter.addWidget(self.file_table)

        splitter.setSizes([250, 650])
        layout.addWidget(splitter)

    def load_path(self, path: str):
        """同步加载指定路径的文件列表，自动解析符号链接"""
        if not path:
            return
        path = path.rstrip('/')
        if not path:
            path = "/"
        
        # 递归解析符号链接（最多解析10层，带循环检测）
        original_path = path
        visited_paths = set()
        for _ in range(10):
            if path in visited_paths:
                print(f"[FileManager] Warning: symlink loop detected at {path}")
                break
            visited_paths.add(path)
            
            check_out = self.adb_client.shell_sync(f"ls -ld {path}", self.serial, timeout=5)
            if " -> " in check_out:
                target = check_out.split(" -> ")[-1].strip()
                print(f"[FileManager] {path} is a symlink to {target}")
                path = target
            else:
                break
        else:
            print(f"[FileManager] Warning: symlink recursion limit reached for {original_path}")
        
        # 检查路径是否存在
        test_out = self.adb_client.shell_sync(f"ls {path}", self.serial, timeout=5)
        if "No such file" in test_out or "cannot access" in test_out:
            self.status_message.emit(f"路径不存在: {path}")
            QMessageBox.warning(self, "路径不存在", f"目录不存在:\n{path}\n\n请检查路径是否正确。")
            return  # 不切换目录
        
        # 检查权限
        if "Permission denied" in test_out:
            self.status_message.emit(f"权限不足，无法访问 {path}")
            QMessageBox.warning(self, "权限不足", f"没有权限访问目录:\n{path}\n\n请检查目录权限或尝试以 root 权限运行。")
            return  # 不切换目录
        
        self.current_path = path
        self.address_bar.setText(path)
        self.status_message.emit(f"正在加载 {path} ...")
        
        out = self.adb_client.shell_sync(f"ls -la {path}", self.serial, timeout=10)
        print(f"[FileManager] ls -la {path} returned {len(out)} bytes")
        
        self.file_list = self._parse_ls_output(out)
        self.populate_file_table()
        self.status_message.emit(f"已加载 {len(self.file_list)} 个项目")
        self.update_dir_tree()

    def _parse_ls_output(self, output: str) -> List[Dict]:
        """解析 ls -la 输出，支持两种日期格式（月日 时:分 或 YYYY-MM-DD HH:MM）"""
        files = []
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("total"):
                continue
            
            parts = line.split()
            # 最少需要 8 个字段（权限 链接数 所有者 组 大小 日期 时间 文件名）
            if len(parts) < 8:
                print(f"[FileManager] Skipping line (too few parts): {line}")
                continue
            
            permissions = parts[0]
            # 链接数 parts[1]
            # 所有者 parts[2]
            # 组 parts[3]
            size_str = parts[4]
            
            # 判断日期格式：如果第5部分包含 '-' 则认为是 YYYY-MM-DD 格式
            date_part = parts[5]
            if '-' in date_part and len(date_part) == 10:  # YYYY-MM-DD
                month = date_part
                day = ""
                time_or_year = parts[6]  # HH:MM
                name_index = 7
            else:
                # 旧格式：月份 日期 时间/年份
                month = parts[5]
                day = parts[6]
                time_or_year = parts[7]
                name_index = 8
            
            # 文件名（可能包含空格）
            name = ' '.join(parts[name_index:])
            
            # 处理链接文件
            if " -> " in name:
                name = name.split(" -> ")[0]
            
            is_dir = permissions.startswith('d')
            
            if not self.show_hidden and name.startswith('.'):
                continue
            
            # 格式化大小
            try:
                size = int(size_str)
                if size < 1024:
                    size_display = f"{size} B"
                elif size < 1024*1024:
                    size_display = f"{size/1024:.1f} KB"
                else:
                    size_display = f"{size/(1024*1024):.1f} MB"
            except ValueError:
                size_display = size_str
            
            if day:
                modified = f"{month} {day} {time_or_year}"
            else:
                modified = f"{month} {time_or_year}"
            
            files.append({
                "name": name,
                "is_dir": is_dir,
                "size": size_display,
                "size_bytes": size_str,
                "modified": modified,
                "full_path": self.current_path.rstrip('/') + '/' + name
            })
        
        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        print(f"[FileManager] Parsed {len(files)} files/directories")
        return files

    def populate_file_table(self):
        print(f"[FileManager] Populating table with {len(self.file_list)} items")
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
        self.dir_tree.clear()
        root_item = QTreeWidgetItem([self.current_path])
        root_item.setData(0, Qt.UserRole, self.current_path)
        self.dir_tree.addTopLevelItem(root_item)
        subdirs = [item for item in self.file_list if item["is_dir"]]
        for sub in subdirs:
            child = QTreeWidgetItem([sub["name"]])
            child.setData(0, Qt.UserRole, sub["full_path"])
            root_item.addChild(child)
        root_item.setExpanded(True)

    def on_tree_item_double_clicked(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path:
            self.load_path(path)

    def on_file_double_clicked(self, item):
        row = item.row()
        file_info = self.file_list[row]
        if file_info["is_dir"]:
            self.load_path(file_info["full_path"])
        else:
            reply = QMessageBox.question(self, "下载文件", f"是否下载文件 {file_info['name']} 到本地？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.download_file(file_info["full_path"], file_info["name"])

    def show_file_context_menu(self, position):
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
        local_path, _ = QFileDialog.getSaveFileName(self, "保存文件", filename)
        if not local_path:
            return
        self.status_message.emit(f"正在下载 {filename} ...")
        # 同步下载
        try:
            self.adb_client.pull_sync(remote_path, local_path, self.serial)
            self.status_message.emit(f"下载完成: {filename}")
            QMessageBox.information(self, "下载成功", f"文件已保存到 {local_path}")
        except Exception as e:
            self.status_message.emit(f"下载失败: {filename}")
            QMessageBox.warning(self, "下载失败", f"下载 {filename} 失败\n{str(e)}")

    def upload_file(self):
        local_paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "所有文件 (*.*)")
        if not local_paths:
            return
        for local_path in local_paths:
            filename = os.path.basename(local_path)
            remote_path = self.current_path.rstrip('/') + '/' + filename
            self.status_message.emit(f"正在上传 {filename} ...")
            try:
                self.adb_client.push_sync(local_path, remote_path, self.serial)
                self.status_message.emit(f"上传完成: {filename}")
                self.load_path(self.current_path)
            except Exception as e:
                self.status_message.emit(f"上传失败: {filename}")
                QMessageBox.warning(self, "上传失败", f"上传 {filename} 失败\n{str(e)}")

    def delete_file(self, remote_path: str, name: str):
        reply = QMessageBox.question(self, "确认删除", f"确定要删除 {name} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        out = self.adb_client.shell_sync(f"rm -rf {remote_path}", self.serial, timeout=5)
        if "Permission denied" in out:
            self.status_message.emit(f"删除失败: 权限不足")
            QMessageBox.warning(self, "删除失败", f"无法删除 {name}\n权限不足，请检查文件权限。")
        elif "No such file" in out or "cannot remove" in out:
            self.status_message.emit(f"删除失败: {name}")
            QMessageBox.warning(self, "删除失败", f"删除 {name} 失败\n{out}")
        else:
            self.status_message.emit(f"已删除: {name}")
            self.load_path(self.current_path)

    def rename_file(self, remote_path: str):
        old_name = remote_path.split('/')[-1]
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        dir_path = remote_path[:remote_path.rfind('/')]
        new_remote_path = dir_path + '/' + new_name
        out = self.adb_client.shell_sync(f"mv {remote_path} {new_remote_path}", self.serial, timeout=5)
        if "No such file" not in out and "cannot rename" not in out:
            self.status_message.emit(f"重命名成功: {new_name}")
            self.load_path(self.current_path)
        else:
            self.status_message.emit(f"重命名失败: {new_name}")
            QMessageBox.warning(self, "重命名失败", f"重命名失败\n{out}")

    def create_directory(self):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:")
        if not ok or not name:
            return
        new_path = self.current_path.rstrip('/') + '/' + name
        out = self.adb_client.shell_sync(f"mkdir {new_path}", self.serial, timeout=5)
        if "read-only" in out or "Permission denied" in out:
            self.status_message.emit("创建失败: 权限不足")
            QMessageBox.warning(self, "错误", "创建文件夹失败: 权限不足")
        elif "File exists" in out:
            self.status_message.emit("创建失败: 文件已存在")
            QMessageBox.warning(self, "错误", "创建文件夹失败: 同名文件已存在")
        else:
            self.status_message.emit(f"已创建文件夹: {name}")
            self.load_path(self.current_path)

    def go_back(self):
        # TODO: 实现历史记录
        pass

    def go_forward(self):
        pass

    def go_up(self):
        if self.current_path == "/":
            return
        parent = os.path.dirname(self.current_path.rstrip('/'))
        if not parent:
            parent = "/"
        self.load_path(parent)

    def go_to_address(self):
        path = self.address_bar.text().strip()
        if not path:
            return
        self.load_path(path)

    def toggle_hidden(self, checked: bool):
        self.show_hidden = checked
        self.load_path(self.current_path)
