import sounddevice as sd

class DeviceManager:
    def __init__(self):
        self.input_devices = []
        self.output_devices = []

    def refresh_devices(self):
        """扫描可用音频设备。"""
        # 重启 PortAudio 检测热插拔
        try:
            sd._terminate()
            sd._initialize()
        except Exception as e:
            print(f"警告：重新初始化 PortAudio 失败: {e}")

        self.input_devices = []
        self.output_devices = []
        
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        
        # 检查 WASAPI
        wasapi_index = -1
        for i, api in enumerate(hostapis):
            if 'WASAPI' in api['name']:
                wasapi_index = i
                break
        
        for i, dev in enumerate(devices):
            # dev 结构信息
            
            host_api_info = sd.query_hostapis(dev['hostapi'])
            api_name = host_api_info['name']
            
            # Windows 下仅显示 WASAPI 设备
            if wasapi_index >= 0 and dev['hostapi'] != wasapi_index:
                continue

            # 保留 Loopback
            
            # 构建设备名
            # 隐藏 Windows WASAPI 后缀
            final_name = dev['name']
            if api_name and api_name != "Windows WASAPI":
                final_name = f"{final_name} ({api_name})"
            
            device_info = {
                'id': i,
                'name': final_name,
                'api': api_name,
                'channels_in': dev['max_input_channels'],
                'channels_out': dev['max_output_channels'],
                'samplerate': dev['default_samplerate']
            }

            if dev['max_input_channels'] > 0:
                self.input_devices.append(device_info)
            
            if dev['max_output_channels'] > 0:
                # 过滤 VB-Cable 防反馈
                if "VB-Audio" not in device_info['name'] and "CABLE" not in device_info['name']:
                    self.output_devices.append(device_info)

    def get_input_devices(self):
        return self.input_devices

    def get_output_devices(self):
        return self.output_devices

    def get_device_by_id(self, device_id):
        try:
            return sd.query_devices(device_id)
        except:
            return None
