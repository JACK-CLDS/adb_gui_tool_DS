#!/usr/bin/env python3
"""
main.py - ADB GUI Tool 程序入口 (Application entry point)

启动时自动检查 ADB 和 scrcpy 依赖，若未找到则引导用户配置。
On startup, automatically checks for ADB and scrcpy; if missing, prompts user to configure.
"""

import sys
import os
import platform
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer

from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils
from core.adb_client import AdbClient
from ui.main_window import MainWindow

# macOS 需要设置 QT_IM_MODULE 避免输入法兼容性问题
# macOS requires QT_IM_MODULE to avoid IME compatibility issues
if platform.system() == "Darwin":
    os.environ["QT_IM_MODULE"] = "simple"


def check_dependencies():
    """
    检查 ADB 和 scrcpy 依赖 (Check ADB & scrcpy dependencies)
    返回：(adb_ok, adb_path, scrcpy_ok, scrcpy_path)
    """
    settings = ConfigManager.get_settings()
    manual_adb = settings.get("adb_path", "")
    manual_scrcpy = settings.get("scrcpy_path", "")

    # --- 查找 ADB ---
    adb_path = SystemUtils.find_adb(manual_adb)
    adb_ok = False
    if adb_path:
        ok, _ = SystemUtils.check_adb_version(adb_path)
        adb_ok = ok

    # 自动更新配置：清除无效路径，或保存找到的路径
    if not adb_ok and manual_adb:
        ConfigManager.set_setting("adb_path", "")
    elif adb_ok and manual_adb != adb_path:
        ConfigManager.set_setting("adb_path", adb_path)

    # --- 查找 scrcpy ---
    scrcpy_path = SystemUtils.find_scrcpy(manual_scrcpy)
    scrcpy_ok = scrcpy_path is not None
    if not scrcpy_ok and manual_scrcpy:
        ConfigManager.set_setting("scrcpy_path", "")
    elif scrcpy_ok and manual_scrcpy != scrcpy_path:
        ConfigManager.set_setting("scrcpy_path", scrcpy_path)

    return adb_ok, adb_path, scrcpy_ok, scrcpy_path


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ADB GUI Tool")
    app.setOrganizationName("YourName")

    # 检查依赖
    adb_ok, adb_path, scrcpy_ok, scrcpy_path = check_dependencies()

    # 创建 ADB 客户端（未找到时为 None）
    adb_client = None
    if adb_ok:
        adb_client = AdbClient(adb_path)
        print(f"[INFO] 使用 ADB: {adb_path}")
    else:
        print("[WARN] 未找到可用的 ADB，请在设置中配置")

    # 创建并显示主窗口
    window = MainWindow(adb_client)
    window.show()

    # 如果没有可用 ADB，延迟 500ms 自动打开设置对话框
    if not adb_ok:
        QTimer.singleShot(500, lambda: window.open_settings_dialog(force=True))

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        input("按回车键退出... (Press Enter to exit)")  # 防止控制台闪退
        sys.exit(1)
