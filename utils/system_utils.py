"""
utils/system_utils.py - 系统相关工具函数

功能：
    - 检测操作系统（Windows/Linux/macOS）
    - 在常见位置查找 adb 和 scrcpy 可执行文件
    - 获取系统语言环境
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class SystemUtils:
    """系统工具类，提供静态方法"""

    @staticmethod
    def get_os() -> str:
        """返回当前操作系统名称: 'windows', 'linux', 'darwin'（macOS）"""
        sys_platform = platform.system().lower()
        if sys_platform == 'windows':
            return 'windows'
        elif sys_platform == 'linux':
            return 'linux'
        elif sys_platform == 'darwin':
            return 'darwin'
        else:
            return 'unknown'

    @staticmethod
    def is_windows() -> bool:
        return SystemUtils.get_os() == 'windows'

    @staticmethod
    def is_linux() -> bool:
        return SystemUtils.get_os() == 'linux'

    @staticmethod
    def is_mac() -> bool:
        return SystemUtils.get_os() == 'darwin'

    @staticmethod
    def get_system_language() -> str:
        """
        获取系统语言，返回格式如 'en', 'zh_CN', 'zh_TW'。
        用于首次运行时自动选择界面语言。
        """
        lang_code = os.environ.get('LANG', 'en_US').split('.')[0]
        # 处理 macOS 下的特殊情况
        if lang_code.startswith('zh_CN'):
            return 'zh_CN'
        elif lang_code.startswith('zh_TW') or lang_code.startswith('zh_HK'):
            return 'zh_TW'
        elif lang_code.startswith('zh'):
            return 'zh_CN'
        elif lang_code.startswith('en'):
            return 'en'
        else:
            return 'en'  # 默认英文

    @staticmethod
    def find_adb(manual_path: Optional[str] = None) -> Optional[str]:
        """
        查找 adb 可执行文件路径。
        搜索顺序：
            1. manual_path（用户指定的路径）
            2. 环境变量 PATH 中的 adb
            3. 常见安装路径（macOS: ~/Library/Android/sdk/platform-tools, 
               Windows: %LOCALAPPDATA%/Android/Sdk/platform-tools,
               Linux: ~/Android/Sdk/platform-tools）
            4. 当前目录下的 scrcpy/adb（用户提到的特殊路径）
        返回绝对路径字符串，如果未找到则返回 None。
        """
        # 1. 手动指定路径
        if manual_path and Path(manual_path).exists():
            return str(Path(manual_path).resolve())

        # 2. 查找系统 PATH
        adb_path = shutil.which('adb')
        if adb_path:
            return adb_path

        # 3. 常见 SDK 路径
        home = Path.home()
        common_paths = []
        if SystemUtils.is_mac():
            common_paths = [
                home / "Library/Android/sdk/platform-tools/adb",
                "/usr/local/bin/adb"
            ]
        elif SystemUtils.is_windows():
            local_appdata = os.environ.get('LOCALAPPDATA', '')
            common_paths = [
                Path(local_appdata) / "Android/Sdk/platform-tools/adb.exe",
                Path("C:/Android/platform-tools/adb.exe")
            ]
        elif SystemUtils.is_linux():
            common_paths = [
                home / "Android/Sdk/platform-tools/adb",
                "/usr/bin/adb"
            ]

        for p in common_paths:
            if p.exists():
                return str(p.resolve())

        # 4. 当前目录下的 ./scrcpy/adb（注意 Windows 下可能带 .exe）
        local_adb = Path.cwd() / "scrcpy" / ("adb.exe" if SystemUtils.is_windows() else "adb")
        if local_adb.exists():
            return str(local_adb.resolve())

        return None

    @staticmethod
    def find_scrcpy(manual_path: Optional[str] = None) -> Optional[str]:
        """
        查找 scrcpy 可执行文件路径。
        搜索顺序类似 find_adb，但还包括 macOS 下的应用程序包。
        """
        if manual_path and Path(manual_path).exists():
            return str(Path(manual_path).resolve())

        scrcpy_path = shutil.which('scrcpy')
        if scrcpy_path:
            return scrcpy_path

        # 常见路径
        home = Path.home()
        common_paths = []
        if SystemUtils.is_mac():
            # macOS 下 scrcpy 通常放在 /usr/local/bin 或通过 brew 安装
            common_paths = [
                "/usr/local/bin/scrcpy",
                home / "scrcpy/scrcpy"   # 用户手动编译的常见位置
            ]
        elif SystemUtils.is_windows():
            common_paths = [
                Path("C:/scrcpy/scrcpy.exe")
            ]
        elif SystemUtils.is_linux():
            common_paths = [
                "/usr/bin/scrcpy",
                home / "scrcpy/scrcpy"
            ]

        for p in common_paths:
            if p.exists():
                return str(p.resolve())

        return None

    @staticmethod
    def check_adb_version(adb_path: str) -> Tuple[bool, str]:
        """
        执行 adb version 检查 adb 是否可用，返回 (是否成功, 版本信息或错误消息)
        """
        if not adb_path or not Path(adb_path).exists():
            return False, f"adb not found at {adb_path}"
        try:
            result = subprocess.run([adb_path, "version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # 提取版本号的第一行
                version_line = result.stdout.splitlines()[0] if result.stdout else ""
                return True, version_line
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def check_scrcpy_version(scrcpy_path: str) -> Tuple[bool, str]:
        """检查 scrcpy 版本"""
        if not scrcpy_path or not Path(scrcpy_path).exists():
            return False, f"scrcpy not found at {scrcpy_path}"
        try:
            result = subprocess.run([scrcpy_path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True, result.stdout.splitlines()[0] if result.stdout else ""
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)