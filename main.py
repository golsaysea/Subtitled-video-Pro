# ==========================================
# 文件名: main.py (工程房间完整版)
# ==========================================
import sys
import os
import threading

os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

FORCE_SOFTWARE_RENDERING = os.environ.get("SUBTITLE_FORCE_SOFTWARE_RENDERING", "").strip() == "1"

if sys.platform == "win32":
    os.environ["QT_GL_ADAPTER_TYPE"] = "any"

chromium_flags = ["--ignore-gpu-blocklist", "--num-raster-threads=4"]
if FORCE_SOFTWARE_RENDERING:
    os.environ["QT_OPENGL"] = "software"
    chromium_flags.extend([
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
    ])
else:
    os.environ.setdefault("QT_OPENGL", "angle" if sys.platform == "win32" else "desktop")
    chromium_flags.append("--enable-gpu-rasterization")

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(chromium_flags)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QStackedWidget, QToolButton,
    QMenu, QCheckBox, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction

from core import auto_sync_cloud_data
from font_assets import ensure_fonts_dir, register_bundled_fonts
from project_io import load_or_create_default_project, update_room_state
from workspace_config import get_active_workspace
from room_project import PROJECT_HALL_THEMES, ProjectView
from room_edit import EditView
from room_scroll import ScrollView
from room_batch import BatchView
from room_deliver import DeliverView
from room_settings import SettingsView


