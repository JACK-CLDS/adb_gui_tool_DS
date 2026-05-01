"""
core/device_manager.py - 设备管理器 (Device Manager)

功能：
    - 定时刷新设备列表 (auto-refresh device list via adb devices)
    - 维护设备状态缓存 (maintain device state cache: serial, state, name, window)
    - 发出信号通知 UI 更新 (emit signals for UI updates)
    - 管理每个设备打开的窗口实例，便于重启 ADB 时关闭 (track open device windows)
    - 支持手动刷新、动态设置刷新间隔 (manual refresh & dynamic interval)

依赖：PyQt5, core/adb_client, utils/config_manager
"""

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from typing import Dict, List, Optional, Any
from core.adb_client import AdbClient
from utils.config_manager import ConfigManager


class DeviceManager(QObject):
    """
    设备管理器 (Device Manager)
    负责获取设备列表并管理设备窗口。
    """

    # 设备列表更新信号：携带 [(serial, state, device_name), ...]
    devices_updated = pyqtSignal(list)
    # 设备状态变化信号：serial, old_state, new_state
    device_state_changed = pyqtSignal(str, str, str)

    def __init__(self, adb_client: AdbClient, parent=None):
        super().__init__(parent)
        self.adb_client = adb_client
        # 设备缓存：serial -> {"state": str, "name": str, "window": Optional[QWidget]}
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)

        # 从配置读取自动刷新间隔，默认 3000 ms
        interval = ConfigManager.get_setting("auto_refresh_interval", 3000)
        self.refresh_timer.start(interval)

    # ---------- 刷新控制 (Refresh control) ----------

    def set_refresh_interval(self, interval_ms: int):
        """
        设置自动刷新间隔并持久化 (Set auto-refresh interval & save)
        :param interval_ms: 毫秒 (milliseconds)
        """
        self.refresh_timer.start(interval_ms)
        ConfigManager.set_setting("auto_refresh_interval", interval_ms)

    def manual_refresh(self):
        """手动刷新一次，不影响定时器 (Trigger a single refresh without affecting the timer)"""
        self.refresh_devices()

    def stop_refresh(self):
        """停止定时刷新，用于程序退出 (Stop auto-refresh on app exit)"""
        self.refresh_timer.stop()

    # ---------- 设备列表逻辑 (Device list logic) ----------

    def refresh_devices(self):
        """从 ADB 获取设备列表并更新本地缓存 (Fetch devices via ADB and update cache)"""
        def on_devices(devices_list):
            new_serials = set()
            updated_data = []

            for serial, state in devices_list:
                new_serials.add(serial)
                old_info = self.devices.get(serial, {})
                old_state = old_info.get("state", "")
                if old_state != state:
                    self.device_state_changed.emit(serial, old_state, state)

                # 保留已有的设备名称和窗口引用，避免反复获取型号
                device_name = old_info.get("name") or self._fetch_device_name(serial)
                self.devices[serial] = {
                    "state": state,
                    "name": device_name,
                    "window": old_info.get("window")
                }
                updated_data.append((serial, state, device_name))

            # 移除已不在线的设备
            for serial in list(self.devices.keys()):
                if serial not in new_serials:
                    # TODO: 可在此处发出设备断开的通知，或自动关闭窗口
                    del self.devices[serial]

            self.devices_updated.emit(updated_data)

        self.adb_client.devices(callback=on_devices)

    def _fetch_device_name(self, serial: str) -> str:
        """
        为未知设备生成一个临时显示名称 (Generate a temporary display name)
        后续可通过异步 getprop ro.product.model 获取真实型号。
        """
        if serial.startswith("emulator-"):
            return f"Emulator {serial[-4:]}"
        elif ":" in serial:      # 网络设备 (Network device)
            return f"Network {serial}"
        else:
            return f"Device {serial[:8]}"

    # ---------- 设备信息查询 (Device info query) ----------

    def get_device_info(self, serial: str) -> Optional[Dict]:
        """获取设备信息字典 (Get device info dict for a serial)"""
        return self.devices.get(serial)

    def get_all_serials(self) -> List[str]:
        """获取所有状态为 'device' 的序列号列表 (Get serials of all online devices)"""
        return [s for s, info in self.devices.items() if info["state"] == "device"]

    # ---------- 设备窗口管理 (Device window management) ----------

    def register_device_window(self, serial: str, window: QObject):
        """
        登记设备打开的窗口对象 (Register an open device window)
        窗口关闭时自动清除引用。
        """
        if serial in self.devices:
            self.devices[serial]["window"] = window
            window.destroyed.connect(lambda: self.unregister_device_window(serial, window))

    def unregister_device_window(self, serial: str, window: QObject):
        """从缓存中移除窗口引用 (Remove window reference)"""
        if serial in self.devices and self.devices[serial].get("window") is window:
            self.devices[serial]["window"] = None

    def close_all_device_windows(self):
        """关闭所有已打开的设备窗口，用于重启 ADB 前 (Close all device windows before ADB restart)"""
        for serial, info in self.devices.items():
            window = info.get("window")
            if window:
                try:
                    window.close()
                except Exception:
                    pass
                info["window"] = None
