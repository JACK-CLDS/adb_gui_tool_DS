"""
ui/terminal.py - 终端控件 (Terminal Widget)

功能 (Features):
    - 运行 adb shell 交互式终端 (Interactive adb shell terminal)
    - 支持历史命令记录，上下键浏览 (Command history with Up/Down browsing)
    - 支持清屏 (clear/cls 命令) (Clear screen)
    - 重置终端按钮 (Reset terminal button)
    - 等宽字体显示 (Monospace font)

依赖 (Dependencies): PyQt5, core.adb_client
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, QHBoxLayout,
    QLabel, QPushButton, QMessageBox
)
from PyQt5.QtCore import QProcess, pyqtSignal, Qt, QEvent, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QFontDatabase


class TerminalWidget(QWidget):
    """交互式终端控件 (Interactive terminal widget)"""

    status_message = pyqtSignal(str)   # 状态栏消息信号

    def __init__(self, serial: str, adb_client, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.process = None
        self.history = []              # 命令历史 (Command history)
        self.history_index = -1

        self.init_ui()
        # 延迟启动 shell，避免阻塞窗口打开 (Defer shell start to avoid UI freeze)
        QTimer.singleShot(50, self.start_shell)

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建终端界面 (Create terminal UI)"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 输出区域 (Output area)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.output)

        # 输入行 + 重置按钮 + 提示 (Input line + reset button + hint)
        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("输入命令...")
        self.input_line.returnPressed.connect(self.send_command)
        self.input_line.installEventFilter(self)
        input_layout.addWidget(self.input_line)

        self.reset_btn = QPushButton("重置终端")
        self.reset_btn.setToolTip("杀死当前 shell 并重启")
        self.reset_btn.clicked.connect(self.reset_terminal)
        input_layout.addWidget(self.reset_btn)

        hint_label = QLabel(" (Ctrl+C 无效，卡死时请点重置)")
        hint_label.setStyleSheet("color: #888;")
        input_layout.addWidget(hint_label)

        layout.addLayout(input_layout)

        # 设置等宽字体 (Set monospace font)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.output.setFont(fixed_font)
        self.input_line.setFont(fixed_font)

    # ========== Shell 进程管理 (Shell Process Management) ==========

    def start_shell(self):
        """启动 adb shell 进程 (Start adb shell process)"""
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
            self.process.waitForFinished(1000)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)
        self.process.started.connect(self.on_shell_started)
        self.process.start(self.adb_client.adb_path, ["-s", self.serial, "shell"])

        # 5 秒超时检测 (5-second startup timeout)
        QTimer.singleShot(5000, self._check_start_timeout)

    def _check_start_timeout(self):
        """检查 shell 是否启动超时 (Check shell startup timeout)"""
        if self.process and self.process.state() != QProcess.Running:
            self.output.append("错误：无法启动 adb shell (超时)")
            self.status_message.emit("无法启动 shell")
            self.input_line.setEnabled(False)
            self.reset_btn.setEnabled(True)

    def on_shell_started(self):
        """shell 启动成功回调 (Shell started callback)"""
        self.input_line.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.output.append("Shell 已启动")

    def reset_terminal(self):
        """重置终端：杀死当前 shell 并重启 (Reset: kill current shell and restart)"""
        reply = QMessageBox.question(
            self, "确认重置",
            "重置终端将终止当前所有运行中的命令，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.output.append("\n[用户重置终端]")
            self.start_shell()

    # ========== 命令发送与输出处理 (Command I/O) ==========

    def send_command(self):
        """发送用户输入的命令 (Send command from input line)"""
        cmd = self.input_line.text().strip()
        if not cmd:
            return

        # 本地处理清屏命令 (Handle clear locally)
        if cmd in ("clear", "cls"):
            self.output.clear()
            self.input_line.clear()
            return

        # top 命令提示 (Hint for top command)
        if cmd == "top":
            QMessageBox.information(
                self, "提示",
                "top 命令会持续刷新，可使用「重置终端」按钮退出。"
            )

        # 记录到历史 (Save to history)
        self.history.append(cmd)
        self.history_index = len(self.history)
        self.input_line.clear()

        # 发送到 shell
        self.process.write((cmd + "\n").encode())

    def on_output(self):
        """读取 shell 输出并显示 (Read shell output and display)"""
        data = self.process.readAllStandardOutput()
        text = data.data().decode('utf-8', errors='ignore')
        if not text:
            return

        self.output.moveCursor(QTextCursor.End)
        if not self.output.textCursor().atBlockStart():
            self.output.insertPlainText('\n')
        self.output.insertPlainText(text)
        if not text.endswith('\n'):
            self.output.insertPlainText('\n')
        self.output.moveCursor(QTextCursor.End)

    def on_finished(self, exit_code, exit_status):
        """shell 进程结束回调 (Shell finished callback)"""
        self.output.append("\n[Shell 进程已结束]")
        self.status_message.emit("shell 进程结束")
        self.input_line.setEnabled(False)

    # ========== 键盘事件处理 (Keyboard Events) ==========

    def eventFilter(self, obj, event):
        """
        键盘事件过滤器 (Keyboard event filter):
          - Ctrl+C: 提示用户使用重置按钮
          - Up/Down: 浏览历史命令
        """
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            # Ctrl+C 提示 (Ctrl+C hint)
            if event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                self.status_message.emit("请使用「重置终端」按钮来停止卡死的命令")
                return True

            # 上箭头: 更早的历史命令 (Up: older history)
            if event.key() == Qt.Key_Up:
                if self.history_index > 0:
                    self.history_index -= 1
                    self.input_line.setText(self.history[self.history_index])
                return True

            # 下箭头: 更新的历史命令，超过最新则清空 (Down: newer history)
            if event.key() == Qt.Key_Down:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.input_line.setText(self.history[self.history_index])
                elif self.history_index == len(self.history) - 1:
                    self.history_index = len(self.history)
                    self.input_line.clear()
                return True

        return super().eventFilter(obj, event)
