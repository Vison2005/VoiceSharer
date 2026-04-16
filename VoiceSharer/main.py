import sys
import os
import sounddevice as sd
from PyQt5.QtWidgets import QApplication, QMessageBox, QMenu, QInputDialog, QSystemTrayIcon
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from ui import MainWindow
from device_manager import DeviceManager
from audio_engine import AudioEngine
from config_manager import ConfigManager, resource_path


class CalibrationThread(QThread):
    """音频延迟校准线程"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, engine, mic_id, output_ids):
        super().__init__()
        self.engine = engine
        self.mic_id = mic_id
        self.output_ids = output_ids

    def run(self):
        """执行校准"""
        try:
            def progress_cb(current, total, msg):
                self.progress.emit(current, total, msg)

            delays = self.engine.calibrate_delays(
                self.mic_id,
                self.output_ids,
                progress_callback=progress_cb
            )
            self.finished.emit(delays)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class ApplicationController:
    """应用程序逻辑控制"""
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        self.dm = DeviceManager()
        self.engine = AudioEngine()
        self.config_mgr = ConfigManager()

        self.selected_output_ids = set()
        self.silent_start = ("--silent" in sys.argv or "--tray" in sys.argv)
        self.tray_icon = None

        self.window.btn_refresh.clicked.connect(self.refresh_devices)
        self.window.btn_start.clicked.connect(self.toggle_audio)
        self.window.btn_stop.clicked.connect(self.stop_audio)
        self.window.btn_calibrate.clicked.connect(self.start_auto_calibration)

        self.window.list_devices.itemChanged.connect(self.on_device_checked)

        self.window.btn_save_group.clicked.connect(self.save_group)
        self.window.list_groups.itemClicked.connect(self.apply_group)
        self.window.list_groups.customContextMenuRequested.connect(self.show_group_context_menu)

        self.config = self.config_mgr.load()
        autostart_enabled = self.config.get("autostart", False)
        minimize_to_tray = self.config.get("minimize_to_tray", True)
        self.window.chk_autostart.setChecked(autostart_enabled)
        self.window.chk_minimize_to_tray.setChecked(minimize_to_tray)
        self.window.chk_autostart.stateChanged.connect(self.on_autostart_changed)
        self.window.chk_minimize_to_tray.stateChanged.connect(self.on_minimize_to_tray_changed)
        self.window.closeEvent = self.on_main_window_close

        self.refresh_devices()
        self.restore_settings()
        self.load_groups()
        self.setup_tray()
        self.ensure_autostart()

        if self.silent_start:
            QTimer.singleShot(0, self.auto_start_last_session)
        else:
            self.window.show()

    def show_custom_message(self, title, text, buttons=QMessageBox.Ok):
        """显示消息对话框"""
        msg = QMessageBox(self.window)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setWindowIcon(QIcon(resource_path('icon/main_program.png')))
        msg.setStandardButtons(buttons)
        return msg.exec_()

    def show_group_context_menu(self, pos):
        """显示设备组合菜单"""
        item = self.window.list_groups.itemAt(pos)
        if not item: return

        menu = QMenu()
        action_rename = menu.addAction("重命名")
        action_delete = menu.addAction("删除")

        action = menu.exec_(self.window.list_devices.mapToGlobal(pos))

        if action == action_rename:
            new_name, ok = QInputDialog.getText(self.window, "重命名组合", "新名称:", text=item.text())
            if ok and new_name:
                self.rename_group(item.text(), new_name)
        elif action == action_delete:
            result = self.show_custom_message(
                "删除组合",
                f"确定要删除 '{item.text()}' 吗?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.Yes:
                self.delete_group(item.text())

    def rename_group(self, old_name, new_name):
        """重命名设备组合"""
        groups = self.config_mgr.get("groups", {})
        if old_name in groups:
            groups[new_name] = groups.pop(old_name)
            self.config_mgr.set("groups", groups)
            self.config_mgr.save()
            self.load_groups()
            self.window.lbl_status.setText(f"已重命名: {old_name} -> {new_name}")

    def delete_group(self, name):
        """删除设备组合"""
        groups = self.config_mgr.get("groups", {})
        if name in groups:
            del groups[name]
            self.config_mgr.set("groups", groups)
            self.config_mgr.save()
            self.load_groups()
            self.window.lbl_status.setText(f"已删除: {name}")

    def refresh_devices(self):
        """刷新音频设备列表"""
        was_running = self.engine.running

        current_active_names = set()
        for dev_id in self.selected_output_ids:
            for dev in self.dm.get_output_devices():
                if dev['id'] == dev_id:
                    current_active_names.add(dev['name'])
                    break

        if was_running:
            self.stop_audio()
            self.window.lbl_status.setText("状态: 正在刷新设备列表...")
            QApplication.processEvents()

        self.dm.refresh_devices()

        self.window.combo_input.clear()
        cable_output_index = -1

        for i, dev in enumerate(self.dm.get_input_devices()):
            self.window.combo_input.addItem(dev['name'], dev['id'])
            if "CABLE Output" in dev['name'] or "VB-Audio" in dev['name']:
                cable_output_index = i

        if cable_output_index >= 0:
            self.window.combo_input.setCurrentIndex(cable_output_index)

        self.window.combo_mic.clear()
        default_mic_index = -1
        default_input_id = sd.default.device[0]

        for i, dev in enumerate(self.dm.get_input_devices()):
            self.window.combo_mic.addItem(dev['name'], dev['id'])
            if dev['id'] == default_input_id:
                default_mic_index = i

        if default_mic_index >= 0:
            self.window.combo_mic.setCurrentIndex(default_mic_index)

        self.window.clear_devices()
        self.window.device_widgets.clear()
        self.selected_output_ids.clear()

        for dev in self.dm.get_output_devices():
            widget = self.window.add_device_to_list(dev['id'], dev['name'])

            if dev['name'] in current_active_names:
                item = self.window.list_devices.item(self.window.list_devices.count() - 1)
                item.setCheckState(Qt.Checked)
                self.selected_output_ids.add(dev['id'])

            widget.delay_changed.connect(self.on_delay_changed)
            widget.volume_changed.connect(self.on_volume_changed)

        if was_running and self.selected_output_ids:
            self.window.btn_start.setChecked(True)
            self.toggle_audio()
        elif was_running and not self.selected_output_ids:
            self.window.lbl_status.setText("状态: 设备已断开，同步停止")

        in_count = len(self.dm.get_input_devices())
        out_count = len(self.dm.get_output_devices())
        self.window.lbl_status.setText(f"状态: 刷新完成 (输入: {in_count}, 输出: {out_count})")

    def restore_settings(self):
        """恢复配置设置"""
        saved_input = self.config.get("input_device")
        if saved_input:
            index = self.window.combo_input.findText(saved_input)
            if index >= 0:
                self.window.combo_input.setCurrentIndex(index)

        saved_settings = self.config.get("device_settings", {})
        saved_selected = self.config.get("output_devices", [])
        current_devices = {d['id']: d['name'] for d in self.dm.get_output_devices()}

        for i in range(self.window.list_devices.count()):
            item = self.window.list_devices.item(i)
            dev_id = item.data(Qt.UserRole)
            dev_name = current_devices.get(dev_id)
            if dev_name in saved_settings:
                settings = saved_settings[dev_name]
                widget = self.window.device_widgets.get(dev_id)
                if widget:
                    widget.spin_delay.setValue(settings.get("delay", 0))
                    widget.slider_vol.setValue(settings.get("volume", 100))
                    self.engine.set_delay(dev_id, settings.get("delay", 0))
                    self.engine.set_volume(dev_id, settings.get("volume", 100))

        for i in range(self.window.list_devices.count()):
            item = self.window.list_devices.item(i)
            dev_id = item.data(Qt.UserRole)
            dev_name = current_devices.get(dev_id)
            if dev_name in saved_selected:
                item.setCheckState(Qt.Checked)

    def load_groups(self):
        """加载设备组合"""
        self.window.list_groups.clear()
        groups = self.config_mgr.get("groups", {})
        for name in groups.keys():
            self.window.list_groups.addItem(name)

    def save_group(self):
        """保存设备组合"""
        if not self.selected_output_ids:
            self.show_custom_message("提示", "请先选择设备")
            return

        groups = self.config_mgr.get("groups", {})
        idx = len(groups) + 1
        name = f"组合 {idx}"

        current_devices = {d['id']: d['name'] for d in self.dm.get_output_devices()}
        active_names = []
        for dev_id in self.selected_output_ids:
            if dev_id in current_devices:
                active_names.append(current_devices[dev_id])

        groups[name] = active_names
        self.config_mgr.set("groups", groups)
        self.config_mgr.save()

        self.window.list_groups.addItem(name)
        self.window.lbl_status.setText(f"已保存: {name}")

    def apply_group(self, item):
        """应用设备组合"""
        group_name = item.text()
        groups = self.config_mgr.get("groups", {})
        target_devices = groups.get(group_name, [])

        if not target_devices:
            return

        was_running = self.engine.running
        if was_running:
            self.stop_audio()
            QApplication.processEvents()

        self.window.list_devices.blockSignals(True)
        for i in range(self.window.list_devices.count()):
            it = self.window.list_devices.item(i)
            it.setCheckState(Qt.Unchecked)
        self.selected_output_ids.clear()
        self.window.list_devices.blockSignals(False)

        for i in range(self.window.list_devices.count()):
            it = self.window.list_devices.item(i)
            dev_name = it.text()
            if dev_name in target_devices:
                it.setCheckState(Qt.Checked)

        if was_running and self.selected_output_ids:
            self.window.btn_start.setChecked(True)
            self.toggle_audio()

        self.window.lbl_status.setText(f"已应用: {group_name}")

    def on_device_checked(self, item):
        """处理设备选中状态"""
        if self.engine.running:
            state = item.checkState()
            self.window.list_devices.blockSignals(True)
            if state == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
            self.window.list_devices.blockSignals(False)
            self.window.lbl_status.setText("状态: 运行中 (请停止后再修改设备选择)")
            return

        dev_id = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.selected_output_ids.add(dev_id)
        else:
            self.selected_output_ids.discard(dev_id)
        self.save_current_settings()

    def on_delay_changed(self, dev_id, delay_ms):
        """设置设备延迟"""
        self.engine.set_delay(dev_id, delay_ms)
        self.save_current_settings()

    def on_volume_changed(self, dev_id, volume):
        """设置设备音量"""
        self.engine.set_volume(dev_id, volume)
        self.save_current_settings()

    def toggle_audio(self):
        """切换同步状态"""
        if self.window.btn_start.isChecked():
            input_idx = self.window.combo_input.currentData()
            if input_idx is None:
                self.show_custom_message("错误", "未选择输入设备")
                self.window.btn_start.setChecked(False)
                return
            if not self.selected_output_ids:
                self.show_custom_message("错误", "未选择输出设备")
                self.window.btn_start.setChecked(False)
                return

            self.window.lbl_status.setText("状态: 启动中...")
            QApplication.processEvents()

            success = self.engine.start_streams(input_idx, list(self.selected_output_ids))

            if success:
                self.window.lbl_status.setText("状态: 运行中")
                self.window.btn_start.setText("运行中")
                self.window.btn_stop.setEnabled(True)
                self.window.combo_input.setEnabled(False)
            else:
                self.window.lbl_status.setText("状态: 启动流失败")
                self.window.btn_start.setChecked(False)
        else:
            self.stop_audio()

    def stop_audio(self):
        """停止同步"""
        self.engine.stop_streams()
        self.window.lbl_status.setText("状态: 已停止")
        self.window.btn_start.setChecked(False)
        self.window.btn_start.setText("开始同步")
        self.window.btn_stop.setEnabled(False)
        self.window.combo_input.setEnabled(True)

    def save_current_settings(self):
        """保存当前设置"""
        self.config_mgr.set("input_device", self.window.combo_input.currentText())
        current_devices = {d['id']: d['name'] for d in self.dm.get_output_devices()}
        active_names = []
        settings = {}

        for dev_id in self.selected_output_ids:
            name = current_devices.get(dev_id)
            if name:
                active_names.append(name)

        for dev_id, widget in self.window.device_widgets.items():
            name = current_devices.get(dev_id)
            if name:
                settings[name] = {
                    "delay": widget.spin_delay.value(),
                    "volume": widget.slider_vol.value()
                }

        self.config_mgr.set("device_settings", settings)
        self.config_mgr.set("output_devices", active_names)
        self.config_mgr.save()

    def auto_start_last_session(self):
        """自动启动同步"""
        input_id = self.window.combo_input.currentData()
        if input_id is None or not self.selected_output_ids:
            return
        if self.engine.running:
            return

        self.window.btn_start.setChecked(True)
        self.toggle_audio()

        if self.engine.running:
            self.show_tray_message("VoiceSharer", "已自动按上次配置开始同步")

    def setup_tray(self):
        """设置托盘图标"""
        icon = QIcon(resource_path('icon/main_program.png'))
        self.tray_icon = QSystemTrayIcon(icon, self.window)
        self.tray_icon.setToolTip("VoiceSharer")
        menu = QMenu()
        action_show = menu.addAction("打开主界面")
        action_show.triggered.connect(self.show_main_window)
        menu.addSeparator()
        action_exit = menu.addAction("退出")
        action_exit.triggered.connect(self.exit_app)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """处理托盘激活"""
        if reason == QSystemTrayIcon.Trigger:
            self.show_main_window()

    def show_main_window(self):
        """显示主窗口"""
        self.window.showNormal()
        self.window.activateWindow()

    def show_tray_message(self, title, text):
        """显示托盘消息"""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, text, QSystemTrayIcon.Information, 3000)

    def ensure_autostart(self):
        """设置开机自启"""
        try:
            if not sys.platform.startswith("win"):
                return
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            autostart_enabled = self.config_mgr.get("autostart", False)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
                value_name = "VoiceSharer"
                if autostart_enabled:
                    if getattr(sys, "frozen", False):
                        exe_path = sys.executable
                        cmd = f'"{exe_path}" --silent'
                    else:
                        exe_path = os.path.abspath(__file__)
                        python_exe = sys.executable
                        cmd = f'"{python_exe}" "{exe_path}" --silent'
                    winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, value_name)
                    except FileNotFoundError:
                        pass
        except Exception as e:
            print(f"设置开机自启失败: {e}")

    def on_autostart_changed(self, state):
        """处理自启变更"""
        enabled = (state == Qt.Checked)
        self.config_mgr.set("autostart", enabled)
        self.config_mgr.save()
        self.ensure_autostart()

    def on_minimize_to_tray_changed(self, state):
        """处理最小化到托盘变更"""
        enabled = (state == Qt.Checked)
        self.config_mgr.set("minimize_to_tray", enabled)
        self.config_mgr.save()

    def on_main_window_close(self, event):
        """处理窗口关闭"""
        minimize_enabled = self.config_mgr.get("minimize_to_tray", True)
        if minimize_enabled:
            event.ignore()
            self.window.hide()
            self.show_tray_message("VoiceSharer", "程序已最小化到托盘，在后台继续运行")
        else:
            self.exit_app()

    def exit_app(self):
        """退出程序"""
        if self.tray_icon:
            self.tray_icon.hide()
        self.app.quit()

    def start_auto_calibration(self):
        """启动自动校准"""
        if not self.selected_output_ids:
            self.show_custom_message("错误", "请先选择要同步的输出设备！")
            return

        mic_id = self.window.combo_mic.currentData()
        if mic_id is None:
            self.show_custom_message("错误", "请先选择校准用的麦克风！")
            return

        reply = self.show_custom_message(
            "自动同步校准",
            "校准即将开始，请确保：\n"
            "1. 环境保持安静\n"
            "2. 麦克风可以清晰听到所有选中的输出设备的声音\n"
            "3. 校准过程中会播放测试音，请勿调整音量\n\n"
            "是否开始？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        was_running = self.engine.running
        if was_running:
            self.stop_audio()
            QApplication.processEvents()

        self.window.btn_calibrate.setEnabled(False)
        self.window.btn_calibrate.setText("校准中...")

        self.calib_thread = CalibrationThread(
            self.engine,
            mic_id,
            list(self.selected_output_ids)
        )

        def on_progress(current, total, msg):
            self.window.lbl_status.setText(f"校准中: {msg}")

        def on_finished(absolute_delays):
            """处理校准结果"""
            current_devices = {d['id']: d['name'] for d in self.dm.get_output_devices()}
            name_to_latencies = {}
            name_to_ids = {}

            for dev_id, latency in absolute_delays.items():
                dev_name = current_devices.get(dev_id)
                if not dev_name: continue
                if dev_name not in name_to_latencies:
                    name_to_latencies[dev_name] = []
                    name_to_ids[dev_name] = []
                if latency > 10:
                    name_to_latencies[dev_name].append(latency)
                name_to_ids[dev_name].append(dev_id)

            final_name_latencies = {}
            for dev_name, latencies in name_to_latencies.items():
                if latencies:
                    final_name_latencies[dev_name] = sum(latencies) / len(latencies)

            if not final_name_latencies:
                on_error("未检测到有效的音频延迟信号")
                return

            max_abs_latency = max(final_name_latencies.values())

            updated_names_count = 0
            for dev_name, abs_latency in final_name_latencies.items():
                rel_delay = max(0, min(500, max_abs_latency - abs_latency))
                for dev_id in name_to_ids[dev_name]:
                    widget = self.window.device_widgets.get(dev_id)
                    if widget:
                        widget.spin_delay.setValue(int(round(rel_delay)))
                        self.engine.set_delay(dev_id, rel_delay)
                updated_names_count += 1

            self.save_current_settings()
            self.window.btn_calibrate.setEnabled(True)
            self.window.btn_calibrate.setText("自动同步校准")
            self.window.lbl_status.setText(f"状态: 校准完成！")

            if was_running:
                self.window.btn_start.setChecked(True)
                self.toggle_audio()

            self.show_custom_message("完成", f"校准已完成！多采样率设备已自动合并。")

        def on_error(err):
            self.window.btn_calibrate.setEnabled(True)
            self.window.btn_calibrate.setText("自动同步校准")
            self.window.lbl_status.setText("状态: 校准失败")
            self.show_custom_message("校准失败", f"错误: {err}")
            if was_running:
                self.window.btn_start.setChecked(True)
                self.toggle_audio()

        self.calib_thread.progress.connect(on_progress)
        self.calib_thread.finished.connect(on_finished)
        self.calib_thread.error.connect(on_error)
        self.calib_thread.start()

    def run(self):
        """启动程序"""
        sys.exit(self.app.exec_())


if __name__ == '__main__':
    controller = ApplicationController()
    controller.run()