#!/usr/bin/env python3
"""
tools/generate_ts.py - 生成 Qt 翻译源文件 (.ts) (Generate Qt Translation Source Files)

功能 (Function):
    扫描项目中所有 Python 源文件，提取所有 self.tr() 包裹的字符串，
    调用 pylupdate5 生成 .ts 翻译模板文件。
    生成的文件默认保存在 resources/i18n/ 目录下，支持中、英文模板。
    Scans all Python files in the project, extracts strings wrapped in self.tr(),
    invokes pylupdate5 to generate .ts template files.
    Generated files are saved in resources/i18n/ by default, supporting Chinese & English templates.

用法 (Usage):
    python tools/generate_ts.py            # 生成中文和英文的 .ts 模板
    python tools/generate_ts.py --lang zh_CN  # 仅生成指定语言的 .ts

依赖 (Dependencies):
    - pylupdate5 (PyQt5 开发工具包自带)
    - 项目源代码必须包含 self.tr() 调用
"""

import sys
import subprocess
from pathlib import Path

# 项目根目录 (Project root directory, assuming this script is in tools/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = PROJECT_ROOT / "resources" / "i18n"
I18N_DIR.mkdir(parents=True, exist_ok=True)

# 需要扫描的源代码目录 (Source directories to scan)
SOURCE_DIRS = [
    PROJECT_ROOT / "ui",
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "utils",
    PROJECT_ROOT / "main.py",
]

# 支持的语言列表 (Supported languages)
SUPPORTED_LANGUAGES = {
    "zh_CN": "adb_gui_zh_CN.ts",
    "en": "adb_gui_en.ts",
}


def generate_ts(lang: str) -> bool:
    """
    为指定语言生成 .ts 翻译模板。
    Generate a .ts template for the given language.

    参数 (Args):
        lang: 语言代码，如 'zh_CN' 或 'en'

    返回 (Returns):
        bool: 成功返回 True，否则 False
    """
    ts_filename = SUPPORTED_LANGUAGES.get(lang)
    if not ts_filename:
        print(f"[ERROR] 不支持的语言代码: {lang}")
        return False

    ts_path = I18N_DIR / ts_filename

    # pylupdate5 的命令行参数 (Command line arguments for pylupdate5)
    cmd = ["pylupdate5"]
    # 添加所有 .py 文件 (Add all .py files)
    for src_dir in SOURCE_DIRS:
        if src_dir.is_file():
            cmd.append(str(src_dir))
        elif src_dir.is_dir():
            for py_file in src_dir.rglob("*.py"):
                cmd.append(str(py_file))

    cmd.extend(["-ts", str(ts_path)])
    # 语言无关（pylupdate5 会处理），不指定源语言，或可指定 -tr-function 等，但默认即可

    print(f"[INFO] 正在生成 {lang} 的翻译模板: {ts_path}")
    print(f"[CMD] {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print(f"[OK] 成功生成: {ts_path}")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"[ERROR] pylupdate5 返回非零状态: {result.returncode}")
            if result.stderr:
                print(f"[STDERR] {result.stderr}")
            return False
    except FileNotFoundError:
        print(
            "[ERROR] 未找到 pylupdate5，请确保 PyQt5 开发工具已安装。\n"
            "可以通过 'pip install pyqt5-tools' 或在系统包管理器中安装。"
        )
        return False


def main():
    """主入口 (Main entry)"""
    # 解析命令行参数 (Parse command-line arguments)
    if len(sys.argv) > 1 and sys.argv[1].startswith("--lang="):
        lang = sys.argv[1].split("=")[1]
        if lang not in SUPPORTED_LANGUAGES:
            print(f"支持的语言: {', '.join(SUPPORTED_LANGUAGES.keys())}")
            sys.exit(1)
        success = generate_ts(lang)
    else:
        # 生成所有支持的语言 (Generate all supported languages)
        success = True
        for lang in SUPPORTED_LANGUAGES:
            if not generate_ts(lang):
                success = False

    if not success:
        sys.exit(1)

    print("\n[INFO] 完成后，请编辑 .ts 文件添加翻译，然后使用 lrelease 编译为 .qm：")
    for lang, ts_name in SUPPORTED_LANGUAGES.items():
        ts_path = I18N_DIR / ts_name
        qm_path = ts_path.with_suffix(".qm")
        print(f"  lrelease {ts_path} -qm {qm_path}")


if __name__ == "__main__":
    main()