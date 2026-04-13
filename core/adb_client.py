"""
core/adb_client.py - ADB 命令异步执行封装（修正版）
"""

from pathlib import Path
from typing import List, Optional, Callable
from PyQt5.QtCore import QObject, QProcess, pyqtSignal

import subprocess

class AdbProcess(QObject):
    """单个 ADB 命令的异步执行器"""
    finished = pyqtSignal(int, bytes, bytes)  # exit_code, stdout, stderr
    output_ready = pyqtSignal(str)  # 实时输出

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        self.adb_path = adb_path
        self.process = QProcess(self)  # 关键：创建 QProcess 实例
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def run(self, args: List[str], device_serial: Optional[str] = None):
        full_args = []
        if device_serial:
            full_args.extend(['-s', device_serial])
        full_args.extend(args)
        self.process.start(self.adb_path, full_args)

    def kill(self):
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
        # 合并模式下，所有输出都在标准输出中
        output = self.process.readAllStandardOutput().data()
        self.finished.emit(exit_code, output, b'')  # stderr 为空


class AdbClient(QObject):
    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        if not adb_path or not Path(adb_path).exists():
            raise ValueError(f"Invalid adb path: {adb_path}")
        self.adb_path = adb_path

    def _exec(self, args: List[str], device_serial: Optional[str] = None,
              callback: Optional[Callable[[int, str, str], None]] = None):
        proc = AdbProcess(self.adb_path, self)
        if callback:
            proc.finished.connect(lambda code, out, err: callback(code, out.decode('utf-8', errors='ignore'), err.decode('utf-8', errors='ignore')))
        proc.run(args, device_serial)
        proc.finished.connect(proc.deleteLater)
        return proc

    def devices(self, callback: Callable[[List[tuple]], None]):
        """同步执行 adb devices 并回调"""
        try:
            result = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True, timeout=5)
            stdout = result.stdout
        except Exception as e:
            print(f"adb devices 失败: {e}")
            callback([])
            return
        devices = []
        lines = stdout.strip().split('\n')[1:]  # 跳过第一行 "List of devices attached"
        for line in lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    devices.append((parts[0], parts[1]))
        callback(devices)


    #dbg
    import subprocess  # 确保文件顶部有导入
    def devices_sync(self, callback: Callable[[List[tuple]], None]):
        """同步版本的 devices 命令，用于调试"""
        result = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True)
        print(f"[SYNC] devices stdout: {result.stdout}")
        print(f"[SYNC] devices stderr: {result.stderr}")
        devices = []
        lines = result.stdout.strip().split('\n')[1:]
        for line in lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    devices.append((parts[0], parts[1]))
        callback(devices)


    def connect_device(self, address: str, callback: Callable[[bool, str], None]):
        """同步执行 adb connect，解析输出"""
        try:
            result = subprocess.run([self.adb_path, 'connect', address], capture_output=True, text=True, timeout=5)
            output = result.stdout + result.stderr
            exit_code = result.returncode
            # 判断成功条件：exit_code 为 0 并且输出中包含 "connected" 或 "already connected"
            success = (exit_code == 0) and ("connected" in output or "already connected" in output)
            msg = output.strip()
            callback(success, msg)
        except Exception as e:
            callback(False, str(e))

    def shell(self, command: str, device_serial: Optional[str] = None,
            callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["shell", command]
        self._exec(args, device_serial, callback=callback)

    def shell_sync(self, command: str, device_serial: Optional[str] = None) -> str:
        """同步执行 shell 命令，返回输出字符串（用于设备信息等一次性加载）"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['shell', command])
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=5)
            # 合并 stdout 和 stderr
            return result.stdout + result.stderr
        except Exception as e:
            print(f"shell_sync error: {e}")
            return ""


    def reboot(self, device_serial: str, mode: str = "",
               callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["reboot"]
        if mode:
            args.append(mode)
        self._exec(args, device_serial, callback=callback)

    def install(self, apk_path: str, device_serial: Optional[str] = None,
                callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["install", "-r", apk_path]
        self._exec(args, device_serial, callback=callback)

    def uninstall(self, package: str, device_serial: Optional[str] = None,
                  callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["uninstall", package]
        self._exec(args, device_serial, callback=callback)

    def pull(self, remote_path: str, local_path: str, device_serial: Optional[str] = None,
             callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["pull", remote_path, local_path]
        self._exec(args, device_serial, callback=callback)

    def push(self, local_path: str, remote_path: str, device_serial: Optional[str] = None,
             callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["push", local_path, remote_path]
        self._exec(args, device_serial, callback=callback)
