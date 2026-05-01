"""
ui/apps_tab.py - 应用管理控件 (App Management Tab)

功能 (Features):
    - 系统应用 / 用户应用分选项卡展示 (System & user app tabs)
    - 应用列表：图标、名称、包名 (App list: icon, name, package)
    - 搜索过滤，支持正则表达式 (Search filter with regex support)
    - 右键菜单：复制包名、卸载、清除数据、导出APK、运行/以root运行
    - 多选应用批量操作 (Multi-select support)
    - 拖拽安装APK (Drag & drop APK install)
    - 后台异步加载应用图标并缓存到本地 (Async icon loading with local cache)

依赖 (Dependencies): PyQt5, core.adb_client
"""

import re
import os
import subprocess
from typing import List, Dict, Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton,
    QMenu, QAction, QMessageBox, QApplication, QFileDialog,
    QProgressDialog, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QThread, QSize
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QIcon

from core.adb_client import AdbClient


class IconLoaderThread(QThread):
    """
    后台线程：从设备获取图标数据 (Background thread: fetch app icon from device)
    """

    icon_ready = pyqtSignal(str, bytes)   # (package, icon_data)

    def __init__(self, adb_client: AdbClient, package: str, apk_path: str, serial: str):
        super().__init__()
        self.adb_client = adb_client
        self.package = package
        self.apk_path = apk_path
        self.serial = serial

    def run(self):
        try:
            data = self.adb_client.get_app_icon_data(self.package, self.apk_path, self.serial)
            if data:
                self.icon_ready.emit(self.package, data)
        except Exception as e:
            print(f"[IconLoaderThread] Failed to load icon for {self.package}: {e}")


