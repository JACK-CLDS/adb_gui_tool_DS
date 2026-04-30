"""
core/adb_client.py - ADB 命令异步执行封装（修正版）
"""

import subprocess
from pathlib import Path
from typing import List, Optional, Callable
from PyQt5.QtCore import QObject, QProcess, pyqtSignal


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

    def pull_sync(self, remote_path: str, local_path: str, device_serial: Optional[str] = None, timeout: int = 30):
        """同步拉取文件"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['pull', remote_path, local_path])
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise Exception(result.stderr or result.stdout)

    def push_sync(self, local_path: str, remote_path: str, device_serial: Optional[str] = None, timeout: int = 30):
        """同步推送文件"""
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['push', local_path, remote_path])
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise Exception(result.stderr or result.stdout)

    def pull_with_progress(self, remote_path: str, local_path: str, device_serial: Optional[str] = None,
                           progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """
        同步拉取文件，实时解析进度并回调
        progress_callback: 接收百分比整数 (0-100)
        返回是否成功
        """
        import re
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['pull', remote_path, local_path])
        
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True, bufsize=1)
        last_percent = -1
        for line in process.stdout:
            # adb pull 输出格式: "   XX%   (XX MB/s)  ..."
            print(f"[DEBUG] pull line: {line.strip()}")
            match = re.search(r'(\d+)%', line)
            if match:
                percent = int(match.group(1))
                if percent != last_percent and progress_callback:
                    progress_callback(percent)
                    last_percent = percent
        process.wait()
        return process.returncode == 0

    def push_with_progress(self, local_path: str, remote_path: str, device_serial: Optional[str] = None,
                           progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """
        同步推送文件，实时解析进度并回调
        """
        import re
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['push', local_path, remote_path])
        
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True, bufsize=1)
        last_percent = -1
        for line in process.stdout:
            # adb push 输出格式: "   XX%   (XX MB/s)  ..."
            print(f"[DEBUG] push line: {line.strip()}")   # 添加这一行
            match = re.search(r'(\d+)%', line)
            if match:
                percent = int(match.group(1))
                if percent != last_percent and progress_callback:
                    progress_callback(percent)
                    last_percent = percent
        process.wait()
        return process.returncode == 0

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

    def disconnect_device(self, address: str, callback: Callable[[bool, str], None] = None):
        def handle(exit_code, stdout, stderr):
            if callback:
                callback(exit_code == 0, stdout.strip() or stderr.strip())
        self._exec(['disconnect', address], callback=handle)

    def shell(self, command: str, device_serial: Optional[str] = None,
            callback: Optional[Callable[[int, str, str], None]] = None):
        args = ["shell", command]
        self._exec(args, device_serial, callback=callback)

    def shell_sync(self, command: str, device_serial: Optional[str] = None, timeout: int = 5) -> str:
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

    def send_keyevent(self, keycode, device_serial=None):
        """发送单个按键事件"""
        args = ['input', 'keyevent', str(keycode)]
        self._exec(args, device_serial)

    def send_text(self, text, device_serial=None):
        """发送文本字符串（需要转义空格等）"""
        # 对文本中的空格、引号等特殊字符进行转义
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
        args = ['input', 'text', escaped]
        self._exec(args, device_serial)

    def get_app_icon_data(self, package: str, apk_path: str, device_serial: Optional[str] = None) -> Optional[bytes]:
        """
        从设备上获取应用的图标数据（PNG 字节流）。
        先尝试通过 dumpsys 获取图标资源路径，再使用 toybox unzip 提取。
        如果失败则回退到拉取整个 APK 并从 ZIP 中提取。
        """
        # 1. 获取图标的资源路径
        out = self.shell_sync(f"dumpsys package {package}", device_serial, timeout=5)
        icon_res_path = None
        for line in out.splitlines():
            if 'icon=' in line:
                # 尝试多种格式：icon=0x7f020000 /path/to/ic_launcher.png
                # 或 icon=7f030000 res/drawable/ic_launcher.png
                import re
                match = re.search(r'icon=\S+\s+(\S+\.png)', line)
                if match:
                    icon_res_path = match.group(1)
                    break
        if not icon_res_path:
            return self._get_icon_fallback(apk_path, device_serial=device_serial)

        # 2. 用 toybox unzip 提取图标到临时文件
        tmp_remote = f"/sdcard/_{package}.png"
        self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
        cmd = f"toybox unzip -p '{apk_path}' '{icon_res_path}' > {tmp_remote} 2>/dev/null"
        self.shell_sync(cmd, device_serial, timeout=5)

        check = self.shell_sync(f"ls -l {tmp_remote} 2>/dev/null", device_serial, timeout=3)
        if "No such file" in check or not check.strip():
            self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
            return self._get_icon_fallback(apk_path, icon_res_path, device_serial)

        # 3. 读取临时文件内容
        import subprocess
        args = [self.adb_path]
        if device_serial:
            args.extend(['-s', device_serial])
        args.extend(['exec-out', 'cat', tmp_remote])
        try:
            result = subprocess.run(args, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
                return result.stdout
        except Exception as e:
            print(f"Failed to read icon temp file: {e}")
        finally:
            self.shell_sync(f"rm -f {tmp_remote}", device_serial, timeout=1)
        return None

    def _get_icon_fallback(self, apk_path: str, icon_res_path: Optional[str] = None, device_serial: Optional[str] = None) -> Optional[bytes]:
        """备用方案：拉取整个 APK 到本地，用 zipfile 提取图标"""
        import tempfile
        import zipfile
        import os
        try:
            tmp_local = tempfile.mktemp(suffix=".apk")
            self.pull_sync(apk_path, tmp_local, device_serial, timeout=60)
            with zipfile.ZipFile(tmp_local, 'r') as zf:
                names = zf.namelist()
                # 如果提供了具体路径，优先精确匹配
                if icon_res_path:
                    if icon_res_path in names:
                        data = zf.read(icon_res_path)
                        os.unlink(tmp_local)
                        return data
                    # 大小写不敏感搜索
                    lower = icon_res_path.lower()
                    for n in names:
                        if n.lower() == lower:
                            data = zf.read(n)
                            os.unlink(tmp_local)
                            return data
                # 否则查找所有 ic_launcher*.png，取最大文件
                candidates = [n for n in names if 'ic_launcher' in n.lower() and n.endswith('.png')]
                if candidates:
                    candidates.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
                    data = zf.read(candidates[0])
                    os.unlink(tmp_local)
                    return data
            os.unlink(tmp_local)
        except Exception as e:
            print(f"Fallback icon extraction failed: {e}")
        return None
