"""
utils/system_utils.py - 系统相关工具函数 (System utility functions)

功能：
    - 检测操作系统类型 (Detect OS: Windows/Linux/macOS)
    - 在常见位置查找 adb 和 scrcpy 可执行文件 (Locate adb & scrcpy binaries)
    - 获取系统语言环境 (Get system language locale)
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class SystemUtils:
    """系统工具类，提供静态方法 (Utility class with static methods)"""

    # ---------- 操作系统检测 (OS detection) ----------

    @staticmethod
    def get_os() -> str:
        """
        返回当前操作系统名称 (Return current OS name):
            'windows', 'linux', 'darwin' (macOS), 或 'unknown'
        """
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

    # ---------- 系统语言 (System language) ----------

    @staticmethod
    def get_system_language() -> str:
        """
        获取系统语言，返回格式如 'en', 'zh_CN', 'zh_TW'。
        用于首次运行时自动选择界面语言。
        Get system language for initial UI language selection.
        """
        lang_code = os.environ.get('LANG', 'en_US').split('.')[0]
        if lang_code.startswith('zh_CN'):
            return 'zh_CN'
        elif lang_code.startswith('zh_TW') or lang_code.startswith('zh_HK'):
            return 'zh_TW'
        elif lang_code.startswith('zh'):
            return 'zh_CN'
        elif lang_code.startswith('en'):
            return 'en'
        else:
            return 'en'  # 默认英文 (default English)

    # ---------- 查找 ADB (Find ADB) ----------

    @staticmethod
    def find_adb(manual_path: Optional[str] = None) -> Optional[str]:
        """
        查找 adb 可执行文件路径 (Find adb executable path)。
        搜索顺序 (Search order):
            1. manual_path（用户指定的路径，如果有效 / user-specified path if valid）
            2. 项目目录下的 ./scrcpy/adb (local project directory)
            3. 环境变量 PATH 中的 adb (system PATH)
            4. 常见 SDK 安装路径 (common SDK install paths)
        """
        # 1. 用户手动指定 (User-provided)
        if manual_path and Path(manual_path).exists():
            return str(Path(manual_path).resolve())

        # 2. 项目内自带的 adb (Bundled with project)
        local_adb = Path.cwd() / "scrcpy" / ("adb.exe" if SystemUtils.is_windows() else "adb")
        if local_adb.exists():
            return str(local_adb.resolve())

        # 3. 系统 PATH 中的 adb
        adb_path = shutil.which('adb')
        if adb_path:
            return adb_path

        # 4. 常见安装路径 (Common install paths)
        home = Path.home()
        common_paths = []
        if SystemUtils.is_mac():
            common_paths = [
                home / "Library/Android/sdk/platform-tools/adb",
                Path("/usr/local/bin/adb")
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
                Path("/usr/bin/adb")
            ]

        for p in common_paths:
            if p.exists():
                return str(p.resolve())

        return None

    # ---------- 查找 scrcpy (Find scrcpy) ----------

    @staticmethod
    def find_scrcpy(manual_path: Optional[str] = None) -> Optional[str]:
        """
        查找 scrcpy 可执行文件路径 (Find scrcpy executable path)。
        搜索顺序与 find_adb 类似，并额外考虑 macOS 下的应用程序包。
        """
        if manual_path and Path(manual_path).exists():
            return str(Path(manual_path).resolve())

        # 系统 PATH
        scrcpy_path = shutil.which('scrcpy')
        if scrcpy_path:
            return scrcpy_path

        # 常见安装路径
        home = Path.home()
        common_paths = []
        if SystemUtils.is_mac():
            common_paths = [
                Path("/usr/local/bin/scrcpy"),
                home / "scrcpy/scrcpy"
            ]
        elif SystemUtils.is_windows():
            common_paths = [
                Path("C:/scrcpy/scrcpy.exe")
            ]
        elif SystemUtils.is_linux():
            common_paths = [
                Path("/usr/bin/scrcpy"),
                home / "scrcpy/scrcpy"
            ]

        for p in common_paths:
            if p.exists():
                return str(p.resolve())

        return None

    # ---------- 版本检测 (Version checks) ----------

    @staticmethod
    def check_adb_version(adb_path: str) -> Tuple[bool, str]:
        """
        检查 adb 是否可用 (Verify adb is usable)
        返回 (成功与否, 版本信息或错误消息).
        """
        if not adb_path or not Path(adb_path).exists():
            return False, f"adb not found at {adb_path}"
        try:
            result = subprocess.run([adb_path, "version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version_line = result.stdout.splitlines()[0] if result.stdout else ""
                return True, version_line
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def check_scrcpy_version(scrcpy_path: str) -> Tuple[bool, str]:
        """检查 scrcpy 是否可用 (Verify scrcpy is usable)"""
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
