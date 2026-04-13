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
from typing import List, Dict, Optional

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
        """创建应用列表表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["应用名称", "包名", "版本名称", "版本号", "安装时间"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)  # 支持多选
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_context_menu)
        return table

    def setup_table_layout(self, parent: QWidget, table: QTableWidget):
        """将表格添加到父布局中"""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(table)

    def load_apps(self):
        """异步加载设备上的应用列表（系统应用和用户应用）"""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("加载中...")
        # 使用 pm list packages 获取包名列表，再获取详细信息（后续可优化）
        # 为了简化，先获取所有包名，再通过 dumpsys package 获取详情（较慢）
        # 实际可以使用 adb shell pm list packages -f -3 等，但为了结构清晰，先获取包名，再分批查询
        # 这里我们采用简单方法：只显示包名和名称，版本等后续再扩展
        # 用户应用：
        self.adb_client.shell("pm list packages -3", self.serial,
                              callback=lambda code, out, err: self._on_user_packages_loaded(out))
        # 系统应用：
        self.adb_client.shell("pm list packages -s", self.serial,
                              callback=lambda code, out, err: self._on_system_packages_loaded(out))

    def _on_user_packages_loaded(self, output: str):
        """处理用户应用包名列表"""
        packages = self._parse_packages(output)
        self.user_apps = packages
        self.populate_table(self.user_table, packages, "user")
        self._check_all_loaded()

    def _on_system_packages_loaded(self, output: str):
        """处理系统应用包名列表"""
        packages = self._parse_packages(output)
        self.system_apps = packages
        self.populate_table(self.system_table, packages, "system")
        self._check_all_loaded()

    def _check_all_loaded(self):
        """检查两个列表是否都加载完成，恢复刷新按钮"""
        if self.user_apps is not None and self.system_apps is not None:
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("刷新")

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
        """将应用数据填充到表格中，并根据当前过滤条件过滤"""
        # 应用过滤
        filtered_apps = self.filter_apps(apps)
        table.setRowCount(len(filtered_apps))
        for row, app in enumerate(filtered_apps):
            name_item = QTableWidgetItem(app.get("name", ""))
            name_item.setData(Qt.UserRole, app["package"])  # 存储包名
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(app["package"]))
            table.setItem(row, 2, QTableWidgetItem(app.get("version_name", "")))
            table.setItem(row, 3, QTableWidgetItem(str(app.get("version_code", ""))))
            table.setItem(row, 4, QTableWidgetItem(app.get("install_time", "")))
        # 调整列宽
        table.resizeColumnsToContents()

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
                self.adb_client.uninstall(pkg, self.serial, callback=self._on_uninstall_finished)

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
        """导出APK文件（保存到本地）"""
        if not packages:
            return
        # 选择保存目录
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dir_path:
            return
        for pkg in packages:
            # 获取APK路径
            self.adb_client.shell(f"pm path {pkg}", self.serial,
                                  callback=lambda code, out, err, p=pkg, d=dir_path: self._on_apk_path_loaded(code, out, err, p, d))

    def _on_apk_path_loaded(self, exit_code, stdout, stderr, pkg, save_dir):
        if exit_code == 0 and stdout.startswith("package:"):
            apk_path = stdout[8:].strip()
            # 拉取APK文件
            local_filename = f"{pkg}.apk"
            local_path = f"{save_dir}/{local_filename}"
            self.adb_client.pull(apk_path, local_path, self.serial,
                                 callback=lambda code, out, err, p=pkg, l=local_path: self._on_export_finished(code, out, err, p, l))
        else:
            QMessageBox.warning(self, "导出失败", f"无法获取 {pkg} 的APK路径")

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
        """安装多个APK，显示进度对话框"""
        if not apk_paths:
            return
        # 确认安装
        reply = QMessageBox.question(self, "确认安装", f"确定要安装 {len(apk_paths)} 个APK吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        # 创建进度对话框
        progress = QProgressDialog("正在安装...", "取消", 0, len(apk_paths), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        self._install_queue = list(apk_paths)
        self._install_progress = progress
        self._install_current_index = 0
        self._install_next()

    def _install_next(self):
        """安装队列中的下一个APK"""
        if self._install_progress.wasCanceled():
            self._install_progress.close()
            return
        if self._install_current_index >= len(self._install_queue):
            self._install_progress.close()
            QMessageBox.information(self, "安装完成", "所有APK安装完毕")
            self.load_apps()  # 刷新应用列表
            return
        apk_path = self._install_queue[self._install_current_index]
        self._install_progress.setLabelText(f"正在安装: {apk_path}")
        self.adb_client.install(apk_path, self.serial,
                                callback=lambda code, out, err: self._on_install_finished(code, out, err))

    def _on_install_finished(self, exit_code, stdout, stderr):
        if exit_code == 0:
            self._install_current_index += 1
            self._install_progress.setValue(self._install_current_index)
            self._install_next()
        else:
            self._install_progress.close()
            QMessageBox.warning(self, "安装失败", f"安装失败:\n{stderr}")