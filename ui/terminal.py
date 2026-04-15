"""
ui/terminal.py - 交互式 Shell 终端控件（带重置功能）
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import QProcess, pyqtSignal, Qt, QEvent
from PyQt5.QtGui import QFont, QTextCursor


class TerminalWidget(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, serial: str, adb_client, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.process = None
        self.history = []
        self.history_index = -1
        self.init_ui()
        self.start_shell()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Monospace", 10))
        self.output.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.output)

        input_layout = QHBoxLayout()
        self.prompt_label = QLabel(f"{self.serial}: $ ")
        self.prompt_label.setFont(QFont("Monospace", 10))
        self.input_line = QLineEdit()
        self.input_line.setFont(QFont("Monospace", 10))
        self.input_line.returnPressed.connect(self.send_command)
        self.input_line.installEventFilter(self)
        input_layout.addWidget(self.prompt_label)
        input_layout.addWidget(self.input_line)

        # 重置按钮（杀死当前 shell 并重启）
        self.reset_btn = QPushButton("重置终端")
        self.reset_btn.setToolTip("杀死当前 shell 并重启，用于结束卡死的命令（如 top）")
        self.reset_btn.clicked.connect(self.reset_terminal)
        input_layout.addWidget(self.reset_btn)

        # 提示标签
        hint_label = QLabel(" (Ctrl+C 无效，卡死时请点重置)")
        hint_label.setFont(QFont("Monospace", 9))
        hint_label.setStyleSheet("color: #888;")
        input_layout.addWidget(hint_label)

        layout.addLayout(input_layout)

    def start_shell(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)
        self.process.start(self.adb_client.adb_path, ["-s", self.serial, "shell"])
        if not self.process.waitForStarted(3000):
            self.output.append("错误：无法启动 adb shell")
            self.status_message.emit("无法启动 shell")
            self.input_line.setEnabled(False)
            self.reset_btn.setEnabled(False)
        else:
            self.input_line.setEnabled(True)
            self.reset_btn.setEnabled(True)

    def reset_terminal(self):
        """重置终端：杀死当前 shell 并重新启动"""
        reply = QMessageBox.question(self, "确认重置", "重置终端将终止当前所有运行中的命令，是否继续？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.output.append("\n[用户重置终端]")
            self.start_shell()

    def send_command(self):
        cmd = self.input_line.text().strip()
        if not cmd:
            return

        # 本地清屏
        if cmd in ("clear", "cls"):
            self.output.clear()
            self.input_line.clear()
            return

        # 提示 top 命令
        if cmd == "top":
            QMessageBox.information(self, "提示", "top 命令会持续刷新，可使用「重置终端」按钮退出。")

        self.history.append(cmd)
        self.history_index = len(self.history)
        self.input_line.clear()
        self.process.write((cmd + "\n").encode())

    def on_output(self):
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
        self.output.append("\n[Shell 进程已结束]")
        self.status_message.emit("shell 进程结束")
        self.input_line.setEnabled(False)
        self.reset_btn.setEnabled(False)

    def eventFilter(self, obj, event):
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            # 禁用 Ctrl+C 的实际功能，仅显示提示
            if event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                self.status_message.emit("请使用「重置终端」按钮来停止卡死的命令")
                return True
            # 上下键历史
            if event.key() == Qt.Key_Up:
                if self.history_index > 0:
                    self.history_index -= 1
                    self.input_line.setText(self.history[self.history_index])
                return True
            elif event.key() == Qt.Key_Down:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.input_line.setText(self.history[self.history_index])
                elif self.history_index == len(self.history) - 1:
                    self.history_index = len(self.history)
                    self.input_line.clear()
                return True
        return super().eventFilter(obj, event)
