"""
core/adb_client.py - ADB 命令异步执行封装

使用 QProcess 执行 adb 命令，通过信号传递输出结果。
支持指定设备序列号、超时控制、取消操作。
"""

from PyQt5.QtCore import QObject, QProcess, pyqtSignal, QByteArray
from typing import Optional, List, Callable
import tempfile
import os


class AdbProcess(QObject):
    """单个 ADB 命令的异步执行器"""

    finished = pyqtSignal(int, bytes, bytes)  # exit_code, stdout, stderr
    output_ready = pyqtSignal(str)  # 实时输出（用于 logcat 等持续命令）

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        self.adb_path = adb_path
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def run(self, args: List[str], device_serial: Optional[str] = None):
        """
        执行 ADB 命令
        :param args: adb 参数列表，例如 ['devices']
        :param device_serial: 如果提供，自动添加 -s serial 参数
        """
        full_args = []
        if device_serial:
            full_args.extend(['-s', device_serial])
        full_args.extend(args)
        self.process.start(self.adb_path, full_args)

    def kill(self):
        """强制终止进程"""
        if self.process.state() == QProcess.Running:
            self.process.kill()
            self.process.waitForFinished(1000)

    def _on_stdout(self):
        data = self.process.readAllStandardOutput()
        if not data.isEmpty():
            self.output_ready.emit(str(data, encoding='utf-8', errors='ignore'))

    def _on_stderr(self):
        data = self.process.readAllStandardError()
        if not data.isEmpty():
            self.output_ready.emit(str(data, encoding='utf-8', errors='ignore'))

    def _on_finished(self, exit_code, exit_status):
        stdout = self.process.readAllStandardOutput().data()
        stderr = self.process.readAllStandardError().data()
        self.finished.emit(exit_code, stdout, stderr)


class AdbClient(QObject):
    """
    ADB 客户端管理器，提供常用的 ADB 操作。
    内部使用 AdbProcess 执行命令，所有方法都是异步的，通过回调或信号返回结果。
    """

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        self.adb_path = adb_path

    def _exec(self, args: List[str], device_serial: Optional[str] = None,
              callback: Optional[Callable[[int, str, str], None]] = None):
        """
        执行一个 ADB 命令，不等待结果。
        :param callback: 回调函数，参数 (exit_code, stdout_str, stderr_str)
        """
        proc = AdbProcess(self.adb_path, self)
        if callback:
            proc.finished.connect(lambda code, out, err: callback(code, out.decode('utf-8', errors='ignore'), err.decode('utf-8', errors='ignore')))
        proc.run(args, device_serial)
        # 保存 proc 防止被回收（后续可以通过 parent 管理，简单起见让它在回调后自删除）
        proc.finished.connect(proc.deleteLater)
        return proc

    # ---------- 基础命令 ----------
    def devices(self, callback: Callable[[List[tuple]], None]):
        """
        获取设备列表，回调参数为 [(serial, state), ...]
        state 可以是 'device', 'offline', 'unauthorized' 等
        """
        def handle(exit_code, stdout, stderr):
            devices = []
            if exit_code == 0:
                lines = stdout.strip().split('\n')[1:]  # 跳过第一行 "List of devices attached"
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            devices.append((parts[0], parts[1]))
            callback(devices)
        self._exec(['devices'], callback=handle)

    def connect_device(self, address: str, callback: Callable[[bool, str], None]):
        """连接网络设备，回调 (成功标志, 消息)"""
        def handle(exit_code, stdout, stderr):
            success = exit_code == 0 and ("connected" in stdout or "already connected" in stdout)
            msg = stdout.strip() or stderr.strip()
            callback(success, msg)
        self._exec(['connect', address], callback=handle)

    def disconnect_device(self, address: str, callback: Callable[[bool, str], None] = None):
        """断开网络设备"""
        def handle(exit_code, stdout, stderr):
            if callback:
                callback(exit_code == 0, stdout.strip())
        self._exec(['disconnect', address], callback=handle)

    def reboot(self, device_serial: str, mode: str = "", callback=None):
        """
        重启设备，mode 可以是 "bootloader", "recovery", 或空字符串表示普通重启
        """
        args = ['reboot']
        if mode:
            args.append(mode)
        self._exec(args, device_serial, callback=callback)

    def screenshot(self, device_serial: str, save_path: str, callback=None):
        """
        截屏并保存到本地文件
        :param save_path: 本地保存路径（必须包含 .png 扩展名）
        """
        # 先截图到设备临时文件，再 pull
        tmp_path = "/sdcard/screenshot_tmp.png"
        # 使用 exec-out 直接获取图片数据
        proc = AdbProcess(self.adb_path, self)
        proc.output_ready.connect(lambda data: self._save_screenshot_data(data, save_path, callback))
        proc.run(['exec-out', 'screencap', '-p'], device_serial)
        # TODO: 注意 exec-out 输出的原始数据可能分多次接收，需要缓存合并。这里简化，实际需要处理。
        # 更可靠的方式：使用临时文件
        # 简单起见，先实现两步法：
        # self._exec(['shell', 'screencap', tmp_path], device_serial, lambda code, out, err: ...)

    # 更多方法（install, uninstall, pull, push, logcat, shell 等）后续逐步添加
    
    # 在 AdbClient 类中添加以下方法

    def shell(self, command: str, device_serial: Optional[str] = None,
            callback: Optional[Callable[[int, str, str], None]] = None):
        """
        执行 adb shell 命令
        :param command: shell 命令
        :param device_serial: 设备序列号
        :param callback: 回调函数 (exit_code, stdout_str, stderr_str)
        """
        args = ["shell", command]
        self._exec(args, device_serial, callback=callback)

    def reboot(self, device_serial: str, mode: str = "",
            callback: Optional[Callable[[int, str, str], None]] = None):
        """重启设备，mode 可以是 "recovery", "bootloader", 或空字符串"""
        args = ["reboot"]
        if mode:
            args.append(mode)
        self._exec(args, device_serial, callback=callback)

    def install(self, apk_path: str, device_serial: Optional[str] = None,
            callback: Optional[Callable[[int, str, str], None]] = None):
        """安装APK"""
        args = ["install", "-r", apk_path]  # -r 覆盖安装
        self._exec(args, device_serial, callback=callback)

    def uninstall(self, package: str, device_serial: Optional[str] = None,
              callback: Optional[Callable[[int, str, str], None]] = None):
        """卸载应用"""
        args = ["uninstall", package]
        self._exec(args, device_serial, callback=callback)

    def pull(self, remote_path: str, local_path: str, device_serial: Optional[str] = None,
            callback: Optional[Callable[[int, str, str], None]] = None):
        """从设备拉取文件到本地"""
        args = ["pull", remote_path, local_path]
        self._exec(args, device_serial, callback=callback)
