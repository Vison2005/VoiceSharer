import sounddevice as sd
import numpy as np
import threading

class CircularBuffer:
    def __init__(self, capacity_frames, channels):
        self.capacity = capacity_frames
        self.channels = channels
        self.buffer = np.zeros((capacity_frames, channels), dtype='float32')
        self.write_idx = 0
        self.read_idx = 0
        self.available_frames = 0
        self.lock = threading.Lock()

    def write(self, data):
        frames = len(data)
        with self.lock:
            # 写入数据，溢出则覆盖旧数据
            
            end_idx = (self.write_idx + frames) % self.capacity
            if end_idx > self.write_idx:
                self.buffer[self.write_idx:end_idx] = data
            else:
                p1 = self.capacity - self.write_idx
                self.buffer[self.write_idx:] = data[:p1]
                self.buffer[:end_idx] = data[p1:]
            
            self.write_idx = end_idx
            self.available_frames = min(self.capacity, self.available_frames + frames)

    def read(self, frames):
        output = np.zeros((frames, self.channels), dtype='float32')
        with self.lock:
            if self.available_frames < frames:
                # 欠载：数据不足，返回静音
                return output, False 
            
            end_idx = (self.read_idx + frames) % self.capacity
            if end_idx > self.read_idx:
                output[:] = self.buffer[self.read_idx:end_idx]
            else:
                p1 = self.capacity - self.read_idx
                output[:p1] = self.buffer[self.read_idx:]
                output[p1:] = self.buffer[:end_idx]
            
            self.read_idx = end_idx
            self.available_frames -= frames
            return output, True
            
    def skip(self, frames):
        with self.lock:
            self.read_idx = (self.read_idx + frames) % self.capacity
            self.available_frames = max(0, self.available_frames - frames)

    def level(self):
        return self.available_frames