class SubtitledvideoPro(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.setWindowTitle("Subtitle Video Pro - 工程房间版")
        self.fit_initial_window_to_screen()
        self.setStyleSheet("background-color: #11111b; color: #cdd6f4;")

        self.project = project_data or {}
        self.rooms = []
        self.current_room_index = 0
        self.room_history = []
        self.room_history_pos = -1
        self.app_settings = QSettings("SubtitleComposer", "SubtitleVideoPro")
        self.auto_save_enabled = self.app_settings.value("auto_save_enabled", True, type=bool)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.create_topbar()
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack, stretch=1)
        self.create_sidebar()
        self.create_rooms()
        self.open_default_room()

    def fit_initial_window_to_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(1360, 860)
            return

        available = screen.availableGeometry()
        max_w = max(640, available.width() - 32)
        max_h = max(480, available.height() - 40)
        width = min(1600, max(960, int(available.width() * 0.94)), max_w)
        height = min(980, max(660, int(available.height() * 0.90)), max_h)
        self.setMinimumSize(min(900, max_w), min(600, max_h))
        self.resize(width, height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def create_topbar(self):
        self.topbar = QWidget()
        self.topbar.setStyleSheet("""
            QWidget { background-color: #181825; border-bottom: 1px solid #313244; }
            QToolButton, QPushButton {
                background-color: transparent; color: #a6adc8; border: none;
                padding: 7px 9px; border-radius: 6px; font-weight: bold;
            }
            QToolButton:hover, QPushButton:hover { background-color: #313244; color: #cdd6f4; }
            QToolButton:disabled { color: #45475a; }
            QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; padding: 6px; }
            QMenu::item { padding: 7px 28px 7px 18px; border-radius: 5px; }
            QMenu::item:selected { background-color: #313244; color: #a6e3a1; }
            QCheckBox { color: #a6e3a1; font-weight: bold; padding: 4px 8px; }
        """)
        layout = QHBoxLayout(self.topbar)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(4)

        self.btn_toggle_nav = QToolButton()
        self.btn_toggle_nav.setText("☰")
        self.btn_toggle_nav.setToolTip("显示/隐藏底部房间导航")
        self.btn_toggle_nav.clicked.connect(self.toggle_bottom_nav)
        layout.addWidget(self.btn_toggle_nav)

        self.btn_back = QToolButton()
        self.btn_back.setText("‹")
        self.btn_back.setToolTip("返回上一个房间")
        self.btn_back.clicked.connect(self.go_back)
        layout.addWidget(self.btn_back)

        self.btn_forward = QToolButton()
        self.btn_forward.setText("›")
        self.btn_forward.setToolTip("前进到下一个房间")
        self.btn_forward.clicked.connect(self.go_forward)
        layout.addWidget(self.btn_forward)

        layout.addSpacing(6)
        layout.addWidget(self._make_menu_button("文件", self._build_file_menu()))
        layout.addWidget(self._make_menu_button("编辑", self._build_edit_menu()))
        layout.addWidget(self._make_menu_button("检视", self._build_view_menu()))
        layout.addWidget(self._make_menu_button("窗口", self._build_window_menu()))
        layout.addWidget(self._make_menu_button("说明", self._build_help_menu()))

        layout.addSpacing(10)
        self.project_label = QLabel("")
        self.project_label.setStyleSheet("color: #7f849c; border: none; padding-left: 6px;")
        layout.addWidget(self.project_label, stretch=1)

        self.auto_save_checkbox = QCheckBox("自动保存")
        self.auto_save_checkbox.setChecked(self.auto_save_enabled)
        self.auto_save_checkbox.stateChanged.connect(self.set_auto_save_enabled)
        layout.addWidget(self.auto_save_checkbox)

        self.main_layout.addWidget(self.topbar)
        self.update_history_buttons()

    def _make_menu_button(self, text, menu):
        btn = QToolButton()
        btn.setText(text)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(menu)
        return btn

    def _action(self, text, callback, shortcut=None, checkable=False, checked=False):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(checked)
            action.triggered.connect(callback)
        else:
            action.triggered.connect(lambda checked=False: callback())
        return action

    def _build_file_menu(self):
        menu = QMenu(self)
        menu.addAction(self._action("新建项目文件夹", self.create_project_folder))
        menu.addAction(self._action("新建 Reel", self.create_reel_in_project))
        menu.addAction(self._action("导入工程文件夹", self.import_project_folder))
        menu.addSeparator()
        menu.addAction(self._action("保存当前工程", lambda: self.save_current_project(False), "Ctrl+S"))
        menu.addAction(self._action("进入工程大厅", lambda: self.switch_room(0)))
        menu.addAction(self._action("打开导出中心", lambda: self.switch_room(4)))
        menu.addSeparator()
        menu.addAction(self._action("退出软件", self.close, "Alt+F4"))
        return menu

    def _build_edit_menu(self):
        menu = QMenu(self)
        menu.addAction(self._action("撤销", self.edit_undo, "Ctrl+Z"))
        menu.addAction(self._action("重做", self.edit_redo, "Ctrl+Y"))
        menu.addSeparator()
        menu.addAction(self._action("检查重叠并整理排版", self.reflow_subtitles))
        return menu

    def _build_view_menu(self):
        menu = QMenu(self)
        for idx, name in enumerate(["工程大厅", "精修", "小工具", "批量", "导出", "设置"]):
            menu.addAction(self._action(name, lambda checked=False, i=idx: self.switch_room(i)))
        menu.addSeparator()
        self.action_show_nav = self._action("显示底部房间导航", self.toggle_bottom_nav_from_menu, checkable=True, checked=True)
        menu.addAction(self.action_show_nav)
        return menu

    def _build_window_menu(self):
        menu = QMenu(self)
        menu.addAction(self._action("最大化/还原", self.toggle_max_restore))
        menu.addAction(self._action("全屏/退出全屏", self.toggle_fullscreen, "F11"))
        return menu

    def _build_help_menu(self):
        menu = QMenu(self)
        menu.addAction(self._action("了解软件架构", self.show_architecture_help))
        menu.addAction(self._action("云端协作说明", self.show_cloud_help))
        return menu

    def create_sidebar(self):
        self.nav_widget = QWidget()
        self.nav_widget.setStyleSheet("background-color: #181825; border-top: 1px solid #313244;")
        nav_layout = QHBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(10)

        nav_btn_style = """
            QPushButton { background-color: transparent; color: #a6adc8; font-size: 14px; font-weight: bold; border: none; padding: 10px 14px; border-radius: 8px; }
            QPushButton:hover { background-color: #313244; color: #cdd6f4; }
            QPushButton:checked { background-color: #313244; color: #a6e3a1; }
        """

        self.btn_project = QPushButton("📁 工程")
        self.btn_edit = QPushButton("🎬 精修")
        self.btn_scroll = QPushButton("🧰 小工具")
        self.btn_batch = QPushButton("📦 批量")
        self.btn_deliver = QPushButton("🚀 导出")
        self.btn_settings = QPushButton("⚙️ 设置")

        self.nav_buttons = [
            self.btn_project,
            self.btn_edit,
            self.btn_scroll,
            self.btn_batch,
            self.btn_deliver,
            self.btn_settings,
        ]

        for btn in self.nav_buttons:
            btn.setStyleSheet(nav_btn_style)
            btn.setCheckable(True)

        nav_layout.addStretch()
        for btn in self.nav_buttons:
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        self.main_layout.addWidget(self.nav_widget)

        self.btn_project.clicked.connect(lambda: self.switch_room(0))
        self.btn_edit.clicked.connect(lambda: self.switch_room(1))
        self.btn_scroll.clicked.connect(lambda: self.switch_room(2))
        self.btn_batch.clicked.connect(lambda: self.switch_room(3))
        self.btn_deliver.clicked.connect(lambda: self.switch_room(4))
        self.btn_settings.clicked.connect(lambda: self.switch_room(5))

    def apply_chrome_theme(self, theme_key):
        colors = PROJECT_HALL_THEMES.get(theme_key, PROJECT_HALL_THEMES["dark_star"])
        self.current_theme_key = theme_key if theme_key in PROJECT_HALL_THEMES else "dark_star"
        self.setStyleSheet(f"background-color: {colors['bg']}; color: {colors['text']};")
        if hasattr(self, "topbar"):
            self.topbar.setStyleSheet(f"""
                QWidget {{ background-color: {colors['panel']}; border-bottom: 1px solid {colors['border']}; }}
                QToolButton, QPushButton {{
                    background-color: transparent; color: {colors['muted']}; border: none;
                    padding: 7px 9px; border-radius: 6px; font-weight: bold;
                }}
                QToolButton:hover, QPushButton:hover {{ background-color: {colors['panel_2']}; color: {colors['text']}; }}
                QToolButton:disabled {{ color: {colors['border']}; }}
                QMenu {{ background-color: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 6px; }}
                QMenu::item {{ padding: 7px 28px 7px 18px; border-radius: 5px; }}
                QMenu::item:selected {{ background-color: {colors['selected']}; color: {colors['selected_text']}; }}
                QCheckBox {{ color: {colors['accent_2']}; font-weight: bold; padding: 4px 8px; }}
            """)
        if hasattr(self, "project_label"):
            self.project_label.setStyleSheet(f"color: {colors['muted']}; border: none; padding-left: 6px;")
        if hasattr(self, "nav_widget"):
            self.nav_widget.setVisible(True)
            self.nav_widget.setStyleSheet(f"background-color: {colors['panel']}; border-top: 1px solid {colors['border']};")
            nav_btn_style = f"""
                QPushButton {{
                    background-color: transparent;
                    color: {colors['muted']};
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    padding: 10px 14px;
                    border-radius: 8px;
                }}
                QPushButton:hover {{ background-color: {colors['panel_2']}; color: {colors['text']}; }}
                QPushButton:checked {{ background-color: {colors['selected']}; color: {colors['selected_text']}; }}
            """
            for btn in getattr(self, "nav_buttons", []):
                btn.setStyleSheet(nav_btn_style)
            if hasattr(self, "action_show_nav"):
                self.action_show_nav.setChecked(True)
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background-color: {colors['panel']}; color: {colors['muted']}; border-top: 1px solid {colors['border']}; }}"
        )
        for room in getattr(self, "rooms", []):
            if hasattr(room, "apply_theme"):
                room.apply_theme(colors, self.current_theme_key)

    def is_auto_save_enabled(self):
        return bool(self.auto_save_enabled)

    def set_auto_save_enabled(self, state):
        self.auto_save_enabled = state == Qt.CheckState.Checked.value
        self.app_settings.setValue("auto_save_enabled", self.auto_save_enabled)
        if self.auto_save_enabled:
            self.save_current_project(silent=True)
            self.statusBar().showMessage("自动保存已开启", 3000)
        else:
            self.statusBar().showMessage("自动保存已关闭，记得手动保存工程", 4000)

    def toggle_bottom_nav(self):
        visible = not self.nav_widget.isVisible()
        self.nav_widget.setVisible(visible)
        if hasattr(self, "action_show_nav"):
            self.action_show_nav.setChecked(visible)

    def toggle_bottom_nav_from_menu(self, checked):
        self.nav_widget.setVisible(bool(checked))

    def go_back(self):
        if self.room_history_pos > 0:
            self.room_history_pos -= 1
            self.switch_room(self.room_history[self.room_history_pos], record_history=False)

    def go_forward(self):
        if self.room_history_pos < len(self.room_history) - 1:
            self.room_history_pos += 1
            self.switch_room(self.room_history[self.room_history_pos], record_history=False)

    def update_history_buttons(self):
        if hasattr(self, "btn_back"):
            self.btn_back.setEnabled(self.room_history_pos > 0)
        if hasattr(self, "btn_forward"):
            self.btn_forward.setEnabled(self.room_history_pos < len(self.room_history) - 1)

    def save_current_project(self, silent=False):
        try:
            if self.current_room_index == 1 and hasattr(self.room_edit, "save_to_project"):
                self.project = self.room_edit.save_to_project(silent=True)
            elif self.current_room_index == 2 and hasattr(self.room_scroll, "export_state"):
                self.project = update_room_state(self.project, "scroll_room", self.room_scroll.export_state())
                self.room_scroll.project_data = self.project
            elif hasattr(self.room_edit, "save_to_project"):
                self.project = self.room_edit.save_to_project(silent=True)
            self.refresh_room_links()
            if not silent:
                self.statusBar().showMessage("工程已保存", 3000)
                QMessageBox.information(self, "保存成功", "当前工程已经保存。")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"工程保存失败：\n{e}")

    def create_project_folder(self):
        self.switch_room(0)
        if hasattr(self.room_project, "create_new_folder"):
            self.room_project.create_new_folder()

    def create_reel_in_project(self):
        self.switch_room(0)
        if hasattr(self.room_project, "create_new_reel"):
            self.room_project.create_new_reel()

    def import_project_folder(self):
        self.switch_room(0)
        if hasattr(self.room_project, "import_project_folder_dialog"):
            self.room_project.import_project_folder_dialog()

    def edit_undo(self):
        self.switch_room(1)
        if hasattr(self.room_edit, "undo"):
            self.room_edit.undo()

    def edit_redo(self):
        self.switch_room(1)
        if hasattr(self.room_edit, "redo"):
            self.room_edit.redo()

    def reflow_subtitles(self):
        self.switch_room(1)
        if hasattr(self.room_edit, "audit_and_reflow_subtitles"):
            self.room_edit.audit_and_reflow_subtitles()

    def toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def show_architecture_help(self):
        QMessageBox.information(
            self,
            "软件架构",
            "软件分成 6 个房间：工程大厅、精修、小工具、批量、导出、设置。\n\n"
            "工程文件是 .scomp，素材会放入工程 assets；云端模式下 Google Drive 会同步这些工程文件和素材。\n\n"
            "精修房间负责字幕、时间轴、样式和预览；导出房间读取当前工程并渲染成视频。"
        )

    def show_cloud_help(self):
        QMessageBox.information(
            self,
            "云端协作说明",
            "推荐每个成员使用自己的 Gmail 登录 Google Drive 桌面版。\n\n"
            "团队共享同一个 Google Drive 文件夹，软件在云端工程大厅里打开 Reel，并用成员 Gmail 写入编辑锁，避免多人同时覆盖。\n\n"
            "云端模式导入素材时会自动复制到当前工程 assets，Google Drive 会继续同步上传。"
        )

    def create_rooms(self):
        self.room_project = ProjectView(self.project, self)
        self.room_edit = EditView(self.project, self)
        self.room_scroll = ScrollView(self.project, self)
        self.room_batch = BatchView(self)
        self.room_deliver = DeliverView(self.project, self)
        self.room_settings = SettingsView(self)

        self.rooms = [
            self.room_project,
            self.room_edit,
            self.room_scroll,
            self.room_batch,
            self.room_deliver,
            self.room_settings,
        ]
        for room in self.rooms:
            self.stack.addWidget(room)
        self.apply_chrome_theme(getattr(self.room_project, "project_theme", "dark_star"))

    def open_default_room(self):
        self.switch_room(0, initial=True)

    def refresh_room_links(self):
        if hasattr(self, "project_label"):
            project_name = self.project.get("project_name") or os.path.basename(self.project.get("project_path", "")) or "未命名工程"
            self.project_label.setText(f"当前工程：{project_name}")

        if hasattr(self, "room_project"):
            self.room_project.project_data = self.project
            self.room_project.sync_current_project_label()

        if hasattr(self.room_edit, "project_data"):
            self.room_edit.project_data = self.project

        if hasattr(self.room_scroll, "project_data"):
            self.room_scroll.project_data = self.project
        if hasattr(self.room_scroll, "load_from_project"):
            self.room_scroll.load_from_project(self.project)

        if hasattr(self.room_deliver, "project_data"):
            self.room_deliver.project_data = self.project
        if hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()

    def reload_rooms_from_project(self):
        if hasattr(self.room_edit, "project_data"):
            self.room_edit.project_data = self.project
        if hasattr(self.room_edit, "load_project_on_boot"):
            self.room_edit.load_project_on_boot()

        if hasattr(self.room_scroll, "project_data"):
            self.room_scroll.project_data = self.project
        if hasattr(self.room_scroll, "load_from_project"):
            self.room_scroll.load_from_project(self.project)

        if hasattr(self.room_deliver, "project_data"):
            self.room_deliver.project_data = self.project
        if hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()

        self.refresh_room_links()

    def switch_room(self, index, initial=False, record_history=True):
        if not initial and self.current_room_index == 1 and hasattr(self.room_edit, "save_to_project"):
            self.project = self.room_edit.save_to_project(silent=True)

        if not initial and self.current_room_index == 2 and hasattr(self.room_scroll, "export_state"):
            self.project = update_room_state(self.project, "scroll_room", self.room_scroll.export_state())
            self.room_scroll.project_data = self.project

        self.current_room_index = index
        if record_history:
            if self.room_history_pos < len(self.room_history) - 1:
                self.room_history = self.room_history[:self.room_history_pos + 1]
            if not self.room_history or self.room_history[-1] != index:
                self.room_history.append(index)
                self.room_history_pos = len(self.room_history) - 1
            elif self.room_history_pos == -1:
                self.room_history_pos = 0
        self.refresh_room_links()
        self.stack.setCurrentIndex(index)

        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        if index == 4 and hasattr(self.room_deliver, "load_project_data"):
            self.room_deliver.load_project_data()
        self.update_history_buttons()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ensure_fonts_dir()
    register_bundled_fonts()
    threading.Thread(target=auto_sync_cloud_data, daemon=True).start()

    workspace = get_active_workspace()
    project_data = load_or_create_default_project(workspace)

    window = SubtitledvideoPro(project_data)
    window.showMaximized()
    sys.exit(app.exec())
