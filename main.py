"""
main.py - 程序入口

功能：
    - 检查系统依赖（adb、scrcpy）
    - 加载配置，处理首次运行逻辑
    - 显示主窗口
    - 异常处理和日志记录
"""

import sys
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils
from core.adb_client import AdbClient
from ui.main_window import MainWindow


def check_dependencies():
    """
    检查必要的依赖（adb 必须，scrcpy 可选）
    返回 (adb_ok, adb_path, scrcpy_ok, scrcpy_path)
    """
    settings = ConfigManager.get_settings()
    manual_adb = settings.get("adb_path", "")
    manual_scrcpy = settings.get("scrcpy_path", "")

    adb_path = SystemUtils.find_adb(manual_adb)
    scrcpy_path = SystemUtils.find_scrcpy(manual_scrcpy)

    adb_ok = adb_path is not None
    scrcpy_ok = scrcpy_path is not None

    # 如果手动路径无效但自动找到了，更新配置
    if not adb_ok and manual_adb:
        # 手动路径无效，清除配置
        ConfigManager.set_setting("adb_path", "")
    elif adb_ok and manual_adb != adb_path:
        # 自动找到的路径与手动不同，保存自动路径（让用户知道）
        ConfigManager.set_setting("adb_path", adb_path)

    if not scrcpy_ok and manual_scrcpy:
        ConfigManager.set_setting("scrcpy_path", "")
    elif scrcpy_ok and manual_scrcpy != scrcpy_path:
        ConfigManager.set_setting("scrcpy_path", scrcpy_path)

    return adb_ok, adb_path, scrcpy_ok, scrcpy_path


def show_missing_adb_dialog():
    """显示缺少 adb 的对话框，引导用户设置"""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle("缺少 ADB")
    msg.setText("未找到 ADB 可执行文件。\n\n"
                "请确保已安装 Android SDK Platform Tools，\n"
                "或在全局设置中手动指定 adb 路径。\n\n"
                "是否立即打开全局设置？")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    return msg.exec_() == QMessageBox.Yes


def show_first_run_wizard():
    """首次运行向导：选择语言，设置 adb 路径（可选）"""
    # 简化：只提示用户去设置，或者自动检测
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("欢迎使用 ADB GUI Tool")
    msg.setText("检测到首次运行。\n\n"
                "程序将自动检测系统中的 ADB。\n"
                "如果自动检测失败，请前往「全局设置」手动指定 adb 路径。\n\n"
                "现在是否打开全局设置？")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    return msg.exec_() == QMessageBox.Yes


def main():
    """程序主入口"""
    app = QApplication(sys.argv)
    app.setApplicationName("ADB GUI Tool")
    app.setOrganizationName("YourName")  # 可用于 QSettings

    # 可选：启动画面
    splash = None
    # if Path("splash.png").exists():
    #     splash = QSplashScreen(QPixmap("splash.png"))
    #     splash.show()
    #     app.processEvents()

    # 1. 检查配置目录是否存在（已由 config_manager 自动创建）
    # 2. 检查是否为首次运行（通过判断 settings.json 中的某个标志）
    settings = ConfigManager.get_settings()
    is_first_run = settings.get("first_run", True)

    # 3. 检查依赖
    adb_ok, adb_path, scrcpy_ok, scrcpy_path = check_dependencies()

    # 4. 处理缺少 adb 的情况
    if not adb_ok:
        # 如果是首次运行，提示向导；否则直接报错并引导设置
        if is_first_run:
            open_settings = show_first_run_wizard()
        else:
            open_settings = show_missing_adb_dialog()

        if open_settings:
            # 由于全局设置对话框尚未实现，此处暂时退出并提示
            QMessageBox.information(None, "提示", "请稍后通过「全局设置」菜单配置 ADB 路径后重启程序。")
            sys.exit(0)
        else:
            sys.exit(1)

    # 5. 记录首次运行已完成
    if is_first_run:
        ConfigManager.set_setting("first_run", False)
        # 设置默认语言（根据系统）
        lang = SystemUtils.get_system_language()
        ConfigManager.set_setting("language", lang)

    # 6. 创建 AdbClient
    adb_client = AdbClient(adb_path)

    # 7. 创建主窗口
    window = MainWindow(adb_client)
    window.show()

    # 关闭启动画面（如果有）
    if splash:
        splash.finish(window)

    # 可选：延迟显示欢迎消息
    if is_first_run:
        QTimer.singleShot(500, lambda: QMessageBox.information(window, "提示",
            "您可以在「全局设置」中调整语言、刷新间隔等。\n"
            "设备控制窗口的功能将逐步完善。"))

    # 8. 运行事件循环
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 捕获未处理的异常，显示错误对话框
        error_msg = f"程序发生未预期的错误:\n{str(e)}\n\n{traceback.format_exc()}"
        QMessageBox.critical(None, "错误", error_msg)
        sys.exit(1)