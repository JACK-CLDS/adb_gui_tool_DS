"""
ui/soft_keyboard.py - 软键盘窗口 (Soft Keyboard Window)

功能 (Features):
    - 标准键盘布局，可点击发送按键 (Standard keyboard layout for sending keys)
    - 所有 Android KeyEvent 常量的分组展示 (All Android KeyEvent constants grouped)
    - 自定义文本或 keyevent 序列发送 (Send custom text or keyevent sequence)
    - 支持字母、数字、方向、功能键、媒体控制等 (Supports letters, digits, arrows, function keys, media controls)

依赖 (Dependencies): PyQt5, core.adb_client
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGridLayout, QPushButton, QLineEdit, QLabel, QScrollArea,
    QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.adb_client import AdbClient


class SoftKeyboardWindow(QDialog):
    """软键盘窗口 (Soft keyboard dialog)"""

    def __init__(self, serial: str, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.setWindowTitle(f"软键盘 - {serial}")
        self.setMinimumSize(800, 600)
        self.init_ui()

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建对话框界面 (Create dialog UI)"""
        layout = QVBoxLayout(self)

        # 选项卡 (Tabs)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self.standard_tab = self.create_standard_keyboard()
        self.tab_widget.addTab(self.standard_tab, "标准键盘")

        self.keyevent_tab = self.create_keyevent_tab()
        self.tab_widget.addTab(self.keyevent_tab, "所有按键")

        # 底部自定义输入区 (Bottom custom input area)
        bottom_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("输入文本或 keyevent 代码 (多个用空格分隔，如 'KEYCODE_HOME KEYCODE_BACK' 或 '3 4')")
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_custom)
        bottom_layout.addWidget(QLabel("自定义:"))
        bottom_layout.addWidget(self.text_input)
        bottom_layout.addWidget(self.send_btn)
        layout.addLayout(bottom_layout)

    # ========== 标准键盘 (Standard Keyboard) ==========

    def create_standard_keyboard(self) -> QWidget:
        """创建标准键盘页面 (Create standard keyboard tab)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        grid = QGridLayout()
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)

        # 按键定义 (Key definitions: label, row, col)
        keys = [
            # 数字行 (Number row)
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2), ("4", 0, 3), ("5", 0, 4),
            ("6", 0, 5), ("7", 0, 6), ("8", 0, 7), ("9", 0, 8), ("0", 0, 9),
            # 第一行字母 (Q-P)
            ("Q", 1, 0), ("W", 1, 1), ("E", 1, 2), ("R", 1, 3), ("T", 1, 4),
            ("Y", 1, 5), ("U", 1, 6), ("I", 1, 7), ("O", 1, 8), ("P", 1, 9),
            # 第二行字母 (A-L)
            ("A", 2, 0), ("S", 2, 1), ("D", 2, 2), ("F", 2, 3), ("G", 2, 4),
            ("H", 2, 5), ("J", 2, 6), ("K", 2, 7), ("L", 2, 8),
            # 第三行字母 (Z-M)
            ("Z", 3, 0), ("X", 3, 1), ("C", 3, 2), ("V", 3, 3), ("B", 3, 4),
            ("N", 3, 5), ("M", 3, 6),
            # 功能键 (Function keys)
            ("空格", 4, 0), ("回车", 4, 1), ("删除", 4, 2), ("Tab", 4, 3), ("ESC", 4, 4),
            # 方向键 (Arrow keys)
            ("上", 5, 0), ("下", 5, 1), ("左", 5, 2), ("右", 5, 3),
            # 系统键 (System keys)
            ("HOME", 6, 0), ("BACK", 6, 1), ("菜单", 6, 2), ("音量+", 6, 3),
            ("音量-", 6, 4), ("电源", 6, 5), ("相机", 6, 6),
            # F1-F12
            ("F1", 7, 0), ("F2", 7, 1), ("F3", 7, 2), ("F4", 7, 3), ("F5", 7, 4),
            ("F6", 7, 5), ("F7", 7, 6), ("F8", 7, 7), ("F9", 7, 8), ("F10", 7, 9),
            ("F11", 7, 10), ("F12", 7, 11),
        ]

        for label, row, col in keys:
            btn = QPushButton(label)
            btn.setFixedSize(80, 40)   # 固定按钮大小 (Fixed button size)
            btn.setFont(QFont("Arial", 10))
            btn.clicked.connect(lambda checked, l=label: self.send_key_by_label(l))
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_button_row(self, labels):
        """创建一行按钮 (Create a row of buttons)"""
        hbox = QHBoxLayout()
        for label in labels:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, l=label: self.send_key_by_label(l))
            hbox.addWidget(btn)
        hbox.addStretch()
        return hbox

    def send_key_by_label(self, label: str):
        """根据按钮标签发送对应的 keyevent (Send keyevent by button label)"""
        mapping = {
            "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
            "6": "6", "7": "7", "8": "8", "9": "9", "0": "0",
            "Q": "KEYCODE_Q", "W": "KEYCODE_W", "E": "KEYCODE_E", "R": "KEYCODE_R", "T": "KEYCODE_T",
            "Y": "KEYCODE_Y", "U": "KEYCODE_U", "I": "KEYCODE_I", "O": "KEYCODE_O", "P": "KEYCODE_P",
            "A": "KEYCODE_A", "S": "KEYCODE_S", "D": "KEYCODE_D", "F": "KEYCODE_F", "G": "KEYCODE_G",
            "H": "KEYCODE_H", "J": "KEYCODE_J", "K": "KEYCODE_K", "L": "KEYCODE_L",
            "Z": "KEYCODE_Z", "X": "KEYCODE_X", "C": "KEYCODE_C", "V": "KEYCODE_V", "B": "KEYCODE_B",
            "N": "KEYCODE_N", "M": "KEYCODE_M",
            "空格": "KEYCODE_SPACE", "回车": "KEYCODE_ENTER", "删除": "KEYCODE_DEL",
            "Tab": "KEYCODE_TAB", "ESC": "KEYCODE_ESCAPE",
            "上": "KEYCODE_DPAD_UP", "下": "KEYCODE_DPAD_DOWN", "左": "KEYCODE_DPAD_LEFT", "右": "KEYCODE_DPAD_RIGHT",
            "HOME": "KEYCODE_HOME", "BACK": "KEYCODE_BACK", "菜单": "KEYCODE_MENU",
            "音量+": "KEYCODE_VOLUME_UP", "音量-": "KEYCODE_VOLUME_DOWN", "电源": "KEYCODE_POWER", "相机": "KEYCODE_CAMERA",
        }
        # F1-F12
        for i in range(1, 13):
            mapping[f"F{i}"] = f"KEYCODE_F{i}"

        keycode = mapping.get(label, label)
        self.send_keyevent(keycode)

    # ========== 所有 KeyEvent (All KeyEvents) ==========

    def create_keyevent_tab(self) -> QWidget:
        """创建所有 KeyEvent 按键页面 (Create all KeyEvent tab)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid_layout = QGridLayout(content)

        groups = self.get_keyevent_groups()
        row = 0
        for group_name, keys in groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QGridLayout()
            for i, (key_name, key_code) in enumerate(keys.items()):
                btn = QPushButton(f"{key_name}\n({key_code})")
                btn.clicked.connect(lambda checked, kc=key_name: self.send_keyevent(kc))
                group_layout.addWidget(btn, i // 4, i % 4)
            group_box.setLayout(group_layout)
            grid_layout.addWidget(group_box, row, 0)
            row += 1

        scroll.setWidget(content)
        layout.addWidget(scroll)
        return widget

    def get_keyevent_groups(self) -> dict:
        """
        返回分组后的 KeyEvent 常量 (Return grouped KeyEvent constants)
        基于 Android API 参考，列出了一部分常用常量。
        """
        groups = {
            "导航键 (Navigation)": {
                "KEYCODE_HOME": 3,
                "KEYCODE_BACK": 4,
                "KEYCODE_MENU": 82,
                "KEYCODE_APP_SWITCH": 187,
                "KEYCODE_DPAD_UP": 19,
                "KEYCODE_DPAD_DOWN": 20,
                "KEYCODE_DPAD_LEFT": 21,
                "KEYCODE_DPAD_RIGHT": 22,
                "KEYCODE_DPAD_CENTER": 23,
            },
            "字母键 (Letters)": {f"KEYCODE_{chr(65+i)}": 29+i for i in range(26)},
            "数字键 (Digits)": {f"KEYCODE_{i}": 7+i for i in range(10)},
            "功能键 (Function Keys)": {
                "KEYCODE_F1": 131, "KEYCODE_F2": 132, "KEYCODE_F3": 133,
                "KEYCODE_F4": 134, "KEYCODE_F5": 135, "KEYCODE_F6": 136,
                "KEYCODE_F7": 137, "KEYCODE_F8": 138, "KEYCODE_F9": 139,
                "KEYCODE_F10": 140, "KEYCODE_F11": 141, "KEYCODE_F12": 142,
                "KEYCODE_F13": 143, "KEYCODE_F14": 144, "KEYCODE_F15": 145,
                "KEYCODE_F16": 146, "KEYCODE_F17": 147, "KEYCODE_F18": 148,
                "KEYCODE_F19": 149, "KEYCODE_F20": 150, "KEYCODE_F21": 151,
                "KEYCODE_F22": 152, "KEYCODE_F23": 153, "KEYCODE_F24": 154,
            },
            "修饰键 (Modifiers)": {
                "KEYCODE_SHIFT_LEFT": 59, "KEYCODE_SHIFT_RIGHT": 60,
                "KEYCODE_CTRL_LEFT": 113, "KEYCODE_CTRL_RIGHT": 114,
                "KEYCODE_ALT_LEFT": 57, "KEYCODE_ALT_RIGHT": 58,
                "KEYCODE_META_LEFT": 117, "KEYCODE_META_RIGHT": 118,
                "KEYCODE_CAPS_LOCK": 115, "KEYCODE_NUM_LOCK": 143,
                "KEYCODE_SCROLL_LOCK": 116,
            },
            "媒体控制 (Media)": {
                "KEYCODE_MEDIA_PLAY_PAUSE": 85,
                "KEYCODE_MEDIA_STOP": 86,
                "KEYCODE_MEDIA_NEXT": 87,
                "KEYCODE_MEDIA_PREVIOUS": 88,
                "KEYCODE_MEDIA_REWIND": 89,
                "KEYCODE_MEDIA_FAST_FORWARD": 90,
                "KEYCODE_VOLUME_UP": 24,
                "KEYCODE_VOLUME_DOWN": 25,
                "KEYCODE_VOLUME_MUTE": 164,
            },
            "其他 (Others)": {
                "KEYCODE_ENTER": 66,
                "KEYCODE_DEL": 67,
                "KEYCODE_TAB": 61,
                "KEYCODE_SPACE": 62,
                "KEYCODE_ESCAPE": 111,
                "KEYCODE_POWER": 26,
                "KEYCODE_CAMERA": 27,
                "KEYCODE_CALL": 5,
                "KEYCODE_ENDCALL": 6,
                "KEYCODE_PAGE_UP": 92,
                "KEYCODE_PAGE_DOWN": 93,
                "KEYCODE_MOVE_HOME": 122,
                "KEYCODE_MOVE_END": 123,
                "KEYCODE_INSERT": 124,
                "KEYCODE_FORWARD_DEL": 112,
            },
        }
        return groups

    # ========== 发送逻辑 (Send Logic) ==========

    def send_keyevent(self, keycode: str):
        """发送单个 keyevent (Send a single keyevent)"""
        self.adb_client.send_keyevent(keycode, self.serial)
        self.status_message(f"发送按键: {keycode}")

    def send_custom(self):
        """发送自定义输入：文本或 keyevent 序列 (Send custom text or keyevent sequence)"""
        text = self.text_input.text().strip()
        if not text:
            return
        parts = text.split()
        if len(parts) > 1:
            # 多个 keyevent 序列 (Multiple keyevents)
            for part in parts:
                self.adb_client.send_keyevent(part, self.serial)
            self.status_message(f"发送按键序列: {text}")
        else:
            # 单个 keyevent 或文本 (Single keyevent or text)
            if text.isdigit() or text.upper().startswith("KEYCODE_"):
                self.adb_client.send_keyevent(text, self.serial)
                self.status_message(f"发送按键: {text}")
            else:
                self.adb_client.send_text(text, self.serial)
                self.status_message(f"发送文本: {text}")
        self.text_input.clear()

    # ========== 状态反馈 (Status Feedback) ==========

    def status_message(self, msg: str):
        """
        输出状态信息，尝试通过父窗口的信号传递。
        Send status message; attempt to emit through parent's signal if available.
        """
        if hasattr(self.parent(), 'status_message'):
            self.parent().status_message.emit(msg)
        else:
            print(f"[SoftKeyboard] {msg}")