class AudioEngine:
    def __init__(self):
        self.input_stream = None
        self.output_streams = {}  # {device_id: stream}
        self.buffers = {}         # {device_id: CircularBuffer}
        self.delays = {}          # {device_id: delay_ms}
        self.volumes = {}         # {device_id: volume_0_to_1}
        self.running = False
        
        self.samplerate = 48000
        self.channels = 2
        self.blocksize = 1024
        self.dtype = 'float32'
        
        # 输出采样率 {id: rate}
        self.output_rates = {}

    def set_delay(self, device_id, delay_ms):
        self.delays[device_id] = delay_ms

    def set_volume(self, device_id, volume_percent):
        self.volumes[device_id] = volume_percent / 100.0

    def start_streams(self, input_device_id, output_device_ids):
        self.stop_streams()
        self.running = True
        self.output_device_ids = output_device_ids
        
        # 1. 确定主采样率
        try:
            in_dev_info = sd.query_devices(input_device_id)
            # 优先用输入设备采样率
            self.samplerate = int(in_dev_info['default_samplerate'])
            print(f"主采样率已设置为 {self.samplerate} Hz (来自输入设备)")
        except Exception as e:
            print(f"无法查询输入设备信息，默认为 48000。错误: {e}")
            self.samplerate = 48000

        # 更新缓冲容量
        self.buffer_capacity = self.samplerate * 2 

        # 2. 初始化缓冲
        for dev_id in output_device_ids:
            self.buffers[dev_id] = CircularBuffer(self.buffer_capacity, self.channels)
            self.volumes[dev_id] = self.volumes.get(dev_id, 1.0)
            self.output_rates[dev_id] = self.samplerate # 默认为主采样率

        # 3. 启动输入流
        try:
            # 检查通道
            in_dev_info = sd.query_devices(input_device_id)
            input_channels = min(self.channels, in_dev_info['max_input_channels'])
            
            # 修正 0 通道情况
            if input_channels <= 0: input_channels = 2

            self.input_stream = sd.InputStream(
                device=input_device_id,
                channels=input_channels,
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype=self.dtype,
                callback=self.make_input_callback(input_channels)
            )
            self.input_stream.start()
        except Exception as e:
            print(f"启动输入流错误: {e}")
            self.running = False
            return False

        # 4. 启动输出流
        for dev_id in output_device_ids:
            try:
                # 尝试以主采样率打开
                current_rate = self.samplerate
                try:
                    stream = sd.OutputStream(
                        device=dev_id,
                        channels=self.channels,
                        samplerate=current_rate,
                        blocksize=self.blocksize,
                        dtype=self.dtype,
                        callback=self.make_output_callback(dev_id)
                    )
                    stream.start()
                    self.output_streams[dev_id] = stream
                except Exception as e:
                    # 检查无效采样率错误
                    if "Invalid sample rate" in str(e) or "-9997" in str(e):
                        print(f"设备 {dev_id} 拒绝了 {current_rate}Hz。尝试默认采样率...")
                        
                        # 获取原生采样率
                        dev_info = sd.query_devices(dev_id)
                        native_rate = int(dev_info['default_samplerate'])
                        
                        if native_rate != current_rate:
                            print(f"设备 {dev_id} 原生采样率: {native_rate}Hz。正在重试...")
                            self.output_rates[dev_id] = native_rate
                            
                            stream = sd.OutputStream(
                                device=dev_id,
                                channels=self.channels,
                                samplerate=native_rate,
                                blocksize=self.blocksize,
                                dtype=self.dtype,
                                callback=self.make_output_callback(dev_id)
                            )
                            stream.start()
                            self.output_streams[dev_id] = stream
                        else:
                            raise e # 其它错误
                    else:
                        raise e # 重新引发
            except Exception as e:
                print(f"启动设备 {dev_id} 的输出流错误: {e}")
        
        return True

    def stop_streams(self):
        self.running = False
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None
        
        for stream in self.output_streams.values():
            stream.stop()
            stream.close()
        self.output_streams.clear()
        self.buffers.clear()

    def make_input_callback(self, input_channels):
        def callback(indata, frames, time, status):
            if status:
                pass # print(f"Input Status: {status}")
            
            # 单声道转立体声
            if input_channels == 1 and self.channels == 2:
                # 扩展通道
                data = np.repeat(indata, 2, axis=1)
            else:
                data = indata.copy()
            
            for dev_id in self.output_device_ids:
                if dev_id in self.buffers:
                    self.buffers[dev_id].write(data)
        return callback

    def make_output_callback(self, dev_id):
        def callback(outdata, frames, time, status):
            if status:
                pass # print(f"Output Status ({dev_id}): {status}")
            
            buf = self.buffers.get(dev_id)
            if not buf:
                outdata.fill(0)
                return

            # 检查重采样
            target_rate = self.output_rates.get(dev_id, self.samplerate)
            
            # 计算需读取帧数
            
            if target_rate == self.samplerate:
                frames_to_read = frames
            else:
                frames_to_read = int(frames * (self.samplerate / target_rate))
                if frames_to_read == 0: frames_to_read = 1 # 避免零读取
            
            delay_ms = self.delays.get(dev_id, 0)
            target_delay_frames_input = int((delay_ms / 1000.0) * self.samplerate)
            
            current_level = buf.level()
            
            # 使用输入帧单位
            
            if current_level < target_delay_frames_input + frames_to_read:
                # 数据不足
                outdata.fill(0)
                return

            # 蓝牙优化：阈值增至 150ms
            threshold_frames = int(0.15 * self.samplerate)
            
            if current_level > target_delay_frames_input + frames_to_read + threshold_frames:
                drop_amount = current_level - (target_delay_frames_input + frames_to_read)
                
                # 丢弃积压数据以同步
                buf.skip(drop_amount)
            
            # 读取数据
            data, success = buf.read(frames_to_read)
            
            if success:
                vol = self.volumes.get(dev_id, 1.0)
                
                # 重采样
                if target_rate != self.samplerate:
                    # 线性插值
                    
                    x_old = np.linspace(0, frames_to_read - 1, frames_to_read)
                    x_new = np.linspace(0, frames_to_read - 1, frames)
                    
                    # 处理通道
                    # 创建临时缓冲
                    resampled_data = np.zeros((frames, self.channels), dtype=self.dtype)
                    
                    for ch in range(self.channels):
                        resampled_data[:, ch] = np.interp(x_new, x_old, data[:, ch])
                    
                    outdata[:] = resampled_data * vol
                else:
                    outdata[:] = data * vol
            else:
                outdata.fill(0)
        
        return callback
