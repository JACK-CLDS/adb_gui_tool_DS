import sys
from typing import List, Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit, QToolBar, QAction, QDockWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QInputDialog,
    QAbstractItemView, QApplication, QDialog, QTextBrowser, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPoint, QProcess, QEvent
from PyQt5.QtGui import QIcon

from core.adb_client import AdbClient
from core.device_manager import DeviceManager
from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils


class MainWindow(QMainWindow):
    def __init__(self, adb_client: Optional[AdbClient], parent=None):
        #dbg
        print("1: Enter __init__", flush=True)
        
        super().__init__(parent)
        self.adb_client = adb_client
        self.device_manager = None
        self.device_windows = []

        # 在 MainWindow.__init__ 中，如果 self.adb_client 存在
        if self.adb_client:
            self.adb_client.devices_sync(lambda devices: print("Sync devices:", devices))

        #dbg
        print("2: Before init_ui", flush=True)
        
        
        self.init_ui()
        self.init_signals()
        self.load_settings()

        if self.adb_client:
            self.device_manager = DeviceManager(self.adb_client, self)
            self.device_manager.devices_updated.connect(self.update_device_table)
            self.device_manager.refresh_devices()
            self.hide_adb_warning()
        else:
            self.device_manager = None
            self.show_adb_warning()

        # 无论是否有 device_manager，更新按钮状态
        self.update_adb_buttons_state()

    def update_adb_buttons_state(self):
        """根据 device_manager 是否存在，更新按钮启用状态"""
        enabled = self.device_manager is not None
        for action in self.adb_dependent_actions:
            action.setEnabled(enabled)

    def init_ui(self):
        #dbg
        print("3: Enter init_ui", flush=True)
        
        self.setWindowTitle("ADB GUI Tool - 设备管理")
        self.setMinimumSize(800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        self.sidebar_widget = self.create_sidebar()
        splitter.addWidget(self.sidebar_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        #        self.device_table = QTableWidget()
        #        self.device_table.setColumnCount(3)
        #        self.device_table.setHorizontalHeaderLabels(["设备名称", "序列号/地址", "状态"])
        #        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        #        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        #        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        #        self.device_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        #        self.device_table.doubleClicked.connect(self.on_device_double_clicked)
                # 设备表格
        
        #        self.device_table.setContextMenuPolicy(Qt.CustomContextMenu)
        #        self.device_table.customContextMenuRequested.connect(self.show_device_menu)
        
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(3)
        self.device_table.setHorizontalHeaderLabels(["设备名称", "序列号/地址", "状态"])
        # 允许用户手动调整列宽
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        # 设置初始列宽
        self.device_table.setColumnWidth(0, 200)  # 设备名称列
        self.device_table.setColumnWidth(1, 250)  # 序列号/地址列
        self.device_table.setColumnWidth(2, 100)  # 状态列
        # 启用排序
        self.device_table.setSortingEnabled(True)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.device_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.device_table.doubleClicked.connect(self.on_device_double_clicked)
        self.device_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.device_table.customContextMenuRequested.connect(self.show_device_menu)
        right_layout.addWidget(self.device_table)

        # 启用拖拽排序
        self.device_table.setDragEnabled(True)
        self.device_table.setAcceptDrops(True)
        self.device_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.device_table.setDropIndicatorShown(True)
        
        # 事件过滤
        self.device_table.viewport().installEventFilter(self)

        # 上下移动按钮条
        move_layout = QHBoxLayout()
        self.move_up_btn = QPushButton("上移")
        self.move_up_btn.clicked.connect(self.move_device_up)
        self.move_down_btn = QPushButton("下移")
        self.move_down_btn.clicked.connect(self.move_device_down)
        move_layout.addWidget(self.move_up_btn)
        move_layout.addWidget(self.move_down_btn)
        move_layout.addStretch()
        right_layout.addLayout(move_layout)

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
        splitter.setSizes([200, 600])

        #dbg
        print("4: Before create_toolbar", flush=True)
        
        self.create_toolbar()
        self.create_log_dock()
        
        #dbg
        print("5: After create_toolbar", flush=True)


        self.adb_warning_label = QLabel("⚠️ 未找到有效的 ADB，请在「全局设置」中配置 ADB 路径")
        self.adb_warning_label.setStyleSheet("color: red; background-color: #ffeeee; padding: 5px;")
        self.adb_warning_label.setAlignment(Qt.AlignCenter)
        self.adb_warning_label.hide()
        central_layout = self.centralWidget().layout()
        if central_layout:
            central_layout.insertWidget(0, self.adb_warning_label)

        self.apply_stylesheet()

    def on_refresh_clicked(self):
        if self.device_manager:
            self.device_manager.manual_refresh()
        else:
            self.log_message("ADB 未配置，无法刷新设备列表")

    def create_toolbar(self):
        toolbar = self.addToolBar("主要工具")
        toolbar.setMovable(False)

        # 创建按钮（先默认启用，后面再根据情况调整）
        refresh_action = QAction("刷新设备", self)
        refresh_action.triggered.connect(self.on_refresh_clicked)
        toolbar.addAction(refresh_action)

        restart_adb_action = QAction("重启 ADB", self)
        restart_adb_action.triggered.connect(self.restart_adb_server)
        toolbar.addAction(restart_adb_action)

        kill_adb_action = QAction("Kill ADB", self)
        kill_adb_action.triggered.connect(self.kill_adb_server)
        toolbar.addAction(kill_adb_action)

        toolbar.addSeparator()

        settings_action = QAction("全局设置", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        toolbar.addAction(settings_action)

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.open_about_dialog)
        toolbar.addAction(about_action)

        # 保存需要根据 ADB 状态启用的按钮列表
        self.adb_dependent_actions = [refresh_action, restart_adb_action, kill_adb_action]

    def create_log_dock(self):
        self.log_dock = QDockWidget("程序日志", self)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_dock.setWidget(self.log_text)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.show()
        self.statusBar().showMessage("就绪")

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QTableWidget::item:selected { background-color: #3498db; color: white; }
            QTreeWidget::item:selected { background-color: #3498db; color: white; }
            QPushButton { padding: 4px 8px; }
        """)

    def init_signals(self):
        pass

    def show_adb_warning(self):
        self.adb_warning_label.show()

    def hide_adb_warning(self):
        self.adb_warning_label.hide()

    def create_sidebar(self):
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabel("历史连接")
        self.history_tree.setIndentation(10)
        self.history_tree.setMaximumHeight(200)
        self.history_tree.itemDoubleClicked.connect(self.on_history_item_clicked)
        layout.addWidget(self.history_tree)
        self.history_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_tree.customContextMenuRequested.connect(self.show_history_menu)

        self.favorites_tree = QTreeWidget()
        self.favorites_tree.setHeaderLabel("收藏设备")
        self.favorites_tree.setIndentation(10)
        self.favorites_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_tree.customContextMenuRequested.connect(self.show_history_menu)
        self.favorites_tree.customContextMenuRequested.connect(self.show_favorites_menu)
        self.favorites_tree.itemDoubleClicked.connect(self.on_favorite_item_clicked)
        layout.addWidget(self.favorites_tree)

        self.refresh_history_tree()
        self.refresh_favorites_tree()
        return sidebar

    def show_device_menu(self, position):
        item = self.device_table.itemAt(position)
        if not item:
            return
        row = item.row()
        serial_item = self.device_table.item(row, 1)
        if not serial_item:
            return
        serial = serial_item.text()
        menu = QMenu()
        alias_action = QAction("设置别名", self)
        alias_action.triggered.connect(lambda: self.set_device_alias(serial))
        disconnect_action = QAction("断开连接", self)
        disconnect_action.triggered.connect(lambda: self.disconnect_device(serial))
        menu.addAction(alias_action)
        menu.addAction(disconnect_action)
        menu.exec_(self.device_table.viewport().mapToGlobal(position))

    def set_device_alias(self, serial):
        from utils.config_manager import ConfigManager
        current_aliases = ConfigManager.get_device_aliases()
        current_alias = current_aliases.get(serial, "")
        alias, ok = QInputDialog.getText(self, "设置设备别名", "请输入别名（留空则清除）:", text=current_alias)
        if ok:
            ConfigManager.set_device_alias(serial, alias.strip())
            # 刷新所有相关界面
            self.device_manager.manual_refresh()      # 刷新设备列表
            self.refresh_history_tree()               # 刷新历史记录
            self.refresh_favorites_tree()             # 刷新收藏（如果收藏也显示别名）
            self.log_message(f"设备 {serial} 别名已更新为: {alias or '无'}")

    def disconnect_device(self, serial):
        self.adb_client.disconnect_device(serial, callback=lambda success, msg: self.log_message(f"断开: {msg}"))
        # 刷新设备列表
        self.device_manager.manual_refresh()

    def show_history_menu(self, position):
        item = self.history_tree.itemAt(position)
        if not item:
            return
        menu = QMenu()
        delete_action = QAction("删除此记录", self)
        delete_action.triggered.connect(lambda: self.delete_history_item(item))
        menu.addAction(delete_action)
        menu.exec_(self.history_tree.viewport().mapToGlobal(position))

    #    def delete_history_item(self, item):
    #        addr = item.text(0)
    #        history = ConfigManager.get_history()
    #        if addr in history:
    #            history.remove(addr)
    #            ConfigManager._write_json_file(HISTORY_FILE, history)  # 注意：需要导入 HISTORY_FILE 或使用 ConfigManager 的方法
    #            self.refresh_history_tree()
    #            self.log_message(f"已从历史记录中删除: {addr}")

    #    def delete_history_item(self, item):
    #        addr = item.text(0)
    #        if ConfigManager.remove_history(addr):
    #            self.refresh_history_tree()
    #            self.log_message(f"已从历史记录中删除: {addr}")

    def delete_history_item(self, item):
        addr = item.text(0)
        if ConfigManager.remove_history(addr):
            self.refresh_history_tree()
            self.log_message(f"已从历史记录中删除: {addr}")
        else:
            self.log_message(f"删除失败: {addr}")

    def refresh_history_tree(self):
        self.history_tree.clear()
        from utils.config_manager import ConfigManager
        aliases = ConfigManager.get_device_aliases()
        for addr in ConfigManager.get_history():
            # 尝试匹配别名：如果原始地址没有端口，尝试加上 :5555
            alias = aliases.get(addr, "")
            if not alias and ":" not in addr:
                alias = aliases.get(f"{addr}:5555", "")
            if alias:
                display_text = f"{alias} ({addr})"
            else:
                display_text = addr
            item = QTreeWidgetItem([display_text])
            item.setData(0, Qt.UserRole, addr)
            self.history_tree.addTopLevelItem(item)

    def refresh_favorites_tree(self):
        self.favorites_tree.clear()
        for group, devices in ConfigManager.get_favorites().items():
            group_item = QTreeWidgetItem([group])
            group_item.setExpanded(True)
            self.favorites_tree.addTopLevelItem(group_item)
            for dev in devices:
                group_item.addChild(QTreeWidgetItem([dev]))

    def on_history_item_clicked(self, item, col):
        addr = item.data(0, Qt.UserRole)
        if addr:
            self.address_input.setText(addr)
            self.connect_to_address()

    def on_favorite_item_clicked(self, item, col):
        if item.parent() is not None:
            self.address_input.setText(item.text(0))
            self.connect_to_address()

    def show_favorites_menu(self, pos):
        item = self.favorites_tree.itemAt(pos)
        menu = QMenu()
        if item is None:
            menu.addAction("新建分组").triggered.connect(self.add_favorite_group)
        elif item.parent() is None:
            menu.addAction("添加设备到此分组").triggered.connect(lambda: self.add_device_to_group(item.text(0)))
            menu.addAction("重命名分组").triggered.connect(lambda: self.rename_favorite_group(item.text(0)))
            menu.addAction("删除分组").triggered.connect(lambda: self.delete_favorite_group(item.text(0)))
        else:
            group = item.parent().text(0)
            menu.addAction("从收藏中移除").triggered.connect(lambda: self.remove_favorite_device(group, item.text(0)))
        menu.exec_(self.favorites_tree.viewport().mapToGlobal(pos))

    def add_favorite_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称:")
        if ok and name and name not in ConfigManager.get_favorites():
            fav = ConfigManager.get_favorites()
            fav[name] = []
            ConfigManager.save_favorites(fav)
            self.refresh_favorites_tree()

    def add_device_to_group(self, group):
        addr = self.address_input.text().strip()
        if addr:
            ConfigManager.add_favorite(group, addr)
            self.refresh_favorites_tree()
        else:
            QMessageBox.warning(self, "提示", "请先在输入框中填写设备地址")

    def rename_favorite_group(self, old):
        new, ok = QInputDialog.getText(self, "重命名分组", "新名称:", text=old)
        if ok and new and new != old:
            fav = ConfigManager.get_favorites()
            if new in fav:
                QMessageBox.warning(self, "错误", "分组名已存在")
                return
            fav[new] = fav.pop(old)
            ConfigManager.save_favorites(fav)
            self.refresh_favorites_tree()

    def delete_favorite_group(self, group):
        if QMessageBox.question(self, "确认删除", f"删除分组「{group}」及其所有设备？") == QMessageBox.Yes:
            fav = ConfigManager.get_favorites()
            fav.pop(group, None)
            ConfigManager.save_favorites(fav)
            self.refresh_favorites_tree()

    def remove_favorite_device(self, group, device):
        ConfigManager.remove_favorite(group, device)
        self.refresh_favorites_tree()

    def connect_to_address(self):
        if not self.adb_client:
            self.log_message("ADB 未配置，请先在全局设置中配置")
            QMessageBox.warning(self, "提示", "请先在全局设置中配置 ADB")
            return
        addr = self.address_input.text().strip()
        if not addr:
            return
        if ":" not in addr and not addr.startswith("emulator-"):
            addr = f"{addr}:5555"
        self.log_message(f"连接 {addr} ...")
        self.adb_client.connect_device(addr, callback=self.on_connect_result)

    def on_connect_result(self, success, message):
        if success:
            self.log_message(f"连接成功: {message}")
            if self.device_manager:
                self.device_manager.manual_refresh()
            ConfigManager.add_history(self.address_input.text().strip())
            self.refresh_history_tree()
            self.address_input.clear()
        else:
            self.log_message(f"连接失败: {message}")
            # 显示详细错误对话框
            QMessageBox.critical(self, "连接失败", f"错误详情:\n{message}\n\n请检查设备是否开启网络调试，或尝试在命令行中手动连接。")
        self.statusBar().showMessage("就绪")

    def restart_adb_server(self):
        if not self.adb_client:
            self.log_message("ADB 未配置，无法重启")
            return
        if self.device_windows and QMessageBox.question(self, "确认", "重启 ADB 会关闭所有设备窗口，继续？") != QMessageBox.Yes:
            return
        for _, win in self.device_windows:
            win.close()
        self.device_windows.clear()
        self.log_message("正在重启 ADB...")
        proc = QProcess(self)
        proc.finished.connect(lambda code, p=proc: self._after_adb_kill(code, p))
        proc.start(self.adb_client.adb_path, ["kill-server"])

    def _after_adb_kill(self, exit_code, proc):
        self.log_message("ADB 已停止，正在启动...")
        proc2 = QProcess(self)
        proc2.finished.connect(lambda code: self._after_adb_start(code))
        proc2.start(self.adb_client.adb_path, ["start-server"])

    def _after_adb_start(self, exit_code):
        if exit_code == 0:
            self.log_message("ADB 已启动")
            if self.device_manager:
                self.device_manager.manual_refresh()
        else:
            self.log_message("ADB 启动失败")
        self.statusBar().showMessage("就绪")

    def kill_adb_server(self):
        if not self.adb_client:
            self.log_message("ADB 未配置，无法停止")
            return
        if QMessageBox.question(self, "确认", "停止 ADB 服务，所有设备将断开。继续？") != QMessageBox.Yes:
            return
        self.log_message("正在停止 ADB...")
        proc = QProcess(self)
        proc.finished.connect(lambda: self.log_message("ADB 已停止"))
        proc.start(self.adb_client.adb_path, ["kill-server"])
        self.device_table.setRowCount(0)
        for _, win in self.device_windows:
            win.close()
        self.device_windows.clear()
        self.statusBar().showMessage("就绪")

    def on_device_double_clicked(self, index):
        if not self.device_manager:
            self.log_message("ADB 未配置，无法打开设备窗口")
            return
        serial = self.device_table.item(index.row(), 1).text()
        self.open_device_window(serial)

    def open_device_window(self, serial):
        for s, win in self.device_windows:
            if s == serial and win.isVisible():
                win.raise_()
                win.activateWindow()
                return
        from ui.device_window import DeviceWindow
        win = DeviceWindow(serial, self.adb_client, self)
        win.show()
        win.closed.connect(lambda: self.remove_device_window(serial, win))
        self.device_windows.append((serial, win))

    def remove_device_window(self, serial, window):
        self.device_windows = [(s, w) for s, w in self.device_windows if w != window]

    def open_settings_dialog(self, force=False):
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec_()   # 不再显示额外提示，因为 settings_dialog 内部已处理

    def open_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        import platform
        sys_info = f"操作系统: {platform.system()} {platform.release()}\nPython版本: {sys.version.split()[0]}"
        if self.adb_client and self.adb_client.adb_path:
            ok, ver = SystemUtils.check_adb_version(self.adb_client.adb_path)
            adb_info = f"ADB路径: {self.adb_client.adb_path}\nADB版本: {ver if ok else '获取失败'}"
        else:
            adb_info = "ADB路径: 未配置或无效\n请在全局设置中配置正确的 ADB 路径"
        text_browser = QTextBrowser()
        text_browser.setText(f"{sys_info}\n\n{adb_info}")
        layout.addWidget(text_browser)
        btn = QPushButton("确定")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        dialog.exec_()
        self.statusBar().showMessage("就绪")

    def log_message(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def load_settings(self):
        geom = ConfigManager.get_settings().get("window_geometry", {})
        if geom:
            self.resize(geom.get("width", 800), geom.get("height", 600))
            self.move(QPoint(geom.get("x", 100), geom.get("y", 100)))

    def closeEvent(self, event):
        ConfigManager.set_setting("window_geometry", {
            "width": self.width(), "height": self.height(),
            "x": self.x(), "y": self.y()
        })
        if self.device_manager:
            self.device_manager.stop_refresh()
        event.accept()

    def reload_adb(self):
        # 暂未使用，但保留占位
        pass

    def update_device_table(self, devices: List[tuple]):
        if not self.device_manager:
            return
        # 获取顺序
        order = ConfigManager.get_device_order()
        device_dict = {serial: (serial, state, name) for serial, state, name in devices}
        ordered = []
        for serial in order:
            if serial in device_dict:
                ordered.append(device_dict.pop(serial))
        ordered.extend(device_dict.values())
        # 填充表格
        aliases = ConfigManager.get_device_aliases()
        self.device_table.setRowCount(len(ordered))
        for row, (serial, state, name) in enumerate(ordered):
            display_name = aliases.get(serial, name)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, serial)
            self.device_table.setItem(row, 0, name_item)
            self.device_table.setItem(row, 1, QTableWidgetItem(serial))
            state_item = QTableWidgetItem(state)
            if state == "device":
                state_item.setForeground(Qt.darkGreen)
            elif state == "offline":
                state_item.setForeground(Qt.darkYellow)
            elif state == "unauthorized":
                state_item.setForeground(Qt.red)
            self.device_table.setItem(row, 2, state_item)
        self.statusBar().showMessage("就绪")

    def move_device_up(self):
        current_row = self.device_table.currentRow()
        if current_row <= 0:
            return
        self.swap_rows(current_row, current_row - 1)
        self.device_table.selectRow(current_row - 1)
        self.save_device_order()

    def move_device_down(self):
        current_row = self.device_table.currentRow()
        if current_row < 0 or current_row >= self.device_table.rowCount() - 1:
            return
        self.swap_rows(current_row, current_row + 1)
        self.device_table.selectRow(current_row + 1)
        self.save_device_order()

    def swap_rows(self, row1, row2):
        for col in range(self.device_table.columnCount()):
            item1 = self.device_table.takeItem(row1, col)
            item2 = self.device_table.takeItem(row2, col)
            self.device_table.setItem(row1, col, item2)
            self.device_table.setItem(row2, col, item1)

    def save_device_order(self):
        order = []
        for row in range(self.device_table.rowCount()):
            serial_item = self.device_table.item(row, 1)
            if serial_item:
                order.append(serial_item.text())
        ConfigManager.set_device_order(order)

    def eventFilter(self, obj, event):
        if obj == self.device_table.viewport() and event.type() == QEvent.Drop:
            # 拖拽完成后保存顺序（延迟一点确保表格已更新）
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(10, self.save_device_order)
        return super().eventFilter(obj, event)
