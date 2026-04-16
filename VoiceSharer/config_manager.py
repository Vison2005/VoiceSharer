import json
import os
import sys

def resource_path(relative_path):
    """获取资源路径"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class ConfigManager:
    """配置管理器"""
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.config = {
            "input_device": None,
            "output_devices": [],
            "device_settings": {},
            "autostart": False,
            "minimize_to_tray": True
        }

    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.config.update(data)
            except Exception as e:
                print(f"加载配置错误: {e}")
        return self.config

    def save(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"保存配置错误: {e}")

    def get(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)

    def set(self, key, value):
        """设置配置项"""
        self.config[key] = value
