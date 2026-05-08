#!/usr/bin/env python3
"""
main.py - ADB GUI Tool 程序入口 (Application entry point)

功能 (Function):
    启动时自动检查 ADB 和 scrcpy 依赖，若未找到则引导用户配置。
    负责初始化 QApplication、加载翻译器（QTranslator）、创建并显示主窗口。
    On startup, automatically checks for ADB and scrcpy; if missing, prompts user to configure.
    Initializes QApplication, loads the translator, creates and shows the main window.

多语言支持 (i18n Support):
    - 使用 QTranslator 加载 .qm 翻译文件
    - 翻译文件位于 resources/i18n/ 目录下，按语言命名（adb_gui_zh_CN.qm / adb_gui_en.qm）
    - 语言设置保存在 config/settings.json 的 "language" 字段
    - 若翻译文件加载失败，界面将回退到源代码中的英文原文
    - Uses QTranslator to load .qm translation files stored in resources/i18n/
    - Language is specified in config/settings.json → "language"
    - Falls back to source text if translation file is missing or invalid
"""

import sys
import os
import platform
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer, QTranslator, QLocale

from utils.config_manager import ConfigManager
from utils.system_utils import SystemUtils
from core.adb_client import AdbClient
from ui.main_window import MainWindow

# macOS 需要设置 QT_IM_MODULE 避免输入法兼容性问题
# macOS requires QT_IM_MODULE to avoid IME compatibility issues
if platform.system() == "Darwin":
    os.environ["QT_IM_MODULE"] = "simple"

# 翻译文件目录 (Translation file directory)
I18N_DIR = Path(__file__).resolve().parent / "resources" / "i18n"


def load_translator(app: QApplication) -> QTranslator:
    """
    根据配置加载对应语言的翻译器，若失败则返回空翻译器（界面显示英文原文）。
    Load translator based on settings; on failure, the UI shows original English text.

    参数 (Args):
        app: QApplication 实例

    返回 (Returns):
        QTranslator 实例，已安装到 app 或为一个空实例 (installed or empty instance)
    """
    translator = QTranslator()
    settings = ConfigManager.get_settings()
    lang = settings.get("language", "auto")

    # 如果设置为 "auto"，暂时不加载任何翻译文件（后续可扩展系统语言自动检测）
    # If "auto" is selected, skip loading for now; auto-detect may be added later
    if lang not in ("zh_CN", "en"):
        print("[INFO] 语言设置为自动，当前不加载翻译文件（使用英文原文）")
        return translator

    # 构建 .qm 文件路径 (Build .qm file path)
    qm_file = I18N_DIR / f"adb_gui_{lang}.qm"
    if qm_file.exists():
        if translator.load(str(qm_file)):
            app.installTranslator(translator)
            print(f"[INFO] 已加载翻译文件：{qm_file}")
        else:
            print(f"[WARN] 翻译文件加载失败：{qm_file}")
    else:
        print(f"[WARN] 翻译文件不存在：{qm_file}，将使用英文原文")
    print(f"[DEBUG] Translator installed: {app.installTranslator(translator)}")
    return translator


def check_dependencies():
    """
    检查 ADB 和 scrcpy 依赖是否可用 (Check ADB & scrcpy dependencies).
    返回 (Returns):
        (adb_ok, adb_path, scrcpy_ok, scrcpy_path)
        adb_ok: bool    ADB 是否可用
        adb_path: str   找到的 ADB 路径（或 None）
        scrcpy_ok: bool scrcpy 是否可用
        scrcpy_path: str 找到的 scrcpy 路径（或 None）
    """
    settings = ConfigManager.get_settings()
    manual_adb = settings.get("adb_path", "")
    manual_scrcpy = settings.get("scrcpy_path", "")

    # ---------- 查找 ADB ----------
    adb_path = SystemUtils.find_adb(manual_adb)
    adb_ok = False
    if adb_path:
        ok, _ = SystemUtils.check_adb_version(adb_path)
        adb_ok = ok

    # 若手动指定的 ADB 无效，清空配置中的路径；若自动找到的与配置不同，更新配置
    # Clear invalid manual path; update config if auto-detected path differs
    if not adb_ok and manual_adb:
        ConfigManager.set_setting("adb_path", "")
    elif adb_ok and manual_adb != adb_path:
        ConfigManager.set_setting("adb_path", adb_path)

    # ---------- 查找 scrcpy ----------
    scrcpy_path = SystemUtils.find_scrcpy(manual_scrcpy)
    scrcpy_ok = scrcpy_path is not None
    if not scrcpy_ok and manual_scrcpy:
        ConfigManager.set_setting("scrcpy_path", "")
    elif scrcpy_ok and manual_scrcpy != scrcpy_path:
        ConfigManager.set_setting("scrcpy_path", scrcpy_path)

    return adb_ok, adb_path, scrcpy_ok, scrcpy_path


def main():
    """程序主入口 (Main entry point)"""
    app = QApplication(sys.argv)
    app.setApplicationName("ADB GUI Tool")
    app.setOrganizationName("YourName")

    # 1. 加载翻译器 (Load translator)
    load_translator(app)

    # 2. 检查依赖 (Check dependencies)
    adb_ok, adb_path, scrcpy_ok, scrcpy_path = check_dependencies()

    # 3. 创建 ADB 客户端（未找到时为 None）
    adb_client = None
    if adb_ok:
        adb_client = AdbClient(adb_path)
        print(f"[INFO] 使用 ADB: {adb_path}")
    else:
        print("[WARN] 未找到可用的 ADB，请在设置中配置")

    # 4. 创建并显示主窗口 (Create and show main window)
    window = MainWindow(adb_client)
    window.show()

    # 5. 如果 ADB 不可用，延迟 500ms 自动弹出设置对话框，引导用户配置
    if not adb_ok:
        QTimer.singleShot(500, lambda: window.open_settings_dialog(force=True))

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        # 防止控制台闪退 (Prevent console from closing immediately)
        input("按回车键退出... (Press Enter to exit)")
        sys.exit(1)
