"""
ui/main_window.py - 主启动窗口

功能：
    - 显示设备列表（表格形式）
    - 左侧可折叠侧边栏：历史记录、收藏设备（支持分组）
    - 底部地址输入框：连接网络设备
    - 工具栏：重启 ADB、Kill ADB、全局设置、刷新
    - 程序日志窗口（可停靠）
    - 多选设备后打开设备控制窗口

依赖：PyQt5, core.device_manager, core.adb_client, utils.config_manager, utils.system_utils
"""

import sys
from typing import List, Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit, QToolBar, QAction, QDockWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QInputDialog,
    QAbstractItemView, QApplication, QDialog, QTextBrowser
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSettings, QPoint, QProcess
from PyQt5.QtGui import QIcon, QKeySequence

from core.adb_client import AdbClient
from core.device_manager import DeviceManager
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class MainWindow(QMainWindow):
    """主启动窗口"""

    def __init__(self, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.adb_client = adb_client
        self.device_manager = DeviceManager(adb_client, self)
        self.device_manager.devices_updated.connect(self.update_device_table)
        
        # 存储当前打开的设备窗口列表（用于管理）
        self.device_windows = []  # 每个元素为 (serial, window)
        
        self.init_ui()
        self.init_signals()
        self.load_settings()
        self.device_manager.refresh_devices()  # 立即刷新一次
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("ADB GUI Tool - 设备管理")
        # 调整窗口宽度：原来是 900，增加 1/3 到 1200 (undo change)
        self.setMinimumSize(800, 600)
        
        # 创建中央部件（包含设备表格和侧边栏）
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建水平分割器（左侧侧边栏，右侧设备表格）
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧侧边栏（可折叠的历史和收藏）
        self.sidebar_widget = self.create_sidebar()
        splitter.addWidget(self.sidebar_widget)
        
        # 右侧区域：设备表格 + 底部连接栏
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 设备表格
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(3)
        self.device_table.setHorizontalHeaderLabels(["设备名称", "序列号/地址", "状态"])
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 支持多选
        self.device_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.device_table.doubleClicked.connect(self.on_device_double_clicked)
        right_layout.addWidget(self.device_table)
        
        # 底部地址输入和连接按钮
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("输入 IP:端口 或 设备序列号，然后按回车连接")
        self.address_input.returnPressed.connect(self.connect_to_address)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.connect_to_address)
        bottom_layout.addWidget(self.address_input)
        bottom_layout.addWidget(self.connect_btn)
        right_layout.addWidget(bottom_widget)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 600])  # 左侧250px，右侧950px（适应更宽窗口）(undo change)
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建程序日志停靠窗口
        self.create_log_dock()
        
        # 应用样式表（可选，后期美化）
        self.apply_stylesheet()
    
    def create_sidebar(self):
        """创建左侧可折叠侧边栏（历史记录和收藏）"""
        from PyQt5.QtWidgets import QFrame, QScrollArea
        
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # 历史记录分组（可折叠，使用 QTreeWidget 实现分组折叠效果）
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabel("历史连接")
        self.history_tree.setIndentation(10)
        self.history_tree.setMaximumHeight(200)
        self.history_tree.itemDoubleClicked.connect(self.on_history_item_clicked)
        layout.addWidget(self.history_tree)
        
        # 收藏分组（支持多分组）
        self.favorites_tree = QTreeWidget()
        self.favorites_tree.setHeaderLabel("收藏设备")
        self.favorites_tree.setIndentation(10)
        self.favorites_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.favorites_tree.customContextMenuRequested.connect(self.show_favorites_menu)
        self.favorites_tree.itemDoubleClicked.connect(self.on_favorite_item_clicked)
        layout.addWidget(self.favorites_tree)
        
        # 刷新侧边栏内容
        self.refresh_history_tree()
        self.refresh_favorites_tree()
        
        return sidebar
    
    def create_toolbar(self):
        """创建顶部工具栏"""
        toolbar = self.addToolBar("主要工具")
        toolbar.setMovable(False)
        
        # 刷新按钮
        refresh_action = QAction("刷新设备", self)
        refresh_action.triggered.connect(self.device_manager.manual_refresh)
        toolbar.addAction(refresh_action)
        
        # 重启 ADB 服务
        restart_adb_action = QAction("重启 ADB", self)
        restart_adb_action.triggered.connect(self.restart_adb_server)
        toolbar.addAction(restart_adb_action)
        
        # Kill ADB 服务
        kill_adb_action = QAction("Kill ADB", self)
        kill_adb_action.triggered.connect(self.kill_adb_server)
        toolbar.addAction(kill_adb_action)
        
        toolbar.addSeparator()
        
        # 全局设置
        settings_action = QAction("全局设置", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        toolbar.addAction(settings_action)
        
        # 关于
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.open_about_dialog)
        toolbar.addAction(about_action)
    
    def create_log_dock(self):
        """创建可停靠的程序日志窗口"""
        self.log_dock = QDockWidget("程序日志", self)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_dock.setWidget(self.log_text)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        # 默认显示
        self.log_dock.show()
    
    def apply_stylesheet(self):
        """应用简单的样式表（可替换为 QSS 文件）"""
        self.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QTreeWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QPushButton {
                padding: 4px 8px;
            }
        """)
    
    def init_signals(self):
        """初始化信号连接（除了已连接的之外）"""
        pass
    
    def update_device_table(self, devices: List[tuple]):
        """
        更新设备表格
        devices: [(serial, state, device_name), ...]
        """
        self.device_table.setRowCount(len(devices))
        for row, (serial, state, name) in enumerate(devices):
            # 设备名称
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, serial)  # 存储 serial
            self.device_table.setItem(row, 0, name_item)
            # 序列号
            serial_item = QTableWidgetItem(serial)
            self.device_table.setItem(row, 1, serial_item)
            # 状态
            state_item = QTableWidgetItem(state)
            # 根据状态着色
            if state == "device":
                state_item.setForeground(Qt.darkGreen)
            elif state == "offline":
                state_item.setForeground(Qt.darkYellow)
            elif state == "unauthorized":
                state_item.setForeground(Qt.red)
            self.device_table.setItem(row, 2, state_item)
    
    def refresh_history_tree(self):
        """刷新历史记录侧边栏"""
        self.history_tree.clear()
        history = ConfigManager.get_history()
        for addr in history:
            item = QTreeWidgetItem([addr])
            self.history_tree.addTopLevelItem(item)
    
    def refresh_favorites_tree(self):
        """刷新收藏设备侧边栏（支持分组）"""
        self.favorites_tree.clear()
        favorites = ConfigManager.get_favorites()
        for group_name, devices in favorites.items():
            group_item = QTreeWidgetItem([group_name])
            group_item.setExpanded(True)
            self.favorites_tree.addTopLevelItem(group_item)
            for dev in devices:
                child = QTreeWidgetItem([dev])
                group_item.addChild(child)
    
    def on_history_item_clicked(self, item, column):
        """双击历史记录项，自动填入地址输入框并连接"""
        addr = item.text(0)
        self.address_input.setText(addr)
        self.connect_to_address()
    
    def on_favorite_item_clicked(self, item, column):
        """双击收藏项，如果是设备则连接，如果是分组则展开/折叠（默认行为）"""
        if item.parent() is not None:  # 是设备项
            addr = item.text(0)
            self.address_input.setText(addr)
            self.connect_to_address()
        # 如果是分组项，双击会展开/折叠，无需额外处理
    
    def show_favorites_menu(self, position):
        """显示收藏设备的右键菜单（添加分组、删除分组、删除设备等）"""
        item = self.favorites_tree.itemAt(position)
        menu = QMenu()
        if item is None:
            # 在空白区域右键：添加分组
            add_group_action = menu.addAction("新建分组")
            add_group_action.triggered.connect(self.add_favorite_group)
        else:
            if item.parent() is None:
                # 分组项
                add_device_action = menu.addAction("添加设备到此分组")
                add_device_action.triggered.connect(lambda: self.add_device_to_group(item.text(0)))
                rename_group_action = menu.addAction("重命名分组")
                rename_group_action.triggered.connect(lambda: self.rename_favorite_group(item.text(0)))
                delete_group_action = menu.addAction("删除分组")
                delete_group_action.triggered.connect(lambda: self.delete_favorite_group(item.text(0)))
                menu.addAction(add_device_action)
                menu.addAction(rename_group_action)
                menu.addAction(delete_group_action)
            else:
                # 设备项
                group_name = item.parent().text(0)
                device_addr = item.text(0)
                remove_action = menu.addAction("从收藏中移除")
                remove_action.triggered.connect(lambda: self.remove_favorite_device(group_name, device_addr))
                menu.addAction(remove_action)
        menu.exec_(self.favorites_tree.viewport().mapToGlobal(position))
    
    def add_favorite_group(self):
        """添加新的收藏分组"""
        name, ok = QInputDialog.getText(self, "新建分组", "请输入分组名称:")
        if ok and name:
            favorites = ConfigManager.get_favorites()
            if name not in favorites:
                favorites[name] = []
                ConfigManager.save_favorites(favorites)
                self.refresh_favorites_tree()
    
    def add_device_to_group(self, group_name):
        """将当前地址输入框中的设备添加到指定分组"""
        addr = self.address_input.text().strip()
        if not addr:
            QMessageBox.warning(self, "提示", "请先在下方输入框填写设备地址")
            return
        ConfigManager.add_favorite(group_name, addr)
        self.refresh_favorites_tree()
    
    def rename_favorite_group(self, old_name):
        """重命名分组"""
        new_name, ok = QInputDialog.getText(self, "重命名分组", "新名称:", text=old_name)
        if ok and new_name and new_name != old_name:
            favorites = ConfigManager.get_favorites()
            if new_name in favorites:
                QMessageBox.warning(self, "错误", "分组名已存在")
                return
            favorites[new_name] = favorites.pop(old_name)
            ConfigManager.save_favorites(favorites)
            self.refresh_favorites_tree()
    
    def delete_favorite_group(self, group_name):
        """删除分组（会同时删除其中的所有设备）"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除分组「{group_name}」及其所有设备吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            favorites = ConfigManager.get_favorites()
            if group_name in favorites:
                del favorites[group_name]
                ConfigManager.save_favorites(favorites)
                self.refresh_favorites_tree()
    
    def remove_favorite_device(self, group_name, device_addr):
        """从分组中移除单个设备"""
        ConfigManager.remove_favorite(group_name, device_addr)
        self.refresh_favorites_tree()
    
    def connect_to_address(self):
        """连接网络设备（或本地模拟器）"""
        addr = self.address_input.text().strip()
        if not addr:
            return
        # 如果地址不包含冒号且不是模拟器，自动添加默认端口 5555
        if ":" not in addr and not addr.startswith("emulator-"):
            addr = f"{addr}:5555"
        self.log_message(f"正在连接 {addr} ...")
        self.adb_client.connect_device(addr, callback=self.on_connect_result)
    
    def on_connect_result(self, success, message):
        """连接结果回调"""
        if success:
            self.log_message(f"连接成功: {message}")
            self.device_manager.manual_refresh()  # 刷新设备列表
            # 添加到历史记录
            ConfigManager.add_history(self.address_input.text().strip())
            self.refresh_history_tree()
            self.address_input.clear()
        else:
            self.log_message(f"连接失败: {message}")
            QMessageBox.warning(self, "连接失败", message)
    
    def restart_adb_server(self):
        """重启 ADB 服务"""
        # 检查是否需要关闭已打开的设备窗口
        if self.device_windows:
            reply = QMessageBox.question(self, "确认重启", "重启 ADB 将关闭所有已打开的设备窗口，是否继续？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            # 关闭所有设备窗口
            for serial, win in self.device_windows:
                win.close()
            self.device_windows.clear()
        # 执行 adb kill-server 和 adb start-server
        self.log_message("正在重启 ADB 服务...")
        proc = QProcess(self)
        proc.finished.connect(lambda code: self._after_adb_kill(code, proc))
        proc.start(self.adb_client.adb_path, ["kill-server"])
    
    def _after_adb_kill(self, exit_code, proc):
        """kill-server 完成后启动 server"""
        self.log_message("ADB 服务已停止，正在启动...")
        proc2 = QProcess(self)
        proc2.finished.connect(lambda code: self._after_adb_start(code, proc2))
        proc2.start(self.adb_client.adb_path, ["start-server"])
    
    def _after_adb_start(self, exit_code, proc):
        if exit_code == 0:
            self.log_message("ADB 服务已启动")
            self.device_manager.manual_refresh()
        else:
            self.log_message("ADB 服务启动失败")
    
    def kill_adb_server(self):
        """Kill ADB 服务"""
        reply = QMessageBox.question(self, "确认操作", "确定要停止 ADB 服务吗？所有设备将断开。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log_message("正在停止 ADB 服务...")
            proc = QProcess(self)
            proc.finished.connect(lambda: self.log_message("ADB 服务已停止"))
            proc.start(self.adb_client.adb_path, ["kill-server"])
            # 清空设备列表
            self.device_table.setRowCount(0)
            # 关闭所有设备窗口
            for serial, win in self.device_windows:
                win.close()
            self.device_windows.clear()
        # 注意：如果用户点击“否”，这里什么都不做，不应该退出程序
        # 之前的错误是因为缺少 QProcess 导入，现在已修复
    
    def on_device_double_clicked(self, index):
        """双击设备行，打开该设备的控制窗口"""
        row = index.row()
        serial_item = self.device_table.item(row, 1)
        if serial_item:
            serial = serial_item.text()
            self.open_device_window(serial)
    
    def open_device_window(self, serial: str):
        """打开指定设备的控制窗口"""
        # 避免重复打开同一个设备窗口（可根据需要决定是否允许多窗口）
        for s, win in self.device_windows:
            if s == serial and win.isVisible():
                win.raise_()
                win.activateWindow()
                return
        # TODO: 导入 DeviceWindow 类
        # from ui.device_window import DeviceWindow
        # win = DeviceWindow(serial, self.adb_client, self)
        # 临时占位：显示提示
        QMessageBox.information(self, "提示", f"设备 {serial} 的控制窗口尚未实现。")
        return
        # win.show()
        # self.device_windows.append((serial, win))
        # win.destroyed.connect(lambda: self.remove_device_window(serial, win))
    
    def remove_device_window(self, serial, window):
        """从列表中移除已关闭的设备窗口"""
        self.device_windows = [(s, w) for s, w in self.device_windows if w != window]
    
    def open_settings_dialog(self):
        """打开全局设置对话框（后续实现）"""
        QMessageBox.information(self, "提示", "全局设置对话框尚未实现。")
    
    def open_about_dialog(self):
        """打开关于对话框（显示系统信息、adb版本等）"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        # 加宽 1/3：假设原来默认宽度约 450，现在设为 600
        dialog.resize(450, 200)
        layout = QVBoxLayout(dialog)
        # 获取系统信息
        import platform
        sys_info = f"操作系统: {platform.system()} {platform.release()}\nPython版本: {sys.version.split()[0]}"
        # 获取 adb 版本
        ok, version = SystemUtils.check_adb_version(self.adb_client.adb_path)
        adb_info = f"ADB路径: {self.adb_client.adb_path}\nADB版本: {version if ok else '获取失败'}"
        text = f"{sys_info}\n\n{adb_info}"
        text_browser = QTextBrowser()
        text_browser.setText(text)
        layout.addWidget(text_browser)
        btn = QPushButton("确定")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        dialog.exec_()
    
    def log_message(self, msg: str):
        """向程序日志窗口添加一条消息（带时间戳）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def load_settings(self):
        """加载窗口大小、位置等配置"""
        settings = ConfigManager.get_settings()
        geometry = settings.get("window_geometry", {})
        if geometry:
            self.resize(geometry.get("width", 800), geometry.get("height", 600))
            pos = QPoint(geometry.get("x", 100), geometry.get("y", 100))
            self.move(pos)
    
    def closeEvent(self, event):
        """保存窗口几何配置"""
        geom = self.geometry()
        ConfigManager.set_setting("window_geometry", {
            "width": geom.width(),
            "height": geom.height(),
            "x": geom.x(),
            "y": geom.y()
        })
        # 停止定时器
        self.device_manager.stop_refresh()
        event.accept()