class AppsTab(QWidget):
    """应用管理控件 (App management widget)"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.system_apps: List[Dict] = []
        self.user_apps: List[Dict] = []
        self.current_filter = ""
        self.use_regex = False
        self.icon_queue = []           # [(package, apk_path, table, row), ...]
        self.icon_workers = []         # 正在运行的 IconLoaderThread
        self.icon_loading_active = False

        # 每个设备独立的缓存目录 (Per-device cache directory)
        self.ICON_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "app_icons" / self.serial
        self.ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        self.init_ui()
        QTimer.singleShot(0, self.load_apps)   # 延迟加载，避免阻塞窗口显示

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建界面布局 (Create UI layout)"""
        layout = QVBoxLayout(self)

        # ---- 搜索栏 (Search bar) ----
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索应用名称或包名... (支持正则表达式)")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.regex_checkbox = QPushButton("正则表达式")
        self.regex_checkbox.setCheckable(True)
        self.regex_checkbox.toggled.connect(self.on_regex_toggled)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_apps)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.regex_checkbox)
        search_layout.addWidget(self.refresh_btn)
        layout.addLayout(search_layout)

        # ---- 选项卡 (Tabs) ----
        self.tab_widget = QTabWidget()
        self.system_tab = QWidget()
        self.user_tab = QWidget()
        self.tab_widget.addTab(self.system_tab, "系统应用")
        self.tab_widget.addTab(self.user_tab, "用户应用")
        layout.addWidget(self.tab_widget)

        # ---- 表格 (Tables) ----
        self.system_table = self.create_app_table()
        self.user_table = self.create_app_table()
        self.setup_table_layout(self.system_tab, self.system_table)
        self.setup_table_layout(self.user_tab, self.user_table)

        self.setAcceptDrops(True)   # 启用拖拽安装

    def create_app_table(self) -> QTableWidget:
        """创建应用表格 (Create app table widget)"""
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["", "应用名称", "包名"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.setColumnWidth(0, 32)     # 图标列
        table.setColumnWidth(1, 200)    # 应用名称
        table.setColumnWidth(2, 500)    # 包名
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_context_menu)
        table.verticalHeader().setFixedWidth(40)
        table.verticalHeader().setDefaultSectionSize(30)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.setIconSize(QSize(24, 24))
        return table

    def setup_table_layout(self, parent, table):
        """将表格嵌入父布局 (Embed table into parent layout)"""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(table)

    # ========== 应用加载与解析 (Load & Parse) ==========

    def load_apps(self):
        """加载应用列表 (Load app list from device)"""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("加载中...")
        # 清空待加载图标队列，停止工作线程
        self.icon_queue.clear()
        self._stop_icon_workers()

        # 用户应用 (User apps)
        try:
            user_out = self.adb_client.shell_sync("pm list packages -f -3", self.serial, timeout=10)
            self.user_apps = self._parse_packages(user_out)
            self.populate_table(self.user_table, self.user_apps)
        except Exception as e:
            print(f"[AppsTab] Error loading user apps: {e}")
            self.user_apps = []

        # 系统应用 (System apps)
        try:
            sys_out = self.adb_client.shell_sync("pm list packages -f -s", self.serial, timeout=10)
            self.system_apps = self._parse_packages(sys_out)
            self.populate_table(self.system_table, self.system_apps)
        except Exception as e:
            print(f"[AppsTab] Error loading system apps: {e}")
            self.system_apps = []

        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("刷新")
        self._start_icon_loading()   # 开始异步加载图标

    def _parse_packages(self, output: str) -> List[Dict]:
        """
        解析 pm list packages -f 输出 (Parse pm list packages output)
        格式: package:/system/app/SomeApp/SomeApp.apk=com.example.app
        """
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                rest = line[8:]
                if '=' in rest:
                    apk_path, pkg = rest.split('=', 1)
                    packages.append({
                        "package": pkg,
                        "apk_path": apk_path,
                        "name": self._get_app_name_from_package(pkg),
                        "version_name": "",
                        "version_code": "",
                        "install_time": ""
                    })
        return packages

    def _get_app_name_from_package(self, pkg: str) -> str:
        """从包名中提取简易应用名 (Extract a simple app name from package)"""
        parts = pkg.split('.')
        return parts[-1] if parts else pkg

    # ========== 表格填充 (Table Population) ==========

    def populate_table(self, table: QTableWidget, apps: List[Dict], app_type: str = ""):
        """将应用列表填充到表格 (Populate table with apps)"""
        filtered = self.filter_apps(apps)
        filtered.sort(key=lambda x: x.get("name", "").lower())
        table.setRowCount(len(filtered))
        for row, app in enumerate(filtered):
            # 图标列 (Icon column)
            icon_item = QTableWidgetItem()
            cached = self._get_cached_icon(app["package"])
            if cached:
                icon_item.setIcon(cached)
            else:
                # 使用默认图标，并加入异步加载队列
                icon_item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                self.icon_queue.append((app["package"], app["apk_path"], table, row))
            table.setItem(row, 0, icon_item)

            # 应用名称列 (App name column)
            name_item = QTableWidgetItem(app.get("name", ""))
            name_item.setData(Qt.UserRole, app["package"])
            table.setItem(row, 1, name_item)

            # 包名列 (Package name column)
            table.setItem(row, 2, QTableWidgetItem(app["package"]))

    # ========== 图标缓存与异步加载 (Icon Caching & Async Loading) ==========

    def _get_cached_icon(self, package: str) -> Optional[QIcon]:
        """从本地缓存加载图标 (Load icon from local cache)"""
        icon_path = self.ICON_CACHE_DIR / f"{package}.png"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return QIcon(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return None

    def _start_icon_loading(self):
        """启动图标异步加载 (Start async icon loading)"""
        if not self.icon_queue:
            return
        self.icon_loading_active = True
        self._process_icon_queue()

    def _stop_icon_workers(self):
        """停止所有图标加载线程 (Stop all icon loading threads)"""
        self.icon_loading_active = False
        for worker in self.icon_workers:
            if worker.isRunning():
                worker.quit()
                worker.wait(100)
        self.icon_workers.clear()

    def _process_icon_queue(self):
        """处理图标加载队列 (Process icon loading queue)"""
        if not self.icon_loading_active or not self.icon_queue:
            self.icon_loading_active = False
            return
        max_workers = 3   # 最多同时运行3个线程
        while len(self.icon_workers) < max_workers and self.icon_queue:
            package, apk_path, table, row = self.icon_queue.pop(0)
            worker = IconLoaderThread(self.adb_client, package, apk_path, self.serial)
            worker.icon_ready.connect(self._on_icon_loaded)
            worker.finished.connect(lambda w=worker: self._worker_finished(w))
            self.icon_workers.append(worker)
            worker.start()

    def _on_icon_loaded(self, package: str, data: bytes):
        """图标加载完成 (Callback when icon is loaded)"""
        # 写入缓存 (Save to cache)
        icon_path = self.ICON_CACHE_DIR / f"{package}.png"
        try:
            with open(icon_path, "wb") as f:
                f.write(data)
        except Exception as e:
            print(f"Failed to cache icon for {package}: {e}")
        # 更新 UI (Update table icons)
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        scaled = pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon(scaled)
        self._update_icon_in_table(self.user_table, package, icon)
        self._update_icon_in_table(self.system_table, package, icon)

    def _update_icon_in_table(self, table: QTableWidget, package: str, icon: QIcon):
        """更新表格中指定包名的图标 (Update icon for a package in table)"""
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item and item.data(Qt.UserRole) == package:
                icon_item = table.item(row, 0)
                if icon_item:
                    icon_item.setIcon(icon)

    def _worker_finished(self, worker):
        """工作线程结束，清理并继续处理队列 (Worker finished callback)"""
        if worker in self.icon_workers:
            self.icon_workers.remove(worker)
        worker.deleteLater()
        self._process_icon_queue()

    # ========== 搜索与过滤 (Search & Filter) ==========

    def filter_apps(self, apps: List[Dict]) -> List[Dict]:
        """根据当前搜索文本过滤应用 (Filter apps by search text)"""
        if not self.current_filter:
            return apps
        try:
            if self.use_regex:
                pattern = re.compile(self.current_filter, re.IGNORECASE)
                return [app for app in apps if pattern.search(app["name"]) or pattern.search(app["package"])]
            else:
                lower = self.current_filter.lower()
                return [app for app in apps if lower in app["name"].lower() or lower in app["package"].lower()]
        except re.error:
            QMessageBox.warning(self, "正则表达式错误", f"无效的正则表达式: {self.current_filter}")
            return apps

    def on_search_text_changed(self, text: str):
        self.current_filter = text.strip()
        self.refresh_display()

    def on_regex_toggled(self, checked: bool):
        self.use_regex = checked
        self.refresh_display()

    def refresh_display(self):
        """刷新两个表格的显示 (Refresh both tables)"""
        if self.user_apps is not None:
            self.populate_table(self.user_table, self.user_apps)
        if self.system_apps is not None:
            self.populate_table(self.system_table, self.system_apps)

    # ========== 右键菜单 (Context Menu) ==========

    def show_context_menu(self, position):
        """显示右键菜单 (Show context menu)"""
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        selected_rows = table.selectedItems()
        if not selected_rows:
            return
        packages = set()
        for item in selected_rows:
            row = item.row()
            pkg_item = table.item(row, 2)   # 包名在第3列
            if pkg_item:
                packages.add(pkg_item.text())
        if not packages:
            return

        menu = QMenu()
        copy_action = QAction("复制包名", self)
        copy_action.triggered.connect(lambda: self.copy_package_names(packages))
        menu.addAction(copy_action)

        uninstall_action = QAction("卸载", self)
        uninstall_action.triggered.connect(lambda: self.uninstall_apps(packages))
        menu.addAction(uninstall_action)

        clear_data_action = QAction("清除数据", self)
        clear_data_action.triggered.connect(lambda: self.clear_app_data(packages))
        menu.addAction(clear_data_action)

        menu.addSeparator()

        run_action = QAction("运行", self)
        run_action.triggered.connect(lambda: self.run_apps(packages, as_root=False))
        menu.addAction(run_action)

        run_root_action = QAction("以 root 权限运行", self)
        run_root_action.triggered.connect(lambda: self.run_apps(packages, as_root=True))
        menu.addAction(run_root_action)

        export_action = QAction("导出APK", self)
        export_action.triggered.connect(lambda: self.export_apks(packages))
        menu.addAction(export_action)

        menu.exec_(table.viewport().mapToGlobal(position))

    def copy_package_names(self, packages: set):
        """复制包名到剪贴板 (Copy package names to clipboard)"""
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(packages))
        QMessageBox.information(self, "提示", f"已复制 {len(packages)} 个包名到剪贴板")

    # ========== 应用操作 (App Operations) ==========

    def uninstall_apps(self, packages: set):
        """卸载选中的应用 (Uninstall selected apps)"""
        if not packages:
            return
        pkg_list = "\n".join(packages)
        reply = QMessageBox.question(self, "确认卸载", f"确定要卸载以下应用吗？\n{pkg_list}",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for pkg in packages:
                self.adb_client.uninstall(pkg, self.serial,
                                          callback=lambda code, out, err, p=pkg: self._on_uninstall_finished(code, out, err, p))

    def _on_uninstall_finished(self, exit_code, stdout, stderr, pkg=None):
        if exit_code == 0:
            QMessageBox.information(self, "卸载成功", f"应用 {pkg} 已卸载")
            self.load_apps()
        else:
            QMessageBox.warning(self, "卸载失败", f"卸载 {pkg} 失败:\n{stderr}")

    def clear_app_data(self, packages: set):
        """清除选中应用的数据 (Clear app data)"""
        if not packages:
            return
        pkg_list = "\n".join(packages)
        reply = QMessageBox.question(self, "确认清除数据", f"确定要清除以下应用的数据吗？\n{pkg_list}\n\n清除后应用将恢复初始状态。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for pkg in packages:
                self.adb_client.shell(f"pm clear {pkg}", self.serial,
                                      callback=lambda code, out, err, p=pkg: self._on_clear_finished(code, out, err, p))

    def _on_clear_finished(self, exit_code, stdout, stderr, pkg):
        if exit_code == 0 and "Success" in stdout:
            QMessageBox.information(self, "清除成功", f"应用 {pkg} 数据已清除")
        else:
            QMessageBox.warning(self, "清除失败", f"清除 {pkg} 数据失败:\n{stderr}")

    def export_apks(self, packages: set):
        """导出选中应用的APK文件 (Export APK files)"""
        if not packages:
            return
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dir_path:
            return
        for pkg in packages:
            out = self.adb_client.shell_sync(f"pm path {pkg}", self.serial, timeout=5)
            if out.startswith("package:"):
                apk_path = out[8:].strip().split('\n')[0]
                local_filename = f"{pkg}.apk"
                local_path = f"{dir_path}/{local_filename}"
                self.adb_client.pull(apk_path, local_path, self.serial,
                                     callback=lambda code, out, err, p=pkg, l=local_path: self._on_export_finished(code, out, err, p, l))
            else:
                QMessageBox.warning(self, "导出失败", f"无法获取 {pkg} 的APK路径，输出：{out}")

    def _on_export_finished(self, exit_code, stdout, stderr, pkg, local_path):
        if exit_code == 0:
            QMessageBox.information(self, "导出成功", f"{pkg} 已保存到 {local_path}")
        else:
            QMessageBox.warning(self, "导出失败", f"导出 {pkg} 失败:\n{stderr}")

    def run_apps(self, packages: set, as_root: bool = False):
        """
        启动应用（支持普通运行或 root 运行）
        Launch app (with optional root)
        """
        if not packages:
            return
        for pkg in packages:
            if as_root:
                cmd = f"su -c 'am start -n {pkg}/$(pm resolve-activity --brief {pkg} | tail -1)'"
            else:
                cmd = f"am start -n {pkg}/$(pm resolve-activity --brief {pkg} | tail -1)"
            self.adb_client.shell(cmd, self.serial,
                                  callback=lambda code, out, err, p=pkg: self._on_run_finished(code, out, err, p))

    def _on_run_finished(self, exit_code, stdout, stderr, pkg):
        if exit_code == 0:
            QMessageBox.information(self, "启动成功", f"应用 {pkg} 已启动")
        else:
            QMessageBox.warning(self, "启动失败", f"启动 {pkg} 失败:\n{stderr}")

    # ========== 拖拽安装 (Drag & Drop Install) ==========

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件：接受 .apk 文件"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith('.apk'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """拖拽放下事件：安装 APK"""
        apk_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith('.apk'):
                apk_paths.append(path)
        if apk_paths:
            self.install_apks(apk_paths)

    def install_apks(self, apk_paths: List[str]):
        """安装一个或多个 APK 文件"""
        if not apk_paths:
            return
        reply = QMessageBox.question(self, "确认安装", f"确定要安装 {len(apk_paths)} 个APK吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        for apk_path in apk_paths:
            filename = os.path.basename(apk_path)
            progress = QProgressDialog(f"正在安装 {filename}...", "取消", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setCancelButtonText("取消")
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setRange(0, 0)
            progress.show()

            args = [self.adb_client.adb_path]
            if self.serial:
                args.extend(['-s', self.serial])
            args.extend(['install', '-r', apk_path])

            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            success = False
            error_msg = ""
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if progress.wasCanceled():
                    process.terminate()
                    break
                if line:
                    progress.setLabelText(f"正在安装 {filename}\n{line.strip()}")
                    if "Success" in line:
                        success = True
                    elif "Failure" in line:
                        error_msg = line.strip()
            process.wait()
            progress.close()

            if progress.wasCanceled():
                QMessageBox.information(self, "取消", f"已取消安装 {filename}")
            elif success:
                QMessageBox.information(self, "安装成功", f"{filename} 安装成功")
                self.load_apps()   # 刷新列表
            else:
                QMessageBox.warning(self, "安装失败", f"{filename} 安装失败\n{error_msg}")
