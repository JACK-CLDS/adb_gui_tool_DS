"""
ui/logcat_tab.py - 日志查看控件 (Logcat Viewer)

功能 (Features):
    - 实时显示 adb logcat 输出 (Real-time logcat output)
    - 按级别过滤 V/D/I/W/E/F (Level filter)
    - 搜索文本高亮 (Search highlight)
    - 暂停/恢复滚动 (Pause/Resume scrolling)
    - 清空和保存日志 (Clear & Save log)
    - 语法高亮器 (Syntax highlighter for log levels)

依赖 (Dependencies): PyQt5, core.adb_client
"""

import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QComboBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QLabel
)
from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QSyntaxHighlighter, QFontDatabase
)


class LogcatHighlighter(QSyntaxHighlighter):
    """
    Logcat 语法高亮器 (Syntax highlighter for logcat)
    - 按日志级别着色
    - 支持搜索词高亮
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_rules = []           # 级别高亮规则 (Level highlight rules)
        self.search_pattern = None      # 当前搜索正则 (Search regex pattern)
        self.search_format = QTextCharFormat()
        self.search_format.setBackground(QColor(255, 255, 0))   # 黄色背景 (Yellow background)
        self.search_format.setForeground(QColor(0, 0, 0))       # 黑色文字 (Black text)

    def setup_level_rules(self, level_filters):
        """
        依据当前启用的级别，设置级别高亮规则。
        Setup level highlighting rules based on active filters.
        """
        self.level_rules = []
        color_map = {
            'V': QColor(128, 128, 128),   # 灰色 (Gray)
            'D': QColor(0, 128, 0),       # 绿色 (Green)
            'I': QColor(0, 0, 255),       # 蓝色 (Blue)
            'W': QColor(255, 165, 0),     # 橙色 (Orange)
            'E': QColor(255, 0, 0),       # 红色 (Red)
            'F': QColor(255, 0, 255),     # 品红 (Magenta)
        }
        for level, color in color_map.items():
            if level in level_filters:
                pattern = re.compile(rf'\b{level}/\w+')
                fmt = QTextCharFormat()
                fmt.setForeground(color)
                self.level_rules.append((pattern, fmt))

    def set_search_text(self, text: str):
        """
        设置搜索文本，支持正则表达式。
        Set search text (supports regex).
        """
        if not text:
            self.search_pattern = None
        else:
            try:
                self.search_pattern = re.compile(re.escape(text), re.IGNORECASE)
            except:
                self.search_pattern = None
        self.rehighlight()

    def highlightBlock(self, text):
        """高亮当前文本块 (Highlight current text block)"""
        # 先应用级别高亮 (Apply level highlighting first)
        for pattern, fmt in self.level_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        # 再叠加搜索高亮 (Overlay search highlighting)
        if self.search_pattern:
            for match in self.search_pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), self.search_format)


class LogcatTab(QWidget):
    """实时日志查看控件 (Real-time logcat viewer tab)"""

    def __init__(self, serial: str, adb_client, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.process = None
        self.paused = False
        self.level_filters = ['V', 'D', 'I', 'W', 'E', 'F']   # 默认显示所有级别

        self.init_ui()
        self.start_logcat()

    # ========== UI 初始化 (UI Initialization) ==========

    def init_ui(self):
        """创建界面布局 (Create UI layout)"""
        layout = QVBoxLayout(self)

        # ---- 控制栏 (Control bar) ----
        control_layout = QHBoxLayout()

        control_layout.addWidget(QLabel("级别:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems([
            "All", "Verbose (V)", "Debug (D)", "Info (I)",
            "Warning (W)", "Error (E)", "Fatal (F)"
        ])
        self.level_combo.currentIndexChanged.connect(self.on_level_changed)
        control_layout.addWidget(self.level_combo)

        control_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("高亮文本")
        self.search_input.textChanged.connect(self.highlight_search)
        control_layout.addWidget(self.search_input)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        control_layout.addWidget(self.pause_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_log)
        control_layout.addWidget(self.clear_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_log)
        control_layout.addWidget(self.save_btn)

        layout.addLayout(control_layout)

        # ---- 日志显示区域 (Log display area) ----
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.log_text.setFont(font)
        layout.addWidget(self.log_text)

        # 创建高亮器并绑定 (Create highlighter and bind)
        self.highlighter = LogcatHighlighter(self.log_text.document())
        self.highlighter.setup_level_rules(self.level_filters)

    # ========== logcat 进程管理 (Logcat Process) ==========

    def start_logcat(self):
        """启动 adb logcat 进程 (Start adb logcat process)"""
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)

        args = ["-s", self.serial, "logcat", "-v", "threadtime"]
        self.process.start(self.adb_client.adb_path, args)

    def on_ready_read(self):
        """读取 logcat 输出并显示 (Read logcat output and display)"""
        if self.paused:
            return
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.splitlines():
            if self.should_show_line(line):
                self.append_log(line)

    def on_finished(self):
        """logcat 进程意外退出时自动重启 (Auto restart on unexpected exit)"""
        self.start_logcat()

    def stop(self):
        """终止 logcat 进程 (Terminate logcat process)"""
        if self.process and self.process.state() == QProcess.Running:
            self.process.terminate()
            self.process.waitForFinished(2000)

    # ========== 显示与过滤 (Display & Filter) ==========

    def should_show_line(self, line: str) -> bool:
        """检查当前行是否满足级别过滤条件 (Check if line passes level filter)"""
        level_char = None
        for ch in ['V', 'D', 'I', 'W', 'E', 'F']:
            if f' {ch}/' in line or f'\t{ch}/' in line:
                level_char = ch
                break
        if level_char and level_char not in self.level_filters:
            return False
        return True

    def append_log(self, text: str):
        """追加一行日志并自动滚动到底部 (Append log line and auto-scroll)"""
        self.log_text.appendPlainText(text)
        if not self.paused:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)

    def on_level_changed(self, index):
        """级别下拉框变更事件 (Level combo box changed)"""
        level_map = {
            0: ['V', 'D', 'I', 'W', 'E', 'F'],
            1: ['V'], 2: ['D'], 3: ['I'], 4: ['W'], 5: ['E'], 6: ['F']
        }
        self.level_filters = level_map.get(index, ['V', 'D', 'I', 'W', 'E', 'F'])
        self.highlighter.setup_level_rules(self.level_filters)
        self.highlighter.rehighlight()

    def toggle_pause(self):
        """暂停/恢复滚动 (Toggle pause/resume scrolling)"""
        self.paused = not self.paused
        self.pause_btn.setText("恢复" if self.paused else "暂停")

    def clear_log(self):
        """清空日志 (Clear log)"""
        self.log_text.clear()

    def save_log(self):
        """保存日志到文件 (Save log to file)"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志", "logcat.txt", "文本文件 (*.txt)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "保存成功", f"日志已保存到 {file_path}")

    # ========== 搜索高亮 (Search Highlight) ==========

    def highlight_search(self):
        """根据搜索框内容更新高亮 (Update search highlighting)"""
        search_text = self.search_input.text().strip()
        self.highlighter.set_search_text(search_text)
        if search_text:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.log_text.setTextCursor(cursor)
            self.log_text.find(search_text)

    # 预留接口 (Reserved interface)
    def apply_filters(self):
        """预留：按包名过滤 (Reserved: filter by package name)"""
        pass
