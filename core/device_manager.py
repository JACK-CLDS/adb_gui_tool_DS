"""
core/device_manager.py - 设备管理器

功能：
    - 定时刷新设备列表（通过 adb devices）
    - 维护设备状态缓存（serial, state, 设备名称等）
    - 发出信号通知 UI 更新
    - 管理每个设备打开的窗口实例（以便重启 ADB 时关闭它们）
    - 支持手动刷新、设置刷新间隔

依赖：PyQt5, core/adb_client, utils/config_manager
"""

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from typing import Dict, List, Optional, Any
from core.adb_client import AdbClient
from utils.config_manager import ConfigManager


class DeviceManager(QObject):
    """设备管理器，负责获取设备列表并管理设备窗口"""

    # 信号：设备列表更新时发出，参数为 [(serial, state, device_name), ...]
    devices_updated = pyqtSignal(list)

    # 信号：某个设备的状态发生变化（如从 device 变为 offline）
    device_state_changed = pyqtSignal(str, str, str)  # serial, old_state, new_state

    def __init__(self, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.adb_client = adb_client
        self.devices: Dict[str, Dict[str, Any]] = {}  # serial -> {"state": str, "name": str, "window": QWidget or None}
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        # 从配置读取刷新间隔（默认 3000 ms）
        interval = ConfigManager.get_setting("auto_refresh_interval", 3000)
        self.refresh_timer.start(interval)

    def set_refresh_interval(self, interval_ms: int):
        """设置自动刷新间隔（毫秒）"""
        self.refresh_timer.start(interval_ms)
        ConfigManager.set_setting("auto_refresh_interval", interval_ms)

    def refresh_devices(self):
        """手动或定时调用，获取最新设备列表"""
        def on_devices(devices_list):
            new_serials = set()
            updated_data = []
            for serial, state in devices_list:
                new_serials.add(serial)
                old_info = self.devices.get(serial, {})
                old_state = old_info.get("state", "")
                if old_state != state:
                    self.device_state_changed.emit(serial, old_state, state)
                # 保留已有的设备名称和窗口引用
                device_name = old_info.get("name", self._fetch_device_name(serial))
                self.devices[serial] = {
                    "state": state,
                    "name": device_name,
                    "window": old_info.get("window")  # 窗口引用保留
                }
                updated_data.append((serial, state, device_name))

            # 移除已断开连接的设备
            for serial in list(self.devices.keys()):
                if serial not in new_serials:
                    # 设备已断开，如果有打开的窗口，可以发出信号通知关闭（但窗口可能已自己关闭）
                    window = self.devices[serial].get("window")
                    if window:
                        # TODO: 可以尝试关闭窗口，或者发出信号让主窗口处理
                        pass
                    del self.devices[serial]

            self.devices_updated.emit(updated_data)

        self.adb_client.devices(callback=on_devices)

    def _fetch_device_name(self, serial: str) -> str:
        """获取设备名称（型号），用于显示。暂时返回 serial 的一部分，后期可通过 getprop 获取"""
        # TODO: 实现异步获取设备型号，避免阻塞。目前返回 serial 作为临时名称
        # 可以调用 adb -s serial shell getprop ro.product.model
        # 但为了简单，先返回 serial 的简写
        if serial.startswith("emulator-"):
            return f"Emulator {serial[-4:]}"
        elif ":" in serial:  # 网络设备
            return f"Network {serial}"
        else:
            return f"Device {serial[:8]}"

    def get_device_info(self, serial: str) -> Optional[Dict]:
        """返回设备信息字典，如果设备不存在则返回 None"""
        return self.devices.get(serial)

    def get_all_serials(self) -> List[str]:
        """返回所有在线设备的序列号列表"""
        return [s for s, info in self.devices.items() if info["state"] == "device"]

    def register_device_window(self, serial: str, window: QObject):
        """记录某个设备打开的窗口对象，以便 ADB 服务重启时关闭"""
        if serial in self.devices:
            self.devices[serial]["window"] = window
            # 窗口关闭时应该自动解除引用，可以通过窗口的 destroyed 信号处理
            window.destroyed.connect(lambda: self.unregister_device_window(serial, window))

    def unregister_device_window(self, serial: str, window: QObject):
        """设备窗口关闭时调用，清除引用"""
        if serial in self.devices and self.devices[serial].get("window") is window:
            self.devices[serial]["window"] = None

    def close_all_device_windows(self):
        """关闭所有已打开的设备窗口（用于重启 ADB 服务前）"""
        for serial, info in self.devices.items():
            window = info.get("window")
            if window:
                try:
                    window.close()
                except Exception:
                    pass
            info["window"] = None

    def stop_refresh(self):
        """停止定时刷新（程序退出时调用）"""
        self.refresh_timer.stop()

    def manual_refresh(self):
        """手动刷新一次（不影响定时器）"""
        self.refresh_devices()