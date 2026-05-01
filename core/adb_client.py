"""
core/adb_client.py - ADB 命令执行封装 (Encapsulation of ADB command execution)

支持异步 (QProcess) 和同步 (subprocess) 两种模式。
Supports both async (QProcess) and sync (subprocess) modes.
"""

import re
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Callable

from PyQt5.QtCore import QObject, QProcess, pyqtSignal


class AdbProcess(QObject):
    """
    单个 ADB 命令的异步执行器 (Async executor for a single ADB command)
    使用 QProcess 实现非阻塞执行，可实时获取输出。
    """
    finished = pyqtSignal(int, bytes, bytes)      # (exit_code, stdout, stderr)
    output_ready = pyqtSignal(str)                # 实时输出 (real-time output)

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        self.adb_path = adb_path
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)      # 合并 stdout/stderr
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def run(self, args: List[str], device_serial: Optional[str] = None):
        """
        启动命令 (Start the command)
        :param args: 命令参数 (command arguments, e.g. ['shell', 'ls'])
        :param device_serial: 目标设备序列号 (target device serial)
        """
        full_args = []
        if device_serial:
            full_args.extend(['-s', device_serial])
        full_args.extend(args)
        self.process.start(self.adb_path, full_args)

    def kill(self):
        """终止进程 (Kill the process)"""
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
        # In merged channel mode, all output is captured in stdout
        output = self.process.readAllStandardOutput().data()
        self.finished.emit(exit_code, output, b'')   # stderr is empty in merged mode


