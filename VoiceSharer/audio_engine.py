import sounddevice as sd
import numpy as np
import threading
import time


class CircularBuffer:
    """音频循环缓冲区"""
    def __init__(self, capacity_frames, channels):
        self.capacity = capacity_frames
        self.channels = channels
        self.buffer = np.zeros((capacity_frames, channels), dtype='float32')
        self.write_idx = 0
        self.read_idx = 0
        self.available_frames = 0
        self.lock = threading.Lock()

    def write(self, data):
        """写入音频数据"""
        frames = len(data)
        with self.lock:
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
        """读取音频数据"""
        output = np.zeros((frames, self.channels), dtype='float32')
        with self.lock:
            if self.available_frames < frames:
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
        """跳过指定帧数"""
        with self.lock:
            self.read_idx = (self.read_idx + frames) % self.capacity
            self.available_frames = max(0, self.available_frames - frames)

    def level(self):
        """获取缓冲区可用帧数"""
        return self.available_frames


class AudioEngine:
    """音频处理核心引擎"""
    def __init__(self):
        self.input_stream = None
        self.output_streams = {}
        self.buffers = {}
        self.delays = {}
        self.volumes = {}
        self.running = False

        self.samplerate = 48000
        self.channels = 2
        self.blocksize = 1024
        self.dtype = 'float32'

        self.output_rates = {}

    def set_delay(self, device_id, delay_ms):
        """设置设备延迟"""
        self.delays[device_id] = delay_ms

    def set_volume(self, device_id, volume_percent):
        """设置设备音量"""
        self.volumes[device_id] = volume_percent / 100.0

    def start_streams(self, input_device_id, output_device_ids):
        """启动音频流"""
        self.stop_streams()
        self.running = True
        self.output_device_ids = output_device_ids

        try:
            in_dev_info = sd.query_devices(input_device_id)
            self.samplerate = int(in_dev_info['default_samplerate'])
            print(f"主采样率已设置为 {self.samplerate} Hz (来自输入设备)")
        except Exception as e:
            print(f"无法查询输入设备信息，默认为 48000。错误: {e}")
            self.samplerate = 48000

        self.buffer_capacity = self.samplerate * 2

        for dev_id in output_device_ids:
            self.buffers[dev_id] = CircularBuffer(self.buffer_capacity, self.channels)
            self.volumes[dev_id] = self.volumes.get(dev_id, 1.0)
            self.output_rates[dev_id] = self.samplerate

        try:
            in_dev_info = sd.query_devices(input_device_id)
            input_channels = min(self.channels, in_dev_info['max_input_channels'])
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

        for dev_id in output_device_ids:
            try:
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
                    if "Invalid sample rate" in str(e) or "-9997" in str(e):
                        dev_info = sd.query_devices(dev_id)
                        native_rate = int(dev_info['default_samplerate'])

                        if native_rate != current_rate:
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
                            raise e
                    else:
                        raise e
            except Exception as e:
                print(f"启动设备 {dev_id} 的输出流错误: {e}")

        return True

    def stop_streams(self):
        """停止所有音频流"""
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
        """创建输入流回调函数"""
        def callback(indata, frames, time, status):
            if input_channels == 1 and self.channels == 2:
                data = np.repeat(indata, 2, axis=1)
            else:
                data = indata.copy()

            for dev_id in self.output_device_ids:
                if dev_id in self.buffers:
                    self.buffers[dev_id].write(data)

        return callback

    def make_output_callback(self, dev_id):
        """创建输出流回调函数"""
        def callback(outdata, frames, time, status):
            buf = self.buffers.get(dev_id)
            if not buf:
                outdata.fill(0)
                return

            target_rate = self.output_rates.get(dev_id, self.samplerate)

            if target_rate == self.samplerate:
                frames_to_read = frames
            else:
                frames_to_read = int(frames * (self.samplerate / target_rate))
            if frames_to_read == 0: frames_to_read = 1

            delay_ms = self.delays.get(dev_id, 0)
            target_delay_frames_input = int((delay_ms / 1000.0) * self.samplerate)

            current_level = buf.level()

            if current_level < target_delay_frames_input + frames_to_read:
                outdata.fill(0)
                return

            threshold_frames = int(0.15 * self.samplerate)

            if current_level > target_delay_frames_input + frames_to_read + threshold_frames:
                drop_amount = current_level - (target_delay_frames_input + frames_to_read)
                buf.skip(drop_amount)

            data, success = buf.read(frames_to_read)

            if success:
                vol = self.volumes.get(dev_id, 1.0)
                if target_rate != self.samplerate:
                    x_old = np.linspace(0, frames_to_read - 1, frames_to_read)
                    x_new = np.linspace(0, frames_to_read - 1, frames)
                    resampled_data = np.zeros((frames, self.channels), dtype=self.dtype)
                    for ch in range(self.channels):
                        resampled_data[:, ch] = np.interp(x_new, x_old, data[:, ch])
                    outdata[:] = resampled_data * vol
                else:
                    outdata[:] = data * vol
            else:
                outdata.fill(0)

        return callback

    def calibrate_delays(self, mic_device_id, output_device_ids, progress_callback=None):
        """自动校准各输出设备延迟"""
        test_duration = 0.4
        silence_duration = 0.6
        f_start = 500
        f_end = 5000

        device_delays = {}
        from collections import deque
        queue = deque()
        
        mic_info = sd.query_devices(mic_device_id)
        mic_rate = int(mic_info['default_samplerate'])
        mic_channels = min(2, mic_info['max_input_channels']) if mic_info['max_input_channels'] > 0 else 1

        for dev_id in output_device_ids:
            dev_info = sd.query_devices(dev_id)
            dev_default_rate = int(dev_info['default_samplerate'])
            rates = []
            for r in [48000, 44100, dev_default_rate]:
                if r not in rates:
                    rates.append(r)
            queue.append((dev_id, rates))

        total_tasks = len(output_device_ids)
        completed_tasks = 0

        recorded_data = []
        def mic_callback(indata, frames, time, status):
            if indata.ndim > 1:
                recorded_data.append(indata[:, 0].copy())
            else:
                recorded_data.append(indata.copy())

        mic_stream = None
        try:
            mic_stream = sd.InputStream(
                device=mic_device_id,
                samplerate=mic_rate,
                channels=mic_channels,
                dtype='float32',
                callback=mic_callback
            )
            mic_stream.start()

            t_mic = np.linspace(0, test_duration, int(mic_rate * test_duration), endpoint=False)
            tone_ref = (0.3 * np.sin(2 * np.pi * f_start * (test_duration / np.log(f_end/f_start)) * (np.exp(t_mic * np.log(f_end/f_start) / test_duration) - 1))).astype(np.float32)

            while queue:
                dev_id, rates = queue.popleft()
                if not rates:
                    device_delays[dev_id] = 0.0
                    completed_tasks += 1
                    continue

                current_out_rate = rates.pop(0)
                if progress_callback:
                    progress_callback(completed_tasks, total_tasks, f"正在测试设备 {dev_id} ({current_out_rate}Hz)")

                out_stream = None
                try:
                    out_stream = sd.OutputStream(
                        device=dev_id,
                        channels=2,
                        samplerate=current_out_rate,
                        dtype='float32'
                    )
                    out_stream.start()

                    t_out = np.linspace(0, test_duration, int(current_out_rate * test_duration), endpoint=False)
                    tone_out = (0.3 * np.sin(2 * np.pi * f_start * (test_duration / np.log(f_end/f_start)) * (np.exp(t_out * np.log(f_end/f_start) / test_duration) - 1))).astype(np.float32)
                    tone_stereo = np.repeat(tone_out[:, np.newaxis], 2, axis=1)

                    time.sleep(0.6)
                    recorded_data.clear()
                    
                    out_stream.write(tone_stereo)
                    time.sleep(test_duration + 1.0)

                    out_stream.stop()
                    out_stream.close()

                    if not recorded_data:
                        raise Exception("未采集到数据")

                    recorded = np.concatenate(recorded_data, axis=0).flatten()
                    recorded = recorded - np.mean(recorded)
                    correlation = np.correlate(recorded, tone_ref, mode='full')
                    peak_idx = np.argmax(np.abs(correlation))
                    delay_frames = peak_idx - (len(tone_ref) - 1)
                    
                    safety_offset_ms = 0
                    if current_out_rate != mic_rate:
                        safety_offset_ms = 5 

                    latency_ms = (delay_frames / mic_rate) * 1000 + safety_offset_ms
                    print(f"设备 {dev_id} 检测延迟: {latency_ms:.2f} ms")
                    
                    device_delays[dev_id] = latency_ms
                    completed_tasks += 1
                    time.sleep(silence_duration)

                except Exception as e:
                    if out_stream: 
                        try:
                            out_stream.stop()
                            out_stream.close()
                        except:
                            pass
                    queue.append((dev_id, rates))
                    time.sleep(1.0)

        except Exception as e:
            print(f"校准全局错误: {e}")
        finally:
            if mic_stream:
                mic_stream.stop()
                mic_stream.close()

        return device_delays