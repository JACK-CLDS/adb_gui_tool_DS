"""
ui/file_manager.py - 文件管理控件 (File Manager Widget)

功能 (Features):
    - 双面板：目录树 + 文件列表 (Split view: directory tree & file table)
    - 浏览、上传、下载、删除、重命名、新建文件夹 (Browse, upload, download, delete, rename, new folder)
    - 拖拽上传本地文件 (Drag & drop upload)
    - 显示隐藏文件切换 (Show/hide hidden files)
    - 地址栏直接跳转 (Address bar for quick navigation)
    - 符号链接自动解析 (Symbolic link resolution)
    - 键盘按键快速定位文件 (Single key press quick locate)

依赖 (Dependencies): PyQt5, core.adb_client
"""

import os
from typing import List, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QPushButton, QToolBar, QAction, QFileDialog,
    QMessageBox, QInputDialog, QProgressDialog, QMenu, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent

from core.adb_client import AdbClient


class FileManager(QWidget):
    """文件管理控件 (File manager widget)"""

    status_message = pyqtSignal(str)   # 状态栏消息信号

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.current_path = "/sdcard"
        self.show_hidden = False
        self.file_list = []
        self.setAcceptDrops(True)

        self.init_ui()
        self.load_path(self.current_path)

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建界面布局 (Create UI layout)"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- 工具栏 (Toolbar) ----
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

        # ---- 地址栏 + 统计标签 (Address bar + stats label) ----
        address_layout = QHBoxLayout()
        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self.go_to_address)
        self.go_btn = QPushButton("前往")
        self.go_btn.clicked.connect(self.go_to_address)

        address_layout.addWidget(QLabel("路径:"))
        address_layout.addWidget(self.address_bar)
        address_layout.addWidget(self.go_btn)
        address_layout.addStretch()

        self.stats_label = QLabel()
        self.stats_label.setAlignment(Qt.AlignRight)
        self.stats_label.setMinimumWidth(200)
        self.stats_label.setFixedHeight(30)
        address_layout.addWidget(self.stats_label)
        layout.addLayout(address_layout)

        # ---- 分割器：目录树 + 文件表格 (Splitter: tree + table) ----
        splitter = QSplitter(Qt.Horizontal)

        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderLabel("目录")
        self.dir_tree.setIndentation(10)
        self.dir_tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        splitter.addWidget(self.dir_tree)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "类型"])
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.file_table.setColumnWidth(0, 200)   # 名称
        self.file_table.setColumnWidth(1, 100)   # 大小
        self.file_table.setColumnWidth(2, 150)   # 修改时间
        self.file_table.setColumnWidth(3, 80)    # 类型
        self.file_table.setSortingEnabled(True)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_table.itemDoubleClicked.connect(self.on_file_double_clicked)
        self.file_table.installEventFilter(self)
        splitter.addWidget(self.file_table)

        splitter.setSizes([250, 650])
        layout.addWidget(splitter)

    # ========== 路径加载 (Path Loading) ==========

    def load_path(self, path: str):
        """
        同步加载指定路径的文件列表，自动解析符号链接。
        Load file list for given path, resolving symlinks up to 10 levels.
        """
        if not path:
            return
        path = path.rstrip('/')
        if not path:
            path = "/"

        # 递归解析符号链接 (Resolve symlinks up to 10 levels)
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

        # 检查路径是否有效 (Check existence and permissions)
        test_out = self.adb_client.shell_sync(f"ls {path}", self.serial, timeout=5)
        if "No such file" in test_out or "cannot access" in test_out:
            self.status_message.emit(f"路径不存在: {path}")
            QMessageBox.warning(self, "路径不存在", f"目录不存在:\n{path}\n\n请检查路径是否正确。")
            return
        if "Permission denied" in test_out:
            self.status_message.emit(f"权限不足，无法访问 {path}")
            QMessageBox.warning(self, "权限不足", f"没有权限访问目录:\n{path}\n\n请检查目录权限或尝试以 root 权限运行。")
            return

        self.current_path = path
        self.address_bar.setText(path)
        self.status_message.emit(f"正在加载 {path} ...")

        out = self.adb_client.shell_sync(f"ls -la {path}", self.serial, timeout=10)
        self.file_list = self._parse_ls_output(out)

        # 更新 UI (Update UI)
        self.populate_file_table()
        self.update_dir_tree()

        dir_count = sum(1 for item in self.file_list if item["is_dir"])
        file_count = len(self.file_list) - dir_count
        self.status_message.emit(f"已加载 {len(self.file_list)} 个项目")
        self.stats_label.setText(f"{dir_count} 个文件夹, {file_count} 个文件")

    def _parse_ls_output(self, output: str) -> List[Dict]:
        """
        解析 ls -la 输出，兼容新旧两种日期格式。
        Parse ls -la output, supports two date formats:
          - "Mon DD HH:MM" (old)
          - "YYYY-MM-DD HH:MM" (new)
        """
        files = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("total"):
                continue

            parts = line.split()
            if len(parts) < 8:   # 权限 链接数 所有者 组 大小 日期 时间 文件名
                print(f"[FileManager] Skipping line (too few parts): {line}")
                continue

            permissions = parts[0]
            size_str = parts[4]

            # 判断日期格式 (Detect date format)
            date_part = parts[5]
            if '-' in date_part and len(date_part) == 10:   # YYYY-MM-DD
                month = date_part
                day = ""
                time_or_year = parts[6]
                name_index = 7
            else:   # Mon DD HH:MM
                month = parts[5]
                day = parts[6]
                time_or_year = parts[7]
                name_index = 8

            name = ' '.join(parts[name_index:])   # 文件名可能包含空格

            # 移除符号链接目标 (Remove symlink target)
            if " -> " in name:
                name = name.split(" -> ")[0]

            is_dir = permissions.startswith('d')

            # 隐藏文件过滤 (Hidden files filter)
            if not self.show_hidden and name.startswith('.'):
                continue

            # 格式化大小 (Format file size)
            try:
                size = int(size_str)
                if size < 1024:
                    size_display = f"{size} B"
                elif size < 1024 * 1024:
                    size_display = f"{size / 1024:.1f} KB"
                else:
                    size_display = f"{size / (1024 * 1024):.1f} MB"
            except ValueError:
                size_display = size_str

            modified = f"{month} {day} {time_or_year}" if day else f"{month} {time_or_year}"

            files.append({
                "name": name,
                "is_dir": is_dir,
                "size": size_display,
                "size_bytes": size_str,
                "modified": modified,
                "full_path": self.current_path.rstrip('/') + '/' + name
            })

        files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return files

    # ========== 表格与树刷新 (Table & Tree Refresh) ==========

    def populate_file_table(self):
        """将文件列表填充到表格 (Populate file table)"""
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
        """刷新目录树 (Refresh directory tree)"""
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

    # ========== 导航 (Navigation) ==========

    def on_tree_item_double_clicked(self, item, column):
        """目录树双击导航 (Navigate from tree double-click)"""
        path = item.data(0, Qt.UserRole)
        if path:
            self.load_path(path)

    def on_file_double_clicked(self, item):
        """文件表格双击：进入目录或下载文件 (Double-click: enter dir or download file)"""
        row = item.row()
        file_info = self.file_list[row]
        if file_info["is_dir"]:
            self.load_path(file_info["full_path"])
        else:
            reply = QMessageBox.question(self, "下载文件", f"是否下载文件 {file_info['name']} 到本地？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.download_file(file_info["full_path"], file_info["name"])

    def go_back(self):
        # TODO: 实现后退历史记录 (Implement back history)
        pass

    def go_forward(self):
        # TODO: 实现前进历史记录 (Implement forward history)
        pass

    def go_up(self):
        """返回上级目录 (Go up to parent directory)"""
        if self.current_path == "/":
            return
        parent = os.path.dirname(self.current_path.rstrip('/'))
        if not parent:
            parent = "/"
        self.load_path(parent)

    def go_to_address(self):
        """跳转到地址栏路径 (Navigate to address bar path)"""
        path = self.address_bar.text().strip()
        if not path:
            return
        self.load_path(path)

    def toggle_hidden(self, checked: bool):
        """切换隐藏文件显示 (Toggle hidden files)"""
        self.show_hidden = checked
        self.load_path(self.current_path)

    # ========== 文件操作 (File Operations) ==========

    def show_file_context_menu(self, position):
        """文件右键菜单 (File context menu)"""
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
        """下载文件到本地 (Download file with progress)"""
        local_path, _ = QFileDialog.getSaveFileName(self, "保存文件", filename)
        if not local_path:
            return

        progress = QProgressDialog(f"正在下载 {filename}...", "取消", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setAutoReset(True)
        progress.show()

        def update_progress(percent):
            if progress.wasCanceled():
                return
            progress.setValue(percent)
            if percent >= 100:
                progress.setLabelText("下载完成，正在完成...")

        try:
            success = self.adb_client.pull_with_progress(remote_path, local_path, self.serial, update_progress)
            if success:
                progress.setValue(100)
                self.status_message.emit(f"下载完成: {filename}")
                QMessageBox.information(self, "下载成功", f"文件已保存到 {local_path}")
            else:
                raise Exception("拉取失败")
        except Exception as e:
            progress.close()
            self.status_message.emit(f"下载失败: {filename}")
            QMessageBox.warning(self, "下载失败", f"下载 {filename} 失败\n{str(e)}")

    def upload_file(self):
        """上传本地文件 (Upload files)"""
        local_paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "所有文件 (*.*)")
        if not local_paths:
            return

        for local_path in local_paths:
            filename = os.path.basename(local_path)
            remote_path = self.current_path.rstrip('/') + '/' + filename

            progress = QProgressDialog(f"正在上传 {filename}...", "取消", 0, 100, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setAutoClose(True)
            progress.setAutoReset(True)
            progress.show()

            def update_progress(percent):
                if progress.wasCanceled():
                    return
                progress.setValue(percent)
                if percent >= 100:
                    progress.setLabelText("上传完成，正在完成...")

            try:
                success = self.adb_client.push_with_progress(local_path, remote_path, self.serial, update_progress)
                if success:
                    progress.setValue(100)
                    self.status_message.emit(f"上传完成: {filename}")
                    self.load_path(self.current_path)   # 刷新文件列表
                else:
                    raise Exception("推送失败")
            except Exception as e:
                progress.close()
                self.status_message.emit(f"上传失败: {filename}")
                QMessageBox.warning(self, "上传失败", f"上传 {filename} 失败\n{str(e)}")

    def upload_files(self, local_paths: List[str]):
        """
        批量上传文件（供拖拽调用）(Batch upload, used by drag & drop)
        """
        if not local_paths:
            return
        reply = QMessageBox.question(self, "确认上传", f"确定要上传 {len(local_paths)} 个文件到当前目录吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for local_path in local_paths:
            filename = os.path.basename(local_path)
            remote_path = self.current_path.rstrip('/') + '/' + filename
            self.status_message.emit(f"正在上传 {filename} ...")
            try:
                self.adb_client.push_sync(local_path, remote_path, self.serial)
                self.status_message.emit(f"上传完成: {filename}")
            except Exception as e:
                self.status_message.emit(f"上传失败: {filename}")
                QMessageBox.warning(self, "上传失败", f"上传 {filename} 失败\n{str(e)}")
        self.load_path(self.current_path)

    def delete_file(self, remote_path: str, name: str):
        """删除文件或文件夹 (Delete file or folder)"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除 {name} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        out = self.adb_client.shell_sync(f"rm -rf {remote_path}", self.serial, timeout=5)
        if "Permission denied" in out:
            self.status_message.emit("删除失败: 权限不足")
            QMessageBox.warning(self, "删除失败", f"无法删除 {name}\n权限不足，请检查文件权限。")
        elif "No such file" in out or "cannot remove" in out:
            self.status_message.emit(f"删除失败: {name}")
            QMessageBox.warning(self, "删除失败", f"删除 {name} 失败\n{out}")
        else:
            self.status_message.emit(f"已删除: {name}")
            self.load_path(self.current_path)

    def rename_file(self, remote_path: str):
        """重命名文件或文件夹 (Rename file or folder)"""
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
        """新建文件夹 (Create new directory)"""
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

    # ========== 拖拽上传 (Drag & Drop Upload) ==========

    def dragEnterEvent(self, event):
        """拖拽进入：接受本地文件 (Accept local file drag)"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """拖拽放下：触发批量上传 (Drop event: start upload)"""
        urls = event.mimeData().urls()
        if not urls:
            return
        local_paths = []
        for url in urls:
            path = url.toLocalFile()
            if path:
                local_paths.append(path)
        if local_paths:
            self.upload_files(local_paths)

    # ========== 事件过滤 (Event Filter) ==========

    def eventFilter(self, obj, event):
        """
        按键快速定位：按下字母键定位到首字母匹配的文件。
        Quick locate: press a letter key to jump to file starting with that letter.
        """
        if obj == self.file_table and event.type() == QEvent.KeyPress:
            key = event.text()
            if key and key.isprintable() and len(key) == 1:
                letter = key.lower()
                for row, item in enumerate(self.file_list):
                    if item["name"].lower().startswith(letter):
                        self.file_table.selectRow(row)
                        self.file_table.scrollToItem(self.file_table.item(row, 0))
                        return True
        return super().eventFilter(obj, event)
