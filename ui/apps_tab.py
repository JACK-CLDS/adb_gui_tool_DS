"""
ui/apps_tab.py - 应用管理控件

功能：
    - 两个选项卡：系统应用、用户应用
    - 应用列表显示（应用名称、包名、版本、安装时间等）
    - 搜索过滤（支持正则表达式）
    - 右键菜单：复制包名、卸载、清除数据、导出APK（占位）
    - 支持多选应用
    - 拖拽安装APK（预留）

依赖：PyQt5, core.adb_client, utils.config_manager
"""

import re
import os
import subprocess
from typing import List, Dict, Optional

from PyQt5.QtWidgets import QStyle

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton,
    QMenu, QAction, QMessageBox, QApplication, QFileDialog,
    QProgressDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QMimeData
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from core.adb_client import AdbClient
from utils.config_manager import ConfigManager


class AppsTab(QWidget):
    """应用管理控件，可嵌入设备窗口的选项卡"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.system_apps = []      # 存储系统应用数据
        self.user_apps = []        # 存储用户应用数据
        self.current_filter = ""   # 当前搜索过滤文本
        self.use_regex = False     # 是否使用正则表达式

        self.init_ui()
        self.load_apps()  # 异步加载应用列表

    def init_ui(self):
        """初始化界面布局"""
        layout = QVBoxLayout(self)

        # 顶部搜索栏
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

        # 选项卡：系统应用 / 用户应用
        self.tab_widget = QTabWidget()
        self.system_tab = QWidget()
        self.user_tab = QWidget()
        self.tab_widget.addTab(self.system_tab, "系统应用")
        self.tab_widget.addTab(self.user_tab, "用户应用")
        layout.addWidget(self.tab_widget)

        # 初始化两个表格
        self.system_table = self.create_app_table()
        self.user_table = self.create_app_table()
        self.setup_table_layout(self.system_tab, self.system_table)
        self.setup_table_layout(self.user_tab, self.user_table)

        # 启用拖拽安装（接受文件拖放）
        self.setAcceptDrops(True)

    def create_app_table(self) -> QTableWidget:
        table = QTableWidget()
#        table.setColumnCount(5)
        table.setColumnCount(2)
        table.setSortingEnabled(True)
        table.setHorizontalHeaderLabels(["应用名称", "包名"])
#        table.setHorizontalHeaderLabels(["应用名称", "包名", "版本名称", "版本号", "安装时间"])
        # 允许用户手动调整列宽
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        # 设置初始列宽（可根据需要调整）
        table.setColumnWidth(0, 200)  # 应用名称
        table.setColumnWidth(1, 500)  # 包名
#        table.setColumnWidth(2, 100)  # 版本名称
#        table.setColumnWidth(3, 80)   # 版本号
#        table.setColumnWidth(4, 120)  # 安装时间
        # 可选：让最后一列拉伸填充剩余空间，但用户仍可手动调整
        # table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_context_menu)
        # 固定垂直表头宽度（行号列）
        table.verticalHeader().setFixedWidth(40)  # 设置固定宽度为40像素
        table.verticalHeader().setDefaultSectionSize(30)  # 固定行高为30像素
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)  # 禁止自动调整
        return table

    def setup_table_layout(self, parent: QWidget, table: QTableWidget):
        """将表格添加到父布局中"""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(table)

    def load_apps(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("加载中...")
        
        try:
            # 获取用户应用（带版本号，但可能不支持，先不加版本号）
            user_out = self.adb_client.shell_sync("pm list packages -3", self.serial, timeout=10)
            print(f"[AppsTab] User packages output (length {len(user_out)}): {user_out[:200]}")
            self.user_apps = self._parse_packages(user_out)
            self.populate_table(self.user_table, self.user_apps, "user")
        except Exception as e:
            print(f"[AppsTab] Error loading user apps: {e}")
            self.user_apps = []
        
        try:
            sys_out = self.adb_client.shell_sync("pm list packages -s", self.serial, timeout=10)
            print(f"[AppsTab] System packages output (length {len(sys_out)}): {sys_out[:200]}")
            self.system_apps = self._parse_packages(sys_out)
            self.populate_table(self.system_table, self.system_apps, "system")
        except Exception as e:
            print(f"[AppsTab] Error loading system apps: {e}")
            self.system_apps = []
        
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("刷新")
        
    def _parse_packages_with_version(self, output: str) -> List[Dict]:
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            # 格式: package:com.example versionCode=123
            parts = line.split()
            pkg = parts[0][8:]  # 去掉 "package:"
            version_code = ""
            for part in parts:
                if part.startswith("versionCode="):
                    version_code = part.split("=")[1]
                    break
            packages.append({
                "package": pkg,
                "name": self._get_app_name_from_package(pkg),
                "version_name": "",
                "version_code": version_code,
                "install_time": ""
            })
        return packages

    def _parse_packages(self, output: str) -> List[Dict]:
        """解析 pm list packages 输出，返回包名列表（字典格式）"""
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkg = line[8:]  # 去掉 "package:" 前缀
                packages.append({
                    "package": pkg,
                    "name": self._get_app_name_from_package(pkg),  # 临时用包名代替应用名
                    "version_name": "",
                    "version_code": "",
                    "install_time": ""
                })
        return packages

    def _get_app_name_from_package(self, pkg: str) -> str:
        """从包名获取应用名称（简化：取最后一段，或保留包名）"""
        # 后续可以通过 dumpsys package 获取真实名称，现在先简单处理
        parts = pkg.split('.')
        return parts[-1] if parts else pkg

    def populate_table(self, table: QTableWidget, apps: List[Dict], app_type: str):
        filtered_apps = self.filter_apps(apps)
        # 手动按应用名称（不区分大小写）排序
        filtered_apps.sort(key=lambda x: x.get("name", "").lower())
        table.setRowCount(len(filtered_apps))
        for row, app in enumerate(filtered_apps):
            name_item = QTableWidgetItem(app.get("name", ""))
            icon = self.style().standardIcon(QStyle.SP_FileIcon)
            name_item.setIcon(icon)
            name_item.setData(Qt.UserRole, app["package"])
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(app["package"]))

    def filter_apps(self, apps: List[Dict]) -> List[Dict]:
        """根据搜索文本过滤应用列表（名称或包名匹配）"""
        if not self.current_filter:
            return apps
        try:
            if self.use_regex:
                pattern = re.compile(self.current_filter, re.IGNORECASE)
                return [app for app in apps if pattern.search(app["name"]) or pattern.search(app["package"])]
            else:
                lower_filter = self.current_filter.lower()
                return [app for app in apps if lower_filter in app["name"].lower() or lower_filter in app["package"].lower()]
        except re.error:
            # 正则表达式无效时，返回空列表或原列表？这里返回原列表并提示
            QMessageBox.warning(self, "正则表达式错误", f"无效的正则表达式: {self.current_filter}")
            return apps

    def on_search_text_changed(self, text: str):
        """搜索框文本变化时触发过滤"""
        self.current_filter = text.strip()
        self.refresh_display()

    def on_regex_toggled(self, checked: bool):
        """正则表达式复选框状态变化"""
        self.use_regex = checked
        self.refresh_display()

    def refresh_display(self):
        """刷新两个表格的显示（基于当前过滤条件）"""
        if self.user_apps is not None:
            self.populate_table(self.user_table, self.user_apps, "user")
        if self.system_apps is not None:
            self.populate_table(self.system_table, self.system_apps, "system")

    def show_context_menu(self, position):
        """显示右键菜单"""
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        selected_rows = table.selectedItems()
        if not selected_rows:
            return
        # 获取选中的包名列表（去重）
        packages = set()
        for item in selected_rows:
            row = item.row()
            pkg_item = table.item(row, 1)  # 包名列是第1列（索引1）
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

        export_action = QAction("导出APK", self)
        export_action.triggered.connect(lambda: self.export_apks(packages))
        menu.addAction(export_action)

        menu.exec_(table.viewport().mapToGlobal(position))

    def copy_package_names(self, packages: set):
        """复制包名到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(packages))
        QMessageBox.information(self, "提示", f"已复制 {len(packages)} 个包名到剪贴板")

    def uninstall_apps(self, packages: set):
        """卸载选中的应用（需要用户确认）"""
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
            self.load_apps()  # 刷新列表
        else:
            QMessageBox.warning(self, "卸载失败", f"卸载 {pkg} 失败:\n{stderr}")

    def clear_app_data(self, packages: set):
        """清除应用数据（需要用户确认）"""
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
        if not packages:
            return
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dir_path:
            return
        for pkg in packages:
            # 同步获取APK路径
            out = self.adb_client.shell_sync(f"pm path {pkg}", self.serial, timeout=5)
            print(f"[DEBUG] pm path for {pkg}: {out}")
            if out.startswith("package:"):
                # 去掉 "package:" 前缀，并处理可能的换行（多个路径）
                apk_path = out[8:].strip().split('\n')[0]
                # 拉取APK
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

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件：接受.apk文件拖放"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith('.apk'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """拖拽放下事件：安装APK"""
        apk_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith('.apk'):
                apk_paths.append(path)
        if apk_paths:
            self.install_apks(apk_paths)

    def install_apks(self, apk_paths: List[str]):
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
            progress.setRange(0, 0)  # 不确定进度
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
                self.load_apps()  # 刷新应用列表
            else:
                QMessageBox.warning(self, "安装失败", f"{filename} 安装失败\n{error_msg}")
