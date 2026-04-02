from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
    QListWidgetItem, QLabel, QSlider, QSpinBox, QPushButton, 
    QSplitter, QCheckBox, QGroupBox, QComboBox, QFrame, QScrollArea,
    QGraphicsOpacityEffect
)
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize
from config_manager import resource_path

# QSS 样式定义
LIGHT_THEME = """
QMainWindow, QWidget { background-color: #f3f3f3; color: #000000; font-family: "Segoe UI", "Microsoft YaHei"; }
QFrame#PanelOuter { background-color: transparent; border: 1px solid #e5e5e5; border-radius: 12px; } /* 背景透明，留边框 */
QLabel#PanelTitle { font-weight: bold; color: #333333; padding: 4px; font-size: 14px; background-color: transparent; } /* 标题背景透明 */
QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; outline: none; } /* 列表白底圆角 */
QListWidget::item { padding: 10px; border-radius: 6px; margin: 4px; color: #000000; background-color: #ffffff; border: 1px solid #eeeeee; }
QListWidget::item:selected { background-color: #e6f7ff; color: #000000; border: 1px solid #1890ff; }
QListWidget::item:hover { background-color: #f5f5f5; }
QPushButton { background-color: #ffffff; border: 1px solid #d0d0d0; border-radius: 6px; padding: 6px 16px; font-weight: 500; }
QPushButton:hover { background-color: #f5f5f5; border-color: #b0b0b0; }
QPushButton:pressed { background-color: #e0e0e0; }
QPushButton:checked { background-color: #0078d4; color: white; border: none; }
QComboBox { background-color: #ffffff; border: 1px solid #d0d0d0; border-radius: 6px; padding: 6px 10px; min-height: 20px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #666666; margin-right: 8px; }
QSlider::groove:horizontal { border: 1px solid #e0e0e0; height: 6px; background: #eeeeee; margin: 2px 0; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #0078d4; border-radius: 3px; } /* 滑块蓝色填充 */
QSlider::handle:horizontal { background: #666666; border: 2px solid #666666; width: 16px; height: 16px; margin: -6px 0; border-radius: 9px; } /* 滑块深灰手柄 */
QSplitter::handle { background-color: transparent; }
QScrollArea { border: none; background-color: transparent; } /* 滚动区透明无边框 */
QWidget#DeviceCard { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; } /* 卡片样式：白底圆角边框 */
QLabel { color: #000000; }
"""

DARK_THEME = """
QMainWindow, QWidget { background-color: #202020; color: #ffffff; font-family: "Segoe UI", "Microsoft YaHei"; }
QFrame#PanelOuter { background-color: transparent; border: 1px solid #3b3b3b; border-radius: 12px; } /* 背景透明，留边框 */
QLabel#PanelTitle { font-weight: bold; color: #cccccc; padding: 4px; font-size: 14px; background-color: transparent; } /* 标题背景透明 */
QListWidget { background-color: #2d2d2d; border: 1px solid #3b3b3b; border-radius: 8px; outline: none; } /* 列表背景深灰色，圆角 */
QListWidget::item { padding: 10px; border-radius: 6px; margin: 4px; color: #ffffff; background-color: #333333; border: 1px solid #3d3d3d; }
QListWidget::item:selected { background-color: #3a3a3a; color: #ffffff; border: 1px solid #60cdff; }
QListWidget::item:hover { background-color: #333333; }
QPushButton { background-color: #333333; border: 1px solid #454545; border-radius: 6px; padding: 6px 16px; color: #ffffff; font-weight: 500; }
QPushButton:hover { background-color: #3e3e3e; border-color: #555555; }
QPushButton:pressed { background-color: #2e2e2e; }
QPushButton:checked { background-color: #60cdff; color: #000000; border: none; }
QComboBox { background-color: #333333; border: 1px solid #454545; border-radius: 6px; padding: 6px 10px; color: #ffffff; min-height: 20px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #cccccc; margin-right: 8px; }
QSlider::groove:horizontal { border: 1px solid #454545; height: 6px; background: #333333; margin: 2px 0; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #60cdff; border-radius: 3px; } /* 滑块蓝色填充 */
QSlider::handle:horizontal { background: #888888; border: 2px solid #888888; width: 16px; height: 16px; margin: -6px 0; border-radius: 9px; } /* 滑块深灰手柄 */
QSplitter::handle { background-color: transparent; }
QScrollArea { border: none; background-color: transparent; } /* 滚动区透明无边框 */
QWidget#DeviceCard { background-color: #2d2d2d; border: 1px solid #3b3b3b; border-radius: 8px; } /* 卡片样式：深灰底圆角边框 */
QLabel { color: #ffffff; }
"""

