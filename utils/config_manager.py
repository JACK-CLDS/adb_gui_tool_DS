"""
utils/config_manager.py - 配置管理器 (Configuration Manager)

负责所有配置文件的读写，使用 JSON 格式存储 (Read/Write all config files in JSON format)。
所有方法都是静态方法，可以直接通过类名调用 (All methods are static).

配置目录结构 (Config directory structure):
    ./config/
        settings.json              # 全局设置 (Global settings)
        device_aliases.json        # 设备别名 (Device aliases)
        device_order.json          # 设备列表排序 (Device list order)
        history.json               # 历史连接记录 (Connection history)
        favorites.json             # 收藏设备 (Favorite devices, grouped)
        no_prompt.json             # “不再提示”记录 (Do-not-prompt flags)
    ./preferences/
        <serial>.json              # 每个设备的偏好设置 (Per-device preferences)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# 项目根目录 (Project root directory, assuming this file is in ./utils/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
PREFERENCES_DIR = PROJECT_ROOT / "preferences"

# 确保目录存在 (Ensure directories exist)
CONFIG_DIR.mkdir(exist_ok=True)
PREFERENCES_DIR.mkdir(exist_ok=True)

# 默认配置文件路径 (Default config file paths)
SETTINGS_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
FAVORITES_FILE = CONFIG_DIR / "favorites.json"
NO_PROMPT_FILE = CONFIG_DIR / "no_prompt.json"


class ConfigManager:
    """全局配置管理类 (Global configuration manager)"""

    # ========== 底层读写 (Low-level read/write) ==========

    @staticmethod
    def _read_json_file(file_path: Path, default: Any = None) -> Any:
        """
        安全读取 JSON 文件，如果文件不存在或解析失败则返回默认值。
        Safely read a JSON file; return default value if missing or corrupted.
        """
        if not file_path.exists():
            return default if default is not None else {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # TODO: 记录日志，提示用户配置文件损坏，将重置为默认
            return default if default is not None else {}

    @staticmethod
    def _write_json_file(file_path: Path, data: Any) -> bool:
        """
        写入 JSON 文件，返回是否成功 (Write JSON file, return success status).
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except IOError:
            # TODO: 记录日志 (Log error)
            return False

    # ========== 全局设置 (Global settings) ==========

    @staticmethod
    def get_settings() -> Dict[str, Any]:
        """
        获取全局设置，若文件不存在则自动创建默认配置。
        Get global settings; auto-create with defaults if file missing.
        """
        default = {
            "language": "auto",                     # 界面语言，auto/en/zh_CN
            "adb_path": "",                         # 用户指定的 adb 路径
            "scrcpy_path": "",                      # scrcpy 可执行文件路径
            "auto_refresh_interval": 3000,          # 设备列表自动刷新间隔（毫秒）
            "check_update_on_startup": True,
            "window_geometry": {},                  # 主窗口位置和大小
            "theme": "default",                     # 预留主题切换
            "shortcuts": {}                         # 自定义快捷键映射，预留
        }
        saved = ConfigManager._read_json_file(SETTINGS_FILE, default)
        # 合并默认值，防止新增字段缺失 (Merge defaults for missing keys)
        for key, val in default.items():
            if key not in saved:
                saved[key] = val
        return saved

    @staticmethod
    def save_settings(settings: Dict[str, Any]) -> bool:
        """保存全局设置 (Save global settings)"""
        return ConfigManager._write_json_file(SETTINGS_FILE, settings)

    @staticmethod
    def get_setting(key: str, default=None):
        """获取单个设置项 (Get a single setting value)"""
        return ConfigManager.get_settings().get(key, default)

    @staticmethod
    def set_setting(key: str, value: Any) -> bool:
        """设置单个设置项并保存 (Set a single setting and save)"""
        settings = ConfigManager.get_settings()
        settings[key] = value
        return ConfigManager.save_settings(settings)

    # ========== 设备别名 (Device aliases) ==========

    @staticmethod
    def get_device_aliases() -> Dict[str, str]:
        """
        获取所有设备别名，格式 {serial: alias, ...}
        Get all device aliases.
        """
        aliases_file = CONFIG_DIR / "device_aliases.json"
        return ConfigManager._read_json_file(aliases_file, {})

    @staticmethod
    def set_device_alias(serial: str, alias: str) -> bool:
        """
        设置或清除设备别名 (Set or clear a device alias).
        若 alias 为空字符串则删除别名。
        """
        aliases = ConfigManager.get_device_aliases()
        if alias:
            aliases[serial] = alias
        else:
            aliases.pop(serial, None)
        return ConfigManager._write_json_file(CONFIG_DIR / "device_aliases.json", aliases)

    # ========== 设备排序 (Device order) ==========

    @staticmethod
    def get_device_order() -> List[str]:
        """获取设备列表排序 (Get device list order)"""
        return ConfigManager._read_json_file(CONFIG_DIR / "device_order.json", [])

    @staticmethod
    def set_device_order(order: List[str]) -> bool:
        """保存设备列表排序 (Save device list order)"""
        return ConfigManager._write_json_file(CONFIG_DIR / "device_order.json", order)

    # ========== 历史连接记录 (Connection history) ==========

    @staticmethod
    def get_history() -> List[str]:
        """获取历史连接地址列表 (Get connection history, max 30 entries)"""
        data = ConfigManager._read_json_file(HISTORY_FILE, [])
        return data if isinstance(data, list) else []

    @staticmethod
    def add_history(address: str) -> bool:
        """
        添加一条历史记录，去重并置于首位，最多保留 30 条。
        Add a history entry, deduplicate, move to front, keep max 30.
        """
        if not address:
            return False
        history = ConfigManager.get_history()
        if address in history:
            history.remove(address)
        history.insert(0, address)
        # 限制最多 30 条 (Keep max 30)
        history = history[:30]
        return ConfigManager._write_json_file(HISTORY_FILE, history)

    @staticmethod
    def clear_history() -> bool:
        """清空历史记录 (Clear all history)"""
        return ConfigManager._write_json_file(HISTORY_FILE, [])

    @staticmethod
    def remove_history(address: str) -> bool:
        """删除指定历史记录 (Remove a history entry)"""
        history = ConfigManager.get_history()
        if address in history:
            history.remove(address)
            return ConfigManager._write_json_file(HISTORY_FILE, history)
        return False

    # ========== 收藏设备 (Favorites) ==========

    @staticmethod
    def get_favorites() -> Dict[str, List[str]]:
        """
        获取收藏设备分组，格式 {"分组名": ["地址1", "地址2"], ...}。
        默认包含“默认”分组。
        """
        default = {"默认": []}
        data = ConfigManager._read_json_file(FAVORITES_FILE, default)
        if not data or not isinstance(data, dict):
            data = default
        if "默认" not in data:
            data["默认"] = []
        return data

    @staticmethod
    def save_favorites(favorites: Dict[str, List[str]]) -> bool:
        """保存收藏设备 (Save favorites)"""
        return ConfigManager._write_json_file(FAVORITES_FILE, favorites)

    @staticmethod
    def add_favorite(group: str, address: str) -> bool:
        """
        将设备添加到指定分组，若分组不存在则自动创建。
        Add device to a group; create group if necessary.
        """
        fav = ConfigManager.get_favorites()
        if group not in fav:
            fav[group] = []
        if address not in fav[group]:
            fav[group].append(address)
        return ConfigManager.save_favorites(fav)

    @staticmethod
    def remove_favorite(group: str, address: str) -> bool:
        """从分组中移除设备 (Remove device from a group)"""
        fav = ConfigManager.get_favorites()
        if group in fav and address in fav[group]:
            fav[group].remove(address)
            return ConfigManager.save_favorites(fav)
        return False

    # ========== “不再提示”记录 (Do-not-prompt flags) ==========

    @staticmethod
    def get_no_prompt_flags() -> Dict[str, bool]:
        """
        获取所有“不再提示”标志，格式 {"confirm_restart_adb": True, ...}
        Get all do-not-prompt flags.
        """
        return ConfigManager._read_json_file(NO_PROMPT_FILE, {})

    @staticmethod
    def set_no_prompt(key: str, value: bool = True) -> bool:
        """设置某个确认对话框的“不再提示”状态"""
        flags = ConfigManager.get_no_prompt_flags()
        flags[key] = value
        return ConfigManager._write_json_file(NO_PROMPT_FILE, flags)

    @staticmethod
    def should_prompt(key: str, default_prompt: bool = True) -> bool:
        """
        检查是否应该弹出提示 (Check if prompt should be shown).
        如果标志为 True 表示“不再提示”，则返回 False。
        """
        flags = ConfigManager.get_no_prompt_flags()
        if flags.get(key, False):
            return False
        return default_prompt

    # ========== 设备偏好 (Per-device preferences) ==========

    @staticmethod
    def get_device_preferences(serial: str) -> Dict[str, Any]:
        """
        获取指定设备的偏好设置，如不存在则返回默认配置。
        Get per-device preferences; return defaults if file missing.
        """
        pref_file = PREFERENCES_DIR / f"{serial}.json"
        default = {
            "log_level_filter": "V",                # Verbose
            "log_highlight_patterns": {
                "WARNING": "#FFA500",               # Orange
                "ERROR": "#FF0000"                  # Red
            },
            "file_manager_show_hidden": False,
            "file_manager_favorites": []            # 文件管理器路径收藏
        }
        saved = ConfigManager._read_json_file(pref_file, default)
        # 合并默认值 (Merge defaults)
        for key, val in default.items():
            if key not in saved:
                saved[key] = val
        return saved

    @staticmethod
    def save_device_preferences(serial: str, prefs: Dict[str, Any]) -> bool:
        """保存设备偏好 (Save device preferences)"""
        pref_file = PREFERENCES_DIR / f"{serial}.json"
        return ConfigManager._write_json_file(pref_file, prefs)

    @staticmethod
    def set_device_preference(serial: str, key: str, value: Any) -> bool:
        """设置单个设备偏好项并保存 (Set a single preference and save)"""
        prefs = ConfigManager.get_device_preferences(serial)
        prefs[key] = value
        return ConfigManager.save_device_preferences(serial, prefs)
