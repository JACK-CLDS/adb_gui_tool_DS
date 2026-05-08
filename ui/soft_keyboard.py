"""
ui/soft_keyboard.py - 软键盘窗口 (Soft Keyboard Window)

功能 (Features):
    - 标准键盘布局，可点击发送按键 (Standard keyboard layout for sending keys)
    - 所有 Android KeyEvent 常量的分组展示 (All Android KeyEvent constants grouped)
    - 自定义文本或 keyevent 序列发送 (Send custom text or keyevent sequence)
    - 支持字母、数字、方向、功能键、媒体控制等 (Supports letters, digits, arrows, function keys, media controls)

多语言 (i18n):
    所有用户可见字符串均已使用 self.tr() 包裹，可通过翻译文件切换语言。
    按钮显示的文本可翻译，但底层 keyevent 标识保持不变。
    All user-visible strings are wrapped with self.tr() for translation.
    Button labels can be translated while underlying keyevent identifiers remain unchanged.

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
        # 窗口标题翻译
        self.setWindowTitle(self.tr("软键盘 - {serial}").format(serial=serial))
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
        self.tab_widget.addTab(self.standard_tab, self.tr("标准键盘"))

        self.keyevent_tab = self.create_keyevent_tab()
        self.tab_widget.addTab(self.keyevent_tab, self.tr("所有按键"))

        # 底部自定义输入区 (Bottom custom input area)
        bottom_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText(
            self.tr("输入文本或 keyevent 代码 (多个用空格分隔，如 'KEYCODE_HOME KEYCODE_BACK' 或 '3 4')")
        )
        self.send_btn = QPushButton(self.tr("发送"))
        self.send_btn.clicked.connect(self.send_custom)
        bottom_layout.addWidget(QLabel(self.tr("自定义:")))
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

        # 按键定义： (显示文本, keycode 标识, 行, 列)
        # Key definitions: (display text, keycode identifier, row, col)
        keys = [
            # 数字行 (Number row)
            ("1", "1", 0, 0), ("2", "2", 0, 1), ("3", "3", 0, 2), ("4", "4", 0, 3),
            ("5", "5", 0, 4), ("6", "6", 0, 5), ("7", "7", 0, 6), ("8", "8", 0, 7),
            ("9", "9", 0, 8), ("0", "0", 0, 9),
            # 第一行字母 (Q-P)
            ("Q", "KEYCODE_Q", 1, 0), ("W", "KEYCODE_W", 1, 1), ("E", "KEYCODE_E", 1, 2),
            ("R", "KEYCODE_R", 1, 3), ("T", "KEYCODE_T", 1, 4), ("Y", "KEYCODE_Y", 1, 5),
            ("U", "KEYCODE_U", 1, 6), ("I", "KEYCODE_I", 1, 7), ("O", "KEYCODE_O", 1, 8),
            ("P", "KEYCODE_P", 1, 9),
            # 第二行字母 (A-L)
            ("A", "KEYCODE_A", 2, 0), ("S", "KEYCODE_S", 2, 1), ("D", "KEYCODE_D", 2, 2),
            ("F", "KEYCODE_F", 2, 3), ("G", "KEYCODE_G", 2, 4), ("H", "KEYCODE_H", 2, 5),
            ("J", "KEYCODE_J", 2, 6), ("K", "KEYCODE_K", 2, 7), ("L", "KEYCODE_L", 2, 8),
            # 第三行字母 (Z-M)
            ("Z", "KEYCODE_Z", 3, 0), ("X", "KEYCODE_X", 3, 1), ("C", "KEYCODE_C", 3, 2),
            ("V", "KEYCODE_V", 3, 3), ("B", "KEYCODE_B", 3, 4), ("N", "KEYCODE_N", 3, 5),
            ("M", "KEYCODE_M", 3, 6),
            # 功能键 (Function keys) - 需要翻译的标签
            (self.tr("空格"), "KEYCODE_SPACE", 4, 0),
            (self.tr("回车"), "KEYCODE_ENTER", 4, 1),
            (self.tr("删除"), "KEYCODE_DEL", 4, 2),
            ("Tab", "KEYCODE_TAB", 4, 3),    # 不翻译，作为标识
            ("ESC", "KEYCODE_ESCAPE", 4, 4),
            # 方向键 (Arrow keys)
            (self.tr("上"), "KEYCODE_DPAD_UP", 5, 0),
            (self.tr("下"), "KEYCODE_DPAD_DOWN", 5, 1),
            (self.tr("左"), "KEYCODE_DPAD_LEFT", 5, 2),
            (self.tr("右"), "KEYCODE_DPAD_RIGHT", 5, 3),
            # 系统键 (System keys)
            ("HOME", "KEYCODE_HOME", 6, 0),   # 不翻译，保持标识
            ("BACK", "KEYCODE_BACK", 6, 1),
            (self.tr("菜单"), "KEYCODE_MENU", 6, 2),
            (self.tr("音量+"), "KEYCODE_VOLUME_UP", 6, 3),
            (self.tr("音量-"), "KEYCODE_VOLUME_DOWN", 6, 4),
            (self.tr("电源"), "KEYCODE_POWER", 6, 5),
            (self.tr("相机"), "KEYCODE_CAMERA", 6, 6),
            # F1-F12 不翻译，保留原样
            ("F1", "KEYCODE_F1", 7, 0), ("F2", "KEYCODE_F2", 7, 1),
            ("F3", "KEYCODE_F3", 7, 2), ("F4", "KEYCODE_F4", 7, 3),
            ("F5", "KEYCODE_F5", 7, 4), ("F6", "KEYCODE_F6", 7, 5),
            ("F7", "KEYCODE_F7", 7, 6), ("F8", "KEYCODE_F8", 7, 7),
            ("F9", "KEYCODE_F9", 7, 8), ("F10", "KEYCODE_F10", 7, 9),
            ("F11", "KEYCODE_F11", 7, 10), ("F12", "KEYCODE_F12", 7, 11),
        ]

        for label, keycode, row, col in keys:
            btn = QPushButton(label)
            btn.setFixedSize(80, 40)   # 固定按钮大小 (Fixed button size)
            btn.setFont(QFont("Arial", 10))
            # 存储 keycode 标识 (Store keycode identifier)
            btn.setProperty("keycode", keycode)
            btn.clicked.connect(lambda checked, b=btn: self.send_key_by_button(b))
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def send_key_by_button(self, button):
        """根据按钮属性发送对应的 keyevent (Send keyevent based on button's stored keycode)"""
        keycode = button.property("keycode")
        if keycode:
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
            # 组名需要翻译 (Translate group name)
            translated_group = self.tr(group_name)
            group_box = QGroupBox(translated_group)
            group_layout = QGridLayout()
            col = 0
            r = 0
            for key_name, key_code in keys.items():
                # 按钮文本保持 “KEYCODE_xxx (数字)”，无需翻译
                btn = QPushButton(f"{key_name}\n({key_code})")
                btn.setProperty("keycode", key_name)
                btn.clicked.connect(lambda checked, b=btn: self.send_key_by_button(b))
                group_layout.addWidget(btn, r, col)
                col += 1
                if col >= 4:
                    col = 0
                    r += 1
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
        注意：组名字符串需可翻译，但 KEYCODE_xxx 标识不翻译。
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
        self.status_message(
            self.tr("发送按键: {keycode}").format(keycode=keycode)
        )

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
            self.status_message(
                self.tr("发送按键序列: {text}").format(text=text)
            )
        else:
            # 单个 keyevent 或文本 (Single keyevent or text)
            if text.isdigit() or text.upper().startswith("KEYCODE_"):
                self.adb_client.send_keyevent(text, self.serial)
                self.status_message(
                    self.tr("发送按键: {text}").format(text=text)
                )
            else:
                self.adb_client.send_text(text, self.serial)
                self.status_message(
                    self.tr("发送文本: {text}").format(text=text)
                )
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