class DeviceControlWidget(QWidget):
    """设备设置控件（音量/延迟）"""
    delay_changed = pyqtSignal(int, int)  # 设备ID, 延迟毫秒
    volume_changed = pyqtSignal(int, int) # 设备ID, 音量百分比

    def __init__(self, device_id, device_name, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.device_name = device_name
        self.setObjectName("DeviceCard") # 设置对象名供 QSS 使用
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16) # 增加内边距
        
        # 标题
        self.lbl_name = QLabel(f"设备: {self.device_name}")
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_name)

        # 延迟控制
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("延迟 (毫秒):"))
        
        # 滑块
        self.slider_delay = QSlider(Qt.Horizontal)
        self.slider_delay.setRange(0, 500)
        self.slider_delay.setValue(0)
        self.slider_delay.valueChanged.connect(self.on_slider_delay_change)
        
        # 数字框
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(0, 500)
        self.spin_delay.setSingleStep(1)
        self.spin_delay.valueChanged.connect(self.on_spin_delay_change)
        
        delay_layout.addWidget(self.slider_delay)
        delay_layout.addWidget(self.spin_delay)
        layout.addLayout(delay_layout)

        # 音量控制
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("音量:"))
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(100)
        self.slider_vol.valueChanged.connect(self.on_volume_change)
        vol_layout.addWidget(self.slider_vol)
        self.lbl_vol_val = QLabel("100%")
        vol_layout.addWidget(self.lbl_vol_val)
        layout.addLayout(vol_layout)

        self.setLayout(layout)

    def on_slider_delay_change(self, val):
        self.spin_delay.blockSignals(True)
        self.spin_delay.setValue(val)
        self.spin_delay.blockSignals(False)
        self.delay_changed.emit(self.device_id, val)

    def on_spin_delay_change(self, val):
        self.slider_delay.blockSignals(True)
        self.slider_delay.setValue(val)
        self.slider_delay.blockSignals(False)
        self.delay_changed.emit(self.device_id, val)
        
    def on_delay_change(self, val):
        # 已弃用，保留兼容
        self.delay_changed.emit(self.device_id, val)

    def on_volume_change(self, val):
        self.lbl_vol_val.setText(f"{val}%")
        self.volume_changed.emit(self.device_id, val)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VoiceSharer")
        self.resize(1000, 700) # 默认窗口大小
        self.setWindowIcon(QIcon(resource_path('icon/main_program.png')))
        
        # 主题初始化
        self.current_theme = "light"
        self.setStyleSheet(LIGHT_THEME)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12) # 减小页边距
        main_layout.setSpacing(8) # 减小板块间距

        # 顶部：输入选择
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12) # 增加行间距
        input_layout.addWidget(QLabel("音频源 (输入):"))
        self.combo_input = QComboBox()
        self.btn_refresh = QPushButton("刷新设备列表")
        
        # 主题切换按钮
        self.btn_theme = QPushButton()
        self.btn_theme.setFixedSize(32, 32)
        # 初始浅色（显月亮）
        self.btn_theme.setIcon(QIcon(resource_path('icon/moon.svg')))
        self.btn_theme.setIconSize(QSize(20, 20))
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        # 初始样式
        self.btn_theme.setStyleSheet("QPushButton { border: 1px solid #d0d0d0; border-radius: 4px; background-color: #ffffff; } QPushButton:hover { background-color: #f0f0f0; }")
        self.btn_theme.clicked.connect(self.toggle_theme)
        
        input_layout.addWidget(self.combo_input, 1)
        input_layout.addWidget(self.btn_refresh)
        input_layout.addWidget(self.btn_theme) # 右侧添加
        
        # 包装布局以设置拉伸
        input_widget = QWidget()
        input_widget.setLayout(input_layout)
        main_layout.addWidget(input_widget, 1) # 1:8:1 的 1
        
        # 主分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(12) # 增加手柄宽
        
        # 左侧：设备列表
        # 使用自定义面板
        self.list_devices = QListWidget()
        self.list_devices.itemChanged.connect(self.on_device_check_changed)
        self.list_devices.currentItemChanged.connect(self.on_device_selection_changed)
        left_panel = self.create_panel("输出设备列表", self.list_devices)
        splitter.addWidget(left_panel)

        # 右侧：垂直分割容器
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setHandleWidth(12) # 增加手柄宽作间距
        
        # 1. 设备设置（顶 60%）
        self.right_layout = QVBoxLayout()
        self.right_layout.setAlignment(Qt.AlignTop)
        self.right_layout.setContentsMargins(0, 0, 0, 0) # 无内边距
        
        self.lbl_no_selection = QLabel("请选择要配置的设备")
        self.right_layout.addWidget(self.lbl_no_selection)
        
        # 动态控件容器
        # 使用滚动区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        
        self.control_container = QWidget()
        self.control_layout = QVBoxLayout(self.control_container)
        self.control_layout.setContentsMargins(12, 12, 12, 12) # 滚动区内边距
        self.control_layout.setAlignment(Qt.AlignTop)
        self.control_layout.setSpacing(16) # 增加项间距
        
        self.scroll_area.setWidget(self.control_container)
        self.right_layout.addWidget(self.scroll_area)
        
        # 包装右侧布局
        settings_content_widget = QWidget()
        settings_content_widget.setLayout(self.right_layout)
        
        settings_panel = self.create_panel("设备设置 (独立音量/延迟)", settings_content_widget)
        right_splitter.addWidget(settings_panel)
        
        # 2. 设备组合（底 40%）
        groups_layout = QVBoxLayout()
        groups_layout.setSpacing(8)
        groups_layout.setContentsMargins(0, 0, 0, 0)
        
        self.list_groups = QListWidget()
        self.list_groups.setContextMenuPolicy(Qt.CustomContextMenu) # 启用右键菜单
        groups_layout.addWidget(self.list_groups)
        
        self.btn_save_group = QPushButton("保存当前组合")
        self.btn_save_group.setFixedHeight(36) # 增加高度
        groups_layout.addWidget(self.btn_save_group)
        
        # 包装组合布局
        groups_content_widget = QWidget()
        groups_content_widget.setLayout(groups_layout)
        
        groups_panel = self.create_panel("设备组合", groups_content_widget)
        right_splitter.addWidget(groups_panel)
        
        # 设置拉伸比例 1:1
        right_splitter.setSizes([300, 300]) 
        
        splitter.addWidget(right_splitter)

        splitter.setSizes([300, 500])
        splitter.setHandleWidth(12) # 主手柄宽
        main_layout.addWidget(splitter, 10) # 1:10:1 的 10

        # 底部：全局控制
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(16) # 增加间距
        self.chk_autostart = QCheckBox("开机自启")
        self.chk_minimize_to_tray = QCheckBox("关闭时最小化到托盘")
        self.btn_start = QPushButton("开始同步")
        self.btn_start.setCheckable(True)
        self.btn_start.setFixedSize(120, 40) # 增大按钮
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setFixedSize(80, 40) # 增大按钮
        self.lbl_status = QLabel("状态: 就绪")
        
        bottom_layout.addWidget(self.chk_autostart)
        bottom_layout.addWidget(self.chk_minimize_to_tray)
        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_start)
        bottom_layout.addWidget(self.btn_stop)
        
        # 包装底部布局
        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_layout)
        main_layout.addWidget(bottom_widget, 1) # 1:8:1 的 1

        # 存储设备控件
        self.device_widgets = {} 

    def create_panel(self, title, widget):
        """创建带标题的自定义面板"""
        panel = QFrame()
        panel.setObjectName("PanelOuter")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12) # 外边距形成夹层
        layout.setSpacing(8) # 标题内容间距
        
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("PanelTitle")
        layout.addWidget(lbl)
        
        layout.addWidget(widget)
        return panel

    def on_device_check_changed(self, item):
        # 复选框切换触发
        pass

    def on_device_selection_changed(self, current, previous):
        # 显示设备设置
        if not current:
            self.lbl_no_selection.show()
            self.control_container.hide()
            return

        self.lbl_no_selection.hide()
        self.control_container.show()
        
        # 隐藏所有
        for w in self.device_widgets.values():
            w.hide()

        # 显示当前
        device_id = current.data(Qt.UserRole)
        if device_id in self.device_widgets:
            self.device_widgets[device_id].show()
        else:
            # 若无则忽略
            pass

    def add_device_to_list(self, device_id, device_name):
        item = QListWidgetItem(device_name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        item.setData(Qt.UserRole, device_id)
        self.list_devices.addItem(item)
        
        # 创建控件
        widget = DeviceControlWidget(device_id, device_name)
        widget.hide()
        self.control_layout.addWidget(widget)
        self.device_widgets[device_id] = widget
        return widget

    def clear_devices(self):
        self.list_devices.clear()
        for w in self.device_widgets.values():
            w.deleteLater()
        self.device_widgets.clear()

    def toggle_theme(self):
        # 确定目标主题
        is_light_now = (self.current_theme == "light")
        
        # 切换深浅模式
        target_theme = "dark" if is_light_now else "light"
        target_style = DARK_THEME if is_light_now else LIGHT_THEME
        
        # 设置图标
        target_icon_path = resource_path('icon/sun.svg') if is_light_now else resource_path('icon/moon.svg')
        
        # 调整按钮样式
        btn_style_light = "QPushButton { border: 1px solid #d0d0d0; border-radius: 4px; background-color: #ffffff; } QPushButton:hover { background-color: #f0f0f0; }"
        btn_style_dark = "QPushButton { border: 1px solid #454545; border-radius: 4px; background-color: #333333; } QPushButton:hover { background-color: #3e3e3e; }"
        target_btn_style = btn_style_dark if is_light_now else btn_style_light

        # 1. 截图用于动画
        pixmap = self.grab()
        overlay = QLabel(self)
        overlay.setPixmap(pixmap)
        overlay.setGeometry(0, 0, self.width(), self.height())
        overlay.show()
        overlay.raise_()
        
        # 2. 应用主题
        self.setStyleSheet(target_style)
        self.current_theme = target_theme
        
        # 更新按钮
        self.btn_theme.setIcon(QIcon(target_icon_path))
        self.btn_theme.setStyleSheet(target_btn_style)
        
        # 3. 淡出动画
        self.effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(self.effect)
        
        self.anim = QPropertyAnimation(self.effect, b"opacity")
        self.anim.setDuration(400) # 400ms 过渡
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.finished.connect(overlay.deleteLater)
        self.anim.start()
