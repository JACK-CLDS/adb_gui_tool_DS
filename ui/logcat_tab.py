"""
ui/logcat_tab.py - 日志查看控件（logcat）

功能：
    - 实时显示 adb logcat 输出
    - 按级别过滤（V/D/I/W/E/F）
    - 按包名过滤
    - 搜索高亮
    - 暂停/恢复滚动
    - 清空和保存日志
"""

import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QComboBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QLabel
)
from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QSyntaxHighlighter, QFont


class LogcatHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_rules = []      # 级别高亮规则
        self.search_pattern = None # 搜索词正则表达式
        self.search_format = QTextCharFormat()
        self.search_format.setBackground(QColor(255, 255, 0))  # 黄色背景
        self.search_format.setForeground(QColor(0, 0, 0))

    def setup_level_rules(self, level_filters):
        """设置级别高亮规则"""
        self.level_rules = []
        color_map = {
            'V': QColor(128, 128, 128),
            'D': QColor(0, 128, 0),
            'I': QColor(0, 0, 255),
            'W': QColor(255, 165, 0),
            'E': QColor(255, 0, 0),
            'F': QColor(255, 0, 255),
        }
        for level, color in color_map.items():
            if level in level_filters:
                pattern = re.compile(rf'\b{level}/\w+')
                fmt = QTextCharFormat()
                fmt.setForeground(color)
                self.level_rules.append((pattern, fmt))

    def set_search_text(self, text: str):
        """设置搜索文本，支持正则表达式"""
        if not text:
            self.search_pattern = None
        else:
            try:
                self.search_pattern = re.compile(re.escape(text), re.IGNORECASE)
            except:
                self.search_pattern = None
        self.rehighlight()

    def highlightBlock(self, text):
        # 先应用级别高亮
        for pattern, fmt in self.level_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        # 再应用搜索高亮（覆盖）
        if self.search_pattern:
            for match in self.search_pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), self.search_format)


class LogcatTab(QWidget):
    def __init__(self, serial: str, adb_client, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.adb_client = adb_client
        self.process = None
        self.paused = False
        self.level_filters = ['V', 'D', 'I', 'W', 'E', 'F']
        self.init_ui()
        self.start_logcat()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 控制栏
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("级别:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["All", "Verbose (V)", "Debug (D)", "Info (I)", "Warning (W)", "Error (E)", "Fatal (F)"])
        self.level_combo.currentIndexChanged.connect(self.on_level_changed)
        control_layout.addWidget(self.level_combo)

        #        control_layout.addWidget(QLabel("包名:"))
        #        self.package_filter = QLineEdit()
        #        self.package_filter.setPlaceholderText("输入包名过滤（可选）")
        #        self.package_filter.returnPressed.connect(self.apply_filters)
        #        control_layout.addWidget(self.package_filter)

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

        # 日志显示区域
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        from PyQt5.QtGui import QFontDatabase
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.log_text.setFont(font)
        layout.addWidget(self.log_text)

        # 创建高亮器（使用修改后的 LogcatHighlighter 类）
        self.highlighter = LogcatHighlighter(self.log_text.document())
        self.highlighter.setup_level_rules(self.level_filters)   # 设置级别高亮规则

    def start_logcat(self):
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        self.process.finished.connect(self.on_finished)

        args = ["-s", self.serial, "logcat", "-v", "threadtime"]
        self.process.start(self.adb_client.adb_path, args)

    def on_ready_read(self):
        if self.paused:
            return
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.splitlines():
            if self.should_show_line(line):
                self.append_log(line)

    def should_show_line(self, line: str) -> bool:
        level_char = None
        for ch in ['V', 'D', 'I', 'W', 'E', 'F']:
            if f' {ch}/' in line or f'\t{ch}/' in line:
                level_char = ch
                break
        if level_char and level_char not in self.level_filters:
            return False
        #        pkg = self.package_filter.text().strip()
        #        if pkg and pkg not in line:
        #            return False
        return True

    def append_log(self, text: str):
        self.log_text.appendPlainText(text)
        if not self.paused:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)

    def on_level_changed(self, index):
        level_map = {0: ['V', 'D', 'I', 'W', 'E', 'F'],
                     1: ['V'], 2: ['D'], 3: ['I'], 4: ['W'], 5: ['E'], 6: ['F']}
        self.level_filters = level_map.get(index, ['V', 'D', 'I', 'W', 'E', 'F'])
        self.highlighter.setup_level_rules(self.level_filters)
        self.highlighter.rehighlight()

    def apply_filters(self):
        pass

    #    def highlight_search(self):
    #        search_text = self.search_input.text().strip()
    #        if not search_text:
    #            self.highlighter.setup_rules(self.level_filters)
    #            self.highlighter.rehighlight()
    #            return
    #        # 简单的搜索高亮：使用 QTextEdit 的 find 功能
    #        cursor = self.log_text.textCursor()
    #        cursor.movePosition(QTextCursor.Start)
    #        self.log_text.setTextCursor(cursor)
    #        self.log_text.find(search_text)
    def highlight_search(self):
        search_text = self.search_input.text().strip()
        self.highlighter.set_search_text(search_text)
        # 可选：自动滚动到第一个匹配项
        if search_text:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.log_text.setTextCursor(cursor)
            self.log_text.find(search_text)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.setText("恢复" if self.paused else "暂停")

    def clear_log(self):
        self.log_text.clear()

    def save_log(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "保存日志", "logcat.txt", "文本文件 (*.txt)")
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "保存成功", f"日志已保存到 {file_path}")

    def on_finished(self):
        self.start_logcat()

    def stop(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.terminate()
            self.process.waitForFinished(2000)
