import sys
import os
from PyQt5.QtWidgets import QApplication, QMessageBox, QMenu, QInputDialog, QSystemTrayIcon
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer

from ui import MainWindow
from device_manager import DeviceManager
from audio_engine import AudioEngine
from config_manager import ConfigManager, resource_path

class ApplicationController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        self.dm = DeviceManager()
        self.engine = AudioEngine()
        self.config_mgr = ConfigManager()
        
        self.selected_output_ids = set()
        self.silent_start = ("--silent" in sys.argv or "--tray" in sys.argv)
        self.tray_icon = None
        
        # 连接信号
        self.window.btn_refresh.clicked.connect(self.refresh_devices)
        self.window.btn_start.clicked.connect(self.toggle_audio)
        self.window.btn_stop.clicked.connect(self.stop_audio)
        
        # 监听设备列表变更
        self.window.list_devices.itemChanged.connect(self.on_device_checked)
        
        # 连接组合按钮
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
        msg = QMessageBox(self.window)
        msg.setWindowTitle(title)
        msg.setText(text)
        
        msg.setWindowIcon(QIcon(resource_path('icon/main_program.png')))
        
        msg.setStandardButtons(buttons)
        return msg.exec_()

    def show_group_context_menu(self, pos):
        item = self.window.list_groups.itemAt(pos)
        if not item: return
        
        menu = QMenu()
        action_rename = menu.addAction("重命名")
        action_delete = menu.addAction("删除")
        
        action = menu.exec_(self.window.list_groups.mapToGlobal(pos))
        
        if action == action_rename:
            new_name, ok = QInputDialog.getText(self.window, "重命名组合", "新名称:", text=item.text())
            if ok and new_name:
                self.rename_group(item.text(), new_name)
        elif action == action_delete:
            # 使用删除图标
            result = self.show_custom_message(
                "删除组合", 
                f"确定要删除 '{item.text()}' 吗?", 
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.Yes:
                self.delete_group(item.text())

    def rename_group(self, old_name, new_name):
        groups = self.config_mgr.get("groups", {})
        if old_name in groups:
            groups[new_name] = groups.pop(old_name)
            self.config_mgr.set("groups", groups)
            self.config_mgr.save()
            self.load_groups()
            self.window.lbl_status.setText(f"已重命名: {old_name} -> {new_name}")

    def delete_group(self, name):
        groups = self.config_mgr.get("groups", {})
        if name in groups:
            del groups[name]
            self.config_mgr.set("groups", groups)
            self.config_mgr.save()
            self.load_groups()
            self.window.lbl_status.setText(f"已删除: {name}")

    def refresh_devices(self):
        # 1. 记录当前状态
        was_running = self.engine.running
        
        # 记录选中设备名（防ID变更）
        current_active_names = set()
        for dev_id in self.selected_output_ids:
             for dev in self.dm.get_output_devices():
                 if dev['id'] == dev_id:
                     current_active_names.add(dev['name'])
                     break
        
        # 2. 若运行中则停止，防崩溃
        if was_running:
            self.stop_audio()
            self.window.lbl_status.setText("状态: 正在刷新设备列表...")
            QApplication.processEvents()

        # 3. 刷新设备
        self.dm.refresh_devices()
        
        # 更新输入框
        self.window.combo_input.clear()
        cable_output_index = -1
        
        for i, dev in enumerate(self.dm.get_input_devices()):
            self.window.combo_input.addItem(dev['name'], dev['id'])
            # 自动检测 CABLE Output
            if "CABLE Output" in dev['name'] or "VB-Audio" in dev['name']:
                cable_output_index = i
        
        if cable_output_index >= 0:
             self.window.combo_input.setCurrentIndex(cable_output_index)
            
        # 更新输出列表
        self.window.clear_devices()
        self.window.device_widgets.clear() # 清除逻辑映射
        self.selected_output_ids.clear() # 重置ID
        
        for dev in self.dm.get_output_devices():
            # 添加到列表
            widget = self.window.add_device_to_list(dev['id'], dev['name'])
            
            # 恢复选择
            if dev['name'] in current_active_names:
                # 获取刚添加的项
                item = self.window.list_devices.item(self.window.list_devices.count() - 1)
                item.setCheckState(Qt.Checked)
                self.selected_output_ids.add(dev['id'])
            
            # 连接信号
            widget.delay_changed.connect(self.on_delay_changed)
            widget.volume_changed.connect(self.on_volume_changed)

        # 4. 若此前运行且设备有效，则重启
        if was_running and self.selected_output_ids:
             self.window.btn_start.setChecked(True) # 恢复状态
             self.toggle_audio() # 使用新ID启动
        elif was_running and not self.selected_output_ids:
             self.window.lbl_status.setText("状态: 设备已断开，同步停止")

        # 反馈状态
        in_count = len(self.dm.get_input_devices())
        out_count = len(self.dm.get_output_devices())
        self.window.lbl_status.setText(f"状态: 刷新完成 (输入: {in_count}, 输出: {out_count})")

    def restore_settings(self):
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
        self.window.list_groups.clear()
        groups = self.config_mgr.get("groups", {})
        for name in groups.keys():
            self.window.list_groups.addItem(name)

    def save_group(self):
        if not self.selected_output_ids:
            self.show_custom_message("提示", "请先选择设备")
            return
            
        # 生成组名
        groups = self.config_mgr.get("groups", {})
        idx = len(groups) + 1
        name = f"组合 {idx}"
        
        # 收集设备名
        current_devices = {d['id']: d['name'] for d in self.dm.get_output_devices()}
        active_names = []
        for dev_id in self.selected_output_ids:
            if dev_id in current_devices:
                active_names.append(current_devices[dev_id])
                
        groups[name] = active_names
        self.config_mgr.set("groups", groups)
        self.config_mgr.save()
        
        # 更新列表
        self.window.list_groups.addItem(name)
        self.window.lbl_status.setText(f"已保存: {name}")

    def apply_group(self, item):
        group_name = item.text()
        groups = self.config_mgr.get("groups", {})
        target_devices = groups.get(group_name, [])
        
        if not target_devices:
            return

        # 若运行中则停止
        was_running = self.engine.running
        if was_running:
            self.stop_audio()
            QApplication.processEvents()

        # 取消全选
        self.window.list_devices.blockSignals(True)
        for i in range(self.window.list_devices.count()):
            it = self.window.list_devices.item(i)
            it.setCheckState(Qt.Unchecked)
        self.selected_output_ids.clear()
        self.window.list_devices.blockSignals(False)
        
        # 选中目标设备
        
        # 按名称查找并选中
        for i in range(self.window.list_devices.count()):
            it = self.window.list_devices.item(i)
            dev_id = it.data(Qt.UserRole)
            dev_name = it.text()
            
            if dev_name in target_devices:
                it.setCheckState(Qt.Checked)
                # setCheckState 触发 itemChanged，on_device_checked 添加到 selected_output_ids
        
        # 若此前运行则重启
        if was_running and self.selected_output_ids:
             self.window.btn_start.setChecked(True)
             self.toggle_audio()
        
        self.window.lbl_status.setText(f"已应用: {group_name}")

    def on_device_checked(self, item):
        if self.engine.running:
             state = item.checkState()
             dev_id = item.data(Qt.UserRole)
             
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
        self.engine.set_delay(dev_id, delay_ms)
        self.save_current_settings()

    def on_volume_changed(self, dev_id, volume):
        self.engine.set_volume(dev_id, volume)
        self.save_current_settings()

    def toggle_audio(self):
        if self.window.btn_start.isChecked():
            # 启动
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
            # 停止
            self.stop_audio()

    def stop_audio(self):
        self.engine.stop_streams()
        self.window.lbl_status.setText("状态: 已停止")
        self.window.btn_start.setChecked(False)
        self.window.btn_start.setText("开始同步")
        self.window.btn_stop.setEnabled(False)
        self.window.combo_input.setEnabled(True)
        self.window.list_devices.setEnabled(True)

    def save_current_settings(self):
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
        input_id = self.window.combo_input.currentData()
        if input_id is None:
            self.show_tray_message("多设备音频同步控制", "已在托盘中静默运行（未选择输入设备）")
            return
        if not self.selected_output_ids:
            self.show_tray_message("多设备音频同步控制", "已在托盘中静默运行（未选择输出设备）")
            return
        if self.engine.running:
            return
        self.window.btn_start.setChecked(True)
        self.toggle_audio()
        if self.engine.running:
            self.show_tray_message("多设备音频同步控制", "已自动按上次配置开始同步")

    def setup_tray(self):
        icon = QIcon(resource_path('icon/main_program.png'))
        self.tray_icon = QSystemTrayIcon(icon, self.window)
        self.tray_icon.setToolTip("多设备音频同步控制")
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
        if reason == QSystemTrayIcon.Trigger:
            self.show_main_window()

    def show_main_window(self):
        self.window.showNormal()
        self.window.activateWindow()

    def show_tray_message(self, title, text):
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, text, QSystemTrayIcon.Information, 3000)

    def ensure_autostart(self):
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
        enabled = (state == Qt.Checked)
        self.config_mgr.set("autostart", enabled)
        self.config_mgr.save()
        self.ensure_autostart()

    def on_minimize_to_tray_changed(self, state):
        enabled = (state == Qt.Checked)
        self.config_mgr.set("minimize_to_tray", enabled)
        self.config_mgr.save()

    def on_main_window_close(self, event):
        minimize_enabled = self.config_mgr.get("minimize_to_tray", True)
        if minimize_enabled:
            event.ignore()
            self.window.hide()
            self.show_tray_message("VoiceSharer", "程序已最小化到托盘，在后台继续运行")
        else:
            self.exit_app()

    def exit_app(self):
        if self.tray_icon:
            self.tray_icon.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == '__main__':
    controller = ApplicationController()
    controller.run()