class AdbClient(QObject):
    """
    ADB 客户端核心类 (Core ADB client class)
    封装了常用的 ADB 操作，提供异步和同步接口。
    """

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        if not adb_path or not Path(adb_path).exists():
            raise ValueError(f"Invalid adb path: {adb_path}")
        self.adb_path = adb_path

    # ---------- 基础命令执行 (Basic command execution) ----------

    def _exec(self, args: List[str], device_serial: Optional[str] = None,
              callback: Optional[Callable[[int, str, str], None]] = None) -> AdbProcess:
        """
        异步执行 ADB 命令 (Execute ADB command asynchronously)
        :param args: 命令参数 (command arguments)
        :param device_serial: 目标设备序列号 (target device serial)
        :param callback: 完成回调，参数为 (exit_code, stdout, stderr)
        :return: AdbProcess 实例，可用于实时读取输出
        """
        proc = AdbProcess(self.adb_path, self)
        if callback:
            proc.finished.connect(lambda code, out, err: callback(
                code, out.decode('utf-8', errors='ignore'),
                err.decode('utf-8', errors='ignore')))
        proc.run(args, device_serial)
        proc.finished.connect(proc.deleteLater)
        return proc

    def shell_sync(self, command: str, device_serial: Optional[str] = None, timeout: int = 5) -> str:
        """
        同步执行 shell 命令 (Execute shell command synchronously)
        :param command: 要执行的 shell 命令 (shell command string)
        :param device_serial: 目标设备序列号 (target device serial)
        :param timeout: 超时秒数 (timeout in seconds)
        :return: 命令输出字符串 (stdout + stderr)
        """
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['shell', command])
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            print(f"[WARN] shell_sync timeout for command: {command}")
            return ""
        except Exception as e:
            print(f"[WARN] shell_sync error: {e}")
            return ""

    # ---------- 设备管理 (Device management) ----------

    def devices(self, callback: Callable[[List[tuple]], None]):
        """
        获取设备列表 (Get device list)
        :param callback: 回调，参数为 [(serial, state), ...]
        """
        try:
            result = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split('\n')[1:]   # Skip header
            devices = []
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        devices.append((parts[0], parts[1]))
            callback(devices)
        except Exception as e:
            print(f"adb devices failed: {e}")
            callback([])

    def connect_device(self, address: str, callback: Callable[[bool, str], None]):
        """连接到网络设备 (Connect to a network device)"""
        try:
            result = subprocess.run([self.adb_path, 'connect', address],
                                    capture_output=True, text=True, timeout=5)
            output = result.stdout + result.stderr
            success = (result.returncode == 0 and
                       ("connected" in output or "already connected" in output))
            callback(success, output.strip())
        except Exception as e:
            callback(False, str(e))

    def disconnect_device(self, address: str, callback: Callable[[bool, str], None] = None):
        """断开设备连接 (Disconnect a device)"""
        def handle(exit_code, stdout, stderr):
            if callback:
                callback(exit_code == 0, stdout.strip() or stderr.strip())
        self._exec(['disconnect', address], callback=handle)

    # ---------- 文件操作 (File operations) ----------

    def pull_sync(self, remote_path: str, local_path: str,
                  device_serial: Optional[str] = None, timeout: int = 30):
        """同步拉取文件 (Pull file from device)"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['pull', remote_path, local_path])
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise Exception(result.stderr or result.stdout)

    def push_sync(self, local_path: str, remote_path: str,
                  device_serial: Optional[str] = None, timeout: int = 30):
        """同步推送文件 (Push file to device)"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['push', local_path, remote_path])
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise Exception(result.stderr or result.stdout)

    def pull_with_progress(self, remote_path: str, local_path: str,
                           device_serial: Optional[str] = None,
                           progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """带进度回调的拉取文件 (Pull with progress percentage callback)"""
        return self._run_with_progress('pull', remote_path, local_path, device_serial, progress_callback)

    def push_with_progress(self, local_path: str, remote_path: str,
                           device_serial: Optional[str] = None,
                           progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """带进度回调的推送文件 (Push with progress percentage callback)"""
        return self._run_with_progress('push', local_path, remote_path, device_serial, progress_callback)

    def _run_with_progress(self, direction: str, source: str, target: str,
                           device_serial: Optional[str],
                           progress_callback: Optional[Callable[[int], None]]) -> bool:
        """
        通用带进度的文件传输 (Generic file transfer with progress)
        :param direction: 'pull' 或 'push'
        """
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend([direction, source, target])
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True, bufsize=1)
        last_percent = -1
        for line in process.stdout:
            match = re.search(r'(\d+)%', line)
            if match:
                percent = int(match.group(1))
                if percent != last_percent and progress_callback:
                    progress_callback(percent)
                    last_percent = percent
        process.wait()
        return process.returncode == 0

    # ---------- 应用管理 (Application management) ----------

    def install(self, apk_path: str, device_serial: Optional[str] = None,
                callback: Optional[Callable[[int, str, str], None]] = None):
        self._exec(["install", "-r", apk_path], device_serial, callback=callback)

    def uninstall(self, package: str, device_serial: Optional[str] = None,
                  callback: Optional[Callable[[int, str, str], None]] = None):
        self._exec(["uninstall", package], device_serial, callback=callback)

    def push(self, local_path: str, remote_path: str, device_serial: Optional[str] = None,
             callback: Optional[Callable[[int, str, str], None]] = None):
        self._exec(["push", local_path, remote_path], device_serial, callback=callback)

    def pull(self, remote_path: str, local_path: str, device_serial: Optional[str] = None,
             callback: Optional[Callable[[int, str, str], None]] = None):
        self._exec(["pull", remote_path, local_path], device_serial, callback=callback)

    def shell(self, command: str, device_serial: Optional[str] = None,
              callback: Optional[Callable[[int, str, str], None]] = None):
        self._exec(["shell", command], device_serial, callback=callback)

    # ---------- 系统操作 (System operations) ----------

    def reboot(self, device_serial: str, mode: str = "",
               callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["reboot"]
        if mode:
            args.append(mode)
        self._exec(args, device_serial, callback=callback)

    def send_keyevent(self, keycode: int, device_serial: Optional[str] = None):
        """发送按键事件 (Send keyevent)"""
        self._exec(['input', 'keyevent', str(keycode)], device_serial)

    def send_text(self, text: str, device_serial: Optional[str] = None):
        """发送文本 (Send text, escaping special characters)"""
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
        self._exec(['input', 'text', escaped], device_serial)

    # ---------- 图标提取 (Icon extraction) ----------

    def get_app_icon_data(self, package: str, apk_path: str,
                          device_serial: Optional[str] = None) -> Optional[bytes]:
        """
        获取应用图标数据 (Fetch app icon PNG bytes)
        优先使用设备上的 toybox unzip 直接解压，失败则拉取 APK 后本地解压。
        """
        # 1. 从 dumpsys 中解析图标资源路径
        icon_res_path = self._parse_icon_path(package, device_serial)
        if not icon_res_path:
            return self._get_icon_fallback(apk_path, device_serial=device_serial)

        # 2. 尝试用 toybox unzip 提取图标到临时文件
        tmp_remote = f"/sdcard/_{package}.png"
        self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
        cmd = f"toybox unzip -p '{apk_path}' '{icon_res_path}' > {tmp_remote} 2>/dev/null"
        self.shell_sync(cmd, device_serial, timeout=5)

        check = self.shell_sync(f"ls -l {tmp_remote} 2>/dev/null", device_serial, timeout=3)
        if "No such file" in check or not check.strip():
            self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
            return self._get_icon_fallback(apk_path, icon_res_path, device_serial)

        # 3. 回传临时文件内容
        data = self._adb_exec_out_read(tmp_remote, device_serial)
        self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
        return data

    def _parse_icon_path(self, package: str, device_serial: Optional[str]) -> Optional[str]:
        """从 dumpsys package 输出中提取图标资源路径"""
        out = self.shell_sync(f"dumpsys package {package}", device_serial, timeout=5)
        for line in out.splitlines():
            if 'icon=' in line:
                match = re.search(r'icon=\S+\s+(\S+\.png)', line)
                if match:
                    return match.group(1)
        return None

    def _adb_exec_out_read(self, remote_path: str, device_serial: Optional[str]) -> Optional[bytes]:
        """通过 exec-out 读取设备文件内容"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['exec-out', 'cat', remote_path])
        try:
            result = subprocess.run(args, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            print(f"Failed to read {remote_path} via exec-out: {e}")
        return None

    def _get_icon_fallback(self, apk_path: str, icon_res_path: Optional[str] = None,
                           device_serial: Optional[str] = None) -> Optional[bytes]:
        """
        备用方案：拉取整个 APK 到本地，用 zipfile 提取图标。
        Fallback: pull the entire APK and extract the icon locally.
        """
        try:
            tmp_local = tempfile.mktemp(suffix=".apk")
            self.pull_sync(apk_path, tmp_local, device_serial, timeout=60)
            with zipfile.ZipFile(tmp_local, 'r') as zf:
                names = zf.namelist()
                # 精确匹配目标路径
                if icon_res_path:
                    if icon_res_path in names:
                        data = zf.read(icon_res_path)
                        os.unlink(tmp_local)
                        return data
                    # 大小写不敏感搜索 (case-insensitive fallback)
                    lower = icon_res_path.lower()
                    for n in names:
                        if n.lower() == lower:
                            data = zf.read(n)
                            os.unlink(tmp_local)
                            return data
                # 无具体路径时，查找所有 ic_launcher*.png 取最大文件
                candidates = [n for n in names if 'ic_launcher' in n.lower() and n.endswith('.png')]
                if candidates:
                    candidates.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
                    data = zf.read(candidates[0])
                    os.unlink(tmp_local)
                    return data
            os.unlink(tmp_local)
        except Exception as e:
            print(f"Icon fallback extraction failed: {e}")
        return None
