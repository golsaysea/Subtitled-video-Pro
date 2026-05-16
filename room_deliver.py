# ==========================================
# 文件名: room_deliver.py (稳定版)
# ==========================================
import os
import json
import tempfile
import re
import threading
import subprocess
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QProgressBar, QTextEdit, QFileDialog, QMessageBox, QDoubleSpinBox,
    QDialog, QTreeWidget, QTreeWidgetItem, QScrollArea, QGridLayout, QCheckBox, QSplitter
)
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QPixmap, QCursor
from core import get_ffmpeg_cmd
from app_theme import apply_tinted_styles
from render_config import build_video_encoder_args, get_render_profile
from playwright.sync_api import sync_playwright

from font_assets import font_face_css
from ui_components import get_exact_duration, get_video_dimensions, get_video_stream_duration, render_subtitle_html
from project_io import load_project, get_project_folder_paths, get_reels_in_folder
from workspace_config import WORKSPACE_MODE_CLOUD, get_active_workspace, get_workspace_config
from project_audit import audit_project, format_project_audit_report
from font_registry import STATUS_NONCOMMERCIAL

CACHE_FILE = os.path.join(tempfile.gettempdir(), "sh_v8_project_cache.json")
SUBTITLE_SUPERSAMPLE = 2


def get_browser_path():
    if os.name == 'nt':
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    else:
        paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


class ProjectPickCard(QFrame):
    def __init__(self, project_data, checked=False, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.project_path = self.project_data.get("project_path", "")
        self.init_ui(checked)

    def init_ui(self, checked):
        self.setFixedSize(180, 245)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 10px; }
            QFrame:hover { border: 2px solid #89b4fa; background-color: #242438; }
            QLabel { border: none; }
            QCheckBox { border: none; color: #cdd6f4; font-weight: bold; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        top_row = QHBoxLayout()
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        top_row.addStretch()
        top_row.addWidget(self.checkbox)
        layout.addLayout(top_row)

        cover = QLabel()
        cover.setFixedSize(164, 145)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet("background-color: #11111b; color: #6c7086; border-radius: 6px; font-weight: bold;")
        cover_rel = self.project_data.get("cover_img", "")
        project_dir = self.project_data.get("project_dir", "")
        cover_path = os.path.join(project_dir, cover_rel) if project_dir and cover_rel else ""
        if cover_path and os.path.exists(cover_path):
            pixmap = QPixmap(cover_path)
            cover.setPixmap(pixmap.scaled(164, 145, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            cover.setText("无封面")
        layout.addWidget(cover)

        name = QLabel(self.project_data.get("project_name", "未命名 Reel"))
        name.setWordWrap(True)
        name.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: bold;")
        layout.addWidget(name)

        date = QLabel(self.project_data.get("updated_at", "").split(" ")[0])
        date.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(date)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


class ProjectPickerDialog(QDialog):
    def __init__(self, workspace, selected_paths=None, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        os.makedirs(self.workspace, exist_ok=True)
        self.selected = {}
        self.cards = []
        for path in selected_paths or []:
            self.selected[self._key(path)] = path
        self.init_ui()
        self.refresh_folders()

    def init_ui(self):
        self.setWindowTitle("选择批量导出的工程")
        self.resize(980, 680)
        self.setStyleSheet("background-color: #11111b; color: #cdd6f4;")
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("工程大厅选择")
        title.setStyleSheet("font-size: 20px; font-weight: 900; color: #cdd6f4;")
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        header.addWidget(title)
        header.addWidget(self.lbl_count)
        header.addStretch()
        main.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #313244; width: 2px; }")
        self.folder_list = QTreeWidget()
        self.folder_list.setHeaderHidden(True)
        self.folder_list.setStyleSheet("""
            QTreeWidget { background: #181825; border: 1px solid #313244; border-radius: 8px; padding: 6px; outline: none; }
            QTreeWidget::item { padding: 8px; margin: 2px 0; border-radius: 6px; color: #a6adc8; font-weight: bold; }
            QTreeWidget::item:hover { background-color: #242438; color: #cdd6f4; }
            QTreeWidget::item:selected { background-color: #89b4fa; color: #11111b; }
        """)
        self.folder_list.itemClicked.connect(lambda item, column: self.on_folder_selected(item))
        splitter.addWidget(self.folder_list)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setSpacing(14)
        scroll.setWidget(self.grid_widget)
        splitter.addWidget(scroll)
        splitter.setSizes([220, 760])
        main.addWidget(splitter, stretch=1)

        actions = QHBoxLayout()
        btn_select_folder = QPushButton("选择当前层")
        btn_select_tree = QPushButton("含子文件夹全选")
        btn_clear = QPushButton("清空选择")
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("确认选择")
        for btn in [btn_select_folder, btn_select_tree, btn_clear, btn_cancel]:
            btn.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 8px 14px; border-radius: 6px;")
        btn_ok.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 8px 18px; border-radius: 6px;")
        btn_select_folder.clicked.connect(lambda: self.select_current_folder(recursive=False))
        btn_select_tree.clicked.connect(lambda: self.select_current_folder(recursive=True))
        btn_clear.clicked.connect(self.clear_selection)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        actions.addWidget(btn_select_folder)
        actions.addWidget(btn_select_tree)
        actions.addWidget(btn_clear)
        actions.addStretch()
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        main.addLayout(actions)
        self.update_count()

    def _key(self, path):
        return os.path.normcase(os.path.abspath(path))

    def _folder_rel_from_item(self, item):
        if not item:
            return ""
        return item.data(0, Qt.ItemDataRole.UserRole) or item.text(0)

    def _folder_path_from_item(self, item):
        rel_path = self._folder_rel_from_item(item)
        return os.path.join(self.workspace, rel_path) if rel_path else ""

    def _add_folder_item(self, rel_path, nodes):
        parent_rel = os.path.dirname(rel_path)
        label = os.path.basename(rel_path)
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, rel_path)
        item.setToolTip(0, rel_path)
        if parent_rel and parent_rel in nodes:
            nodes[parent_rel].addChild(item)
        else:
            self.folder_list.addTopLevelItem(item)
        nodes[rel_path] = item
        return item

    def refresh_folders(self):
        self.folder_list.clear()
        folders = get_project_folder_paths(self.workspace, recursive=True, max_depth=4)
        nodes = {}
        for folder in folders:
            self._add_folder_item(folder, nodes)
        self.folder_list.expandAll()
        if folders:
            first = self.folder_list.topLevelItem(0)
            self.folder_list.setCurrentItem(first)
            self.load_folder(os.path.join(self.workspace, self._folder_rel_from_item(first)))

    def on_folder_selected(self, item):
        if item:
            self.load_folder(self._folder_path_from_item(item))

    def load_folder(self, folder_path):
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.cards = []

        paths = get_reels_in_folder(folder_path, recursive=False)
        if not paths:
            child_count = len(get_reels_in_folder(folder_path, recursive=True))
            empty_text = "这个文件夹当前层没有 Reel 工程"
            if child_count:
                empty_text += f"\n子文件夹里有 {child_count} 个工程，可点左侧子文件夹或用「含子文件夹全选」。"
            empty = QLabel(empty_text)
            empty.setStyleSheet("color: #6c7086; font-size: 15px; padding: 20px;")
            self.grid_layout.addWidget(empty, 0, 0)
            return

        row, col, col_count = 0, 0, 4
        for path in paths:
            try:
                project = load_project(path)
            except Exception:
                continue
            card = ProjectPickCard(project, checked=self._key(path) in self.selected)
            card.checkbox.toggled.connect(lambda checked, p=path: self.set_selected(p, checked))
            self.cards.append(card)
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col >= col_count:
                col = 0
                row += 1
        if hasattr(self, "_theme_colors"):
            apply_tinted_styles(self.grid_widget, self._theme_colors)

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        apply_tinted_styles(self, colors)

    def set_selected(self, path, checked):
        key = self._key(path)
        if checked:
            self.selected[key] = path
        else:
            self.selected.pop(key, None)
        self.update_count()

    def select_current_folder(self, recursive=False):
        item = self.folder_list.currentItem()
        folder_path = self._folder_path_from_item(item) if item else ""
        paths = get_reels_in_folder(folder_path, recursive=recursive) if folder_path else []
        if recursive:
            for path in paths:
                self.selected[self._key(path)] = path
            for card in self.cards:
                card.checkbox.blockSignals(True)
                card.checkbox.setChecked(self._key(card.project_path) in self.selected)
                card.checkbox.blockSignals(False)
            self.update_count()
            return
        for card in self.cards:
            card.checkbox.setChecked(True)

    def clear_selection(self):
        self.selected.clear()
        for card in self.cards:
            card.checkbox.blockSignals(True)
            card.checkbox.setChecked(False)
            card.checkbox.blockSignals(False)
        self.update_count()

    def update_count(self):
        self.lbl_count.setText(f"已选 {len(self.selected)} 个工程")

    def selected_paths(self):
        return list(self.selected.values())


class DeliverView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.project_state = {}
        self.render_process = None
        self.temp_dir = ""
        self.concat_path = ""
        self.out_file_path = ""
        self.batch_project_paths = []
        self.batch_output_dir = ""
        self.batch_rendering = False
        self.batch_render_index = 0
        self.current_batch_project_path = ""
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #181825; border-radius: 10px;")
        left_panel.setFixedWidth(380)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("📦 渲染交付设置 (Deliver)", styleSheet="font-size: 18px; font-weight: bold; color: #cdd6f4;"))
        left_layout.addSpacing(20)
        self.lbl_info = QLabel("等待加载工程...")
        self.lbl_info.setStyleSheet("color: #a6e3a1; font-size: 14px; line-height: 1.5;")
        left_layout.addWidget(self.lbl_info)
        left_layout.addSpacing(20)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("⏱️ 目标导出时长 (秒):", styleSheet="color: #f9e2af; font-weight: bold;"))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(1.0, 36000.0)
        self.spin_duration.setStyleSheet("background: #313244; color: white; padding: 5px; font-size: 14px; border-radius: 3px;")
        dur_row.addWidget(self.spin_duration)
        left_layout.addLayout(dur_row)

        left_layout.addWidget(QLabel("✅ 多轨道时间推演 / 混音器 / 画面缩放\n底层核心已全量挂载！", styleSheet="color: #89b4fa; margin-top: 15px;"))
        batch_frame = QFrame()
        batch_frame.setStyleSheet("background-color: #11111b; border: 1px solid #313244; border-radius: 8px; margin-top: 12px;")
        batch_layout = QVBoxLayout(batch_frame)
        batch_layout.setContentsMargins(12, 12, 12, 12)
        batch_layout.setSpacing(8)
        batch_layout.addWidget(QLabel("批量渲染工程", styleSheet="font-size: 15px; font-weight: bold; color: #f9e2af; border: none;"))
        self.lbl_batch_projects = QLabel("未选择工程")
        self.lbl_batch_projects.setWordWrap(True)
        self.lbl_batch_projects.setStyleSheet("color: #a6adc8; border: none;")
        self.lbl_batch_output = QLabel("输出目录: 未选择")
        self.lbl_batch_output.setWordWrap(True)
        self.lbl_batch_output.setStyleSheet("color: #a6adc8; border: none;")
        self.btn_select_batch_projects = QPushButton("从工程大厅选择")
        self.btn_select_batch_projects.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 7px; border-radius: 5px;")
        self.btn_select_batch_projects.clicked.connect(self.select_batch_projects)
        self.btn_select_batch_output = QPushButton("选择批量成品目录")
        self.btn_select_batch_output.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 7px; border-radius: 5px;")
        self.btn_select_batch_output.clicked.connect(self.select_batch_output_dir)
        self.btn_batch_render = QPushButton("开始批量导出")
        self.btn_batch_render.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; padding: 9px; border-radius: 5px;")
        self.btn_batch_render.clicked.connect(self.start_batch_render)
        batch_layout.addWidget(self.lbl_batch_projects)
        batch_layout.addWidget(self.lbl_batch_output)
        batch_layout.addWidget(self.btn_select_batch_projects)
        batch_layout.addWidget(self.btn_select_batch_output)
        batch_layout.addWidget(self.btn_batch_render)
        left_layout.addWidget(batch_frame)
        left_layout.addStretch()

        self.btn_render = QPushButton("🚀 开始压制导出成片")
        self.btn_render.setFixedHeight(55)
        self.btn_render.setStyleSheet("background-color: #f38ba8; color: #11111b; font-size: 16px; font-weight: bold; border-radius: 8px;")
        self.btn_render.clicked.connect(self.start_render)
        left_layout.addWidget(self.btn_render)
        main_layout.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #1e1e2e; border-radius: 10px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("📋 压制日志 (Render Log)", styleSheet="font-size: 16px; font-weight: bold; color: #89b4fa;"))
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #11111b; color: #a6adc8; font-family: Consolas; font-size: 13px; border: none; padding: 10px;")
        right_layout.addWidget(self.log_console)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 2px solid #313244; border-radius: 5px; text-align: center; color: white; font-weight: bold; } QProgressBar::chunk { background-color: #a6e3a1; }")
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)
        main_layout.addWidget(right_panel, stretch=1)

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        apply_tinted_styles(self, colors)

    def _summarize_project_state(self):
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path", "")
        dur = self.project_state.get("duration", 10.0)
        sub_count = len(self.project_state.get("subs_data", []))
        v_info = f"{len(clips)} 个弹性复合片段" if clips else "未导入"
        a_name = os.path.basename(a_path) if a_path else "未导入"
        info = f"🎥 视频源: {v_info}\n🎵 音频源: {a_name}\n📝 独立字幕片段: {sub_count} 个"
        self.lbl_info.setText(info)
        try:
            dur_value = float(str(dur or 10.0).replace(",", "."))
        except Exception:
            dur_value = 10.0
        self.spin_duration.setValue(max(1.0, dur_value))

    def _project_state_score(self, state):
        if not isinstance(state, dict):
            return 0
        clips = state.get("video_clips", []) or []
        subs = state.get("subs_data", []) or []
        score = len(clips) * 1000 + len(subs)
        if state.get("audio_path"):
            score += 100
        return score

    def _project_candidates(self):
        parent = self.parent()
        candidates = []
        for project in (
            self.project_data,
            getattr(parent, "project", None) if parent else None,
            getattr(getattr(parent, "room_project", None), "project_data", None) if parent else None,
        ):
            if not isinstance(project, dict):
                continue
            state = dict(project.get("room_state", {}).get("edit_room", {}))
            candidates.append((self._project_state_score(state), state, project))

            project_path = project.get("project_path", "")
            if project_path and os.path.exists(project_path):
                try:
                    loaded_project = load_project(project_path)
                    loaded_state = dict(loaded_project.get("room_state", {}).get("edit_room", {}))
                    candidates.append((self._project_state_score(loaded_state), loaded_state, loaded_project))
                except Exception:
                    pass

        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_state = json.load(f)
                if isinstance(cached_state, dict):
                    candidates.append((self._project_state_score(cached_state), cached_state, self.project_data))
            except Exception:
                pass
        return candidates

    def load_project_data(self):
        try:
            candidates = self._project_candidates()
            if candidates:
                _, state, project = max(candidates, key=lambda item: item[0])
                self.project_state = state
                if isinstance(project, dict):
                    self.project_data = project
                    parent = self.parent()
                    if parent is not None and hasattr(parent, "project") and self._project_state_score(state) > 0:
                        parent.project = project
            else:
                self.project_state = {}
            self._summarize_project_state()
        except Exception:
            self.project_state = {}
            self.lbl_info.setText("❌ 工程数据读取失败")

    def log_safe(self, msg, color="#cdd6f4"):
        QTimer.singleShot(0, lambda: self._log_msg(msg, color))

    def _log_msg(self, msg, color):
        self.log_console.append(f"<span style='color:{color}'>{msg}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def update_progress_safe(self, val):
        QTimer.singleShot(0, lambda: self.progress_bar.setValue(int(val)))

    def current_workspace(self):
        parent = self.parent()
        while parent is not None and not hasattr(parent, "room_project"):
            parent = parent.parent()
        room_project = getattr(parent, "room_project", None) if parent else None
        if room_project and getattr(room_project, "workspace", ""):
            return room_project.workspace
        return get_active_workspace()

    def select_batch_projects(self):
        workspace = self.current_workspace()
        if not workspace or not os.path.isdir(workspace):
            return QMessageBox.warning(self, "提示", "当前工作区不可用，请先在工程大厅选择本地或云端工作区。")
        dialog = ProjectPickerDialog(workspace, self.batch_project_paths, self)
        if hasattr(self, "_theme_colors"):
            dialog.apply_theme(self._theme_colors, getattr(self, "_theme_key", ""))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = get_workspace_config()
        source_label = "云端工程大厅" if cfg.get("mode") == WORKSPACE_MODE_CLOUD else "工程大厅"
        self.set_batch_projects(dialog.selected_paths(), source_label=source_label)

    def set_batch_projects(self, paths, source_label="", output_dir=""):
        valid_paths = []
        seen = set()
        for path in paths or []:
            if not path or not os.path.exists(path) or not path.lower().endswith(".scomp"):
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            valid_paths.append(path)

        self.batch_project_paths = valid_paths
        if valid_paths:
            label = f"已选择 {len(valid_paths)} 个工程"
            if source_label:
                label += f" · {source_label}"
            self.lbl_batch_projects.setText(label)
            if output_dir:
                self.batch_output_dir = output_dir
                self.lbl_batch_output.setText(f"输出目录: {output_dir}")
            self.log_safe(f"已接收 {len(valid_paths)} 个批量导出工程。", "#89b4fa")
        else:
            self.lbl_batch_projects.setText("未选择工程")

    def select_batch_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择批量成品输出目录")
        if d:
            self.batch_output_dir = d
            self.lbl_batch_output.setText(f"输出目录: {d}")

    def start_batch_render(self):
        if self.batch_rendering:
            return
        if not self.batch_project_paths:
            return QMessageBox.warning(self, "提示", "请先从工程大厅选择要批量导出的工程。")
        if not self.batch_output_dir:
            return QMessageBox.warning(self, "提示", "请先选择批量成品输出目录。")
        os.makedirs(self.batch_output_dir, exist_ok=True)
        self.batch_rendering = True
        self.batch_render_index = 0
        self.btn_render.setEnabled(False)
        self.btn_batch_render.setEnabled(False)
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.log_safe(f"批量渲染启动，共 {len(self.batch_project_paths)} 个工程。", "#a6e3a1")
        self._start_next_batch_render()

    def _start_next_batch_render(self):
        if self.batch_render_index >= len(self.batch_project_paths):
            self.batch_rendering = False
            self.current_batch_project_path = ""
            self.btn_render.setEnabled(True)
            self.btn_batch_render.setEnabled(True)
            self.progress_bar.setValue(100)
            self.log_safe("批量渲染全部完成。", "#a6e3a1")
            QMessageBox.information(self, "批量渲染完成", f"已处理 {len(self.batch_project_paths)} 个工程。\n输出目录:\n{self.batch_output_dir}")
            return

        project_path = self.batch_project_paths[self.batch_render_index]
        try:
            project = load_project(project_path)
            self.project_data = project
            self.project_state = dict(project.get("room_state", {}).get("edit_room", {}))
            self.log_safe(
                f"📦 读取工程: 字幕 {len(self.project_state.get('subs_data', []) or [])} / 视频 {len(self.project_state.get('video_clips', []) or [])}",
                "#89b4fa",
            )
            if not self.project_state.get("video_clips") or not self.project_state.get("subs_data"):
                self.log_safe(f"跳过工程: {os.path.basename(project_path)} | 缺少视频或字幕数据", "#f38ba8")
                self.batch_render_index += 1
                QTimer.singleShot(0, self._start_next_batch_render)
                return
            batch_audit = audit_project(project, workspace=self.current_workspace())
            if any(row.get("status") == STATUS_NONCOMMERCIAL for row in batch_audit.get("fonts", {}).get("fonts", [])):
                self.log_safe(f"跳过工程: {os.path.basename(project_path)} | 含非商用/禁止商用字体", "#f38ba8")
                self.batch_render_index += 1
                QTimer.singleShot(0, self._start_next_batch_render)
                return
            self.current_batch_project_path = project_path
            self._summarize_project_state()
            self.out_file_path = self._unique_batch_output_path(project)
            self.progress_bar.setValue(0)
            self.log_safe(f"[{self.batch_render_index + 1}/{len(self.batch_project_paths)}] 开始渲染: {project.get('project_name', os.path.basename(project_path))}", "#f9e2af")
            self.log_safe(f"输出: {self.out_file_path}", "#89b4fa")
            threading.Thread(target=self.generate_html_frames, daemon=True).start()
        except Exception as e:
            self.log_safe(f"跳过工程: {os.path.basename(project_path)} | {e}", "#f38ba8")
            self.batch_render_index += 1
            QTimer.singleShot(0, self._start_next_batch_render)

    def _unique_batch_output_path(self, project):
        raw_name = project.get("project_name") or os.path.splitext(os.path.basename(project.get("project_path", "output")))[0]
        safe_name = "".join(c for c in raw_name if c not in r'\/:*?"<>|').strip() or "output"
        candidate = os.path.join(self.batch_output_dir, f"{safe_name}.mp4")
        n = 2
        while os.path.exists(candidate):
            candidate = os.path.join(self.batch_output_dir, f"{safe_name}-{n}.mp4")
            n += 1
        return candidate

    def _handle_render_stage_failed(self):
        if self.batch_rendering:
            try:
                if self.temp_dir:
                    shutil.rmtree(self.temp_dir)
            except Exception:
                pass
            self.batch_render_index += 1
            QTimer.singleShot(0, self._start_next_batch_render)
        else:
            self.btn_render.setEnabled(True)

    def start_render(self):
        self.batch_rendering = False
        self.load_project_data()
        subs = self.project_state.get("subs_data", [])
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path", "")

        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.log_safe(f"📊 字幕数: {len(subs)}", "#89b4fa")
        self.log_safe(f"📊 视频数: {len(clips)}", "#89b4fa")
        self.log_safe(f"📊 音频路径: {a_path or '未提供'}", "#89b4fa")

        if (not clips or not subs) and self.batch_project_paths and self.batch_output_dir:
            self.log_safe("⚠️ 当前工程数据为空，已自动切换到已选择的批量导出队列。", "#f9e2af")
            return self.start_batch_render()

        if not clips:
            return QMessageBox.warning(self, "提示", "请先在 Edit 房间导入至少一个视频片段并保存工程！")
        if not subs:
            return QMessageBox.warning(self, "提示", "当前工程没有字幕数据。请先在 Edit 房间生成字幕并点“保存工程”。")
        if not a_path:
            self.log_safe("⚠️ 未检测到独立音频，将尝试使用视频原声；若原视频也无音轨，则输出静音视频。", "#f9e2af")

        try:
            audit_source = dict(self.project_data or {})
            audit_source.setdefault("room_state", {})["edit_room"] = self.project_state
            preflight = audit_project(audit_source, workspace=self.current_workspace())
            if preflight.get("warnings"):
                has_noncommercial_fonts = any(
                    row.get("status") == STATUS_NONCOMMERCIAL
                    for row in preflight.get("fonts", {}).get("fonts", [])
                )
                self.log_safe("⚠️ 导出前体检发现需要复核的素材或字体。", "#f9e2af")
                detail = format_project_audit_report(preflight, workspace=self.current_workspace())
                reply = QMessageBox.warning(
                    self,
                    "导出前体检提醒",
                    detail + "\n\n仍然继续导出吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No if preflight.get("missing_media") or has_noncommercial_fonts else QMessageBox.StandardButton.Yes,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
        except Exception as e:
            self.log_safe(f"⚠️ 导出前体检跳过: {e}", "#f9e2af")

        file_path, _ = QFileDialog.getSaveFileName(self, "导出最终视频", "", "MP4 Files (*.mp4)")
        if not file_path:
            return
        self.out_file_path = file_path
        self.btn_render.setEnabled(False)
        self.log_safe("🚀 [阶段 1/2] 启动全局时间推演引擎 (多轨道同频渲染)...", "#f9e2af")
        threading.Thread(target=self.generate_html_frames, daemon=True).start()

    def generate_html_frames(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="subtitle_render_")
            self.concat_path = os.path.join(self.temp_dir, "subs_concat.txt").replace("\\", "/")
            blank_path = os.path.join(self.temp_dir, "blank.png").replace("\\", "/")
            subs_data = self.project_state.get("subs_data", [])
            total_dur = float(self.spin_duration.value())

            clips = self.project_state.get("video_clips", [])
            proj_w, proj_h = 1080, 1920
            res_text = self.project_state.get("resolution", "自动检测")
            if "自动跟随" in res_text and clips:
                proj_w, proj_h = get_video_dimensions(clips[0]["path"])
            elif "1080x1920" in res_text:
                proj_w, proj_h = 1080, 1920
            elif "1920x1080" in res_text:
                proj_w, proj_h = 1920, 1080
            elif "1080x1080" in res_text:
                proj_w, proj_h = 1080, 1080

            with sync_playwright() as p:
                b_path = get_browser_path()
                browser = p.chromium.launch(headless=True, executable_path=b_path) if b_path else p.chromium.launch(headless=True)
                render_w = int(proj_w * SUBTITLE_SUPERSAMPLE)
                render_h = int(proj_h * SUBTITLE_SUPERSAMPLE)
                page = browser.new_page(viewport={"width": render_w, "height": render_h}, device_scale_factor=1)
                page.set_content("<html><body style='background:transparent;'></body></html>")
                page.screenshot(path=blank_path, omit_background=True, scale="css")
                bundled_font_css = font_face_css()

                with open(self.concat_path, "w", encoding="utf-8") as f_concat:
                    current_time = 0.0
                    frame_idx = 0
                    fps = 30
                    frame_step = 1.0 / fps
                    last_concat_file = blank_path

                    def write_subtitle_frame(path, duration):
                        nonlocal last_concat_file
                        duration = max(0.001, float(duration or 0.0))
                        f_concat.write(f"file '{path}'\n")
                        f_concat.write(f"duration {duration:.3f}\n")
                        last_concat_file = path

                    while current_time < total_dur:
                        active_subs = [s for s in subs_data if float(s.get('start', 0)) <= current_time <= float(s.get('end', 1))]
                        if not active_subs:
                            future_starts = [float(s.get('start', 0)) for s in subs_data if float(s.get('start', 0)) > current_time]
                            if future_starts:
                                next_start = min(future_starts)
                                gap = next_start - current_time
                                write_subtitle_frame(blank_path, gap)
                                current_time = next_start
                            else:
                                gap = total_dur - current_time
                                if gap > 0:
                                    write_subtitle_frame(blank_path, gap)
                                current_time = total_dur
                            continue

                        html_subs = ""
                        for s in active_subs:
                            px = s.get("pos_x", 0.0)
                            py = s.get("pos_y", 25.0)
                            trk = s.get("track", 1)
                            z_idx = 10 if trk == 0 else 5
                            base_css = f"position: absolute; left: calc(50% + {px}%); top: calc(50% + {py}%); transform: translate(-50%, -50%); z-index: {z_idx}; width: max-content; max-width: 92%;"
                            sub_html = render_subtitle_html(s, current_time, proj_w)
                            html_subs += f"<div style='{base_css}'>{sub_html}</div>\n"

                        # 👑 修复：增加全局抗锯齿和平滑处理
                        html_content = f"""<!DOCTYPE html>
                        <html>
                        <head>
                            <style>
                                {bundled_font_css}
                                html, body {{ 
                                    margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; 
                                    background: transparent; display: flex; justify-content: center; align-items: center; 
                                    -webkit-text-size-adjust: 100%; text-size-adjust: 100%; 
                                    -webkit-font-smoothing: antialiased; 
                                    -moz-osx-font-smoothing: grayscale;
                                    text-rendering: optimizeLegibility;
                                }}
                                #scale-wrapper {{ 
                                    width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; 
                                    transform-origin: center center;
                                }}
                            </style>
                        </head>
                        <body>
                            <div id="scale-wrapper">
                                {html_subs}
                            </div>
                        </body>
                        </html>"""

                        page.set_content(html_content)
                        frame_path = os.path.join(self.temp_dir, f"f_{frame_idx}.png").replace("\\", "/")
                        page.screenshot(path=frame_path, omit_background=True, scale="css")
                        write_subtitle_frame(frame_path, frame_step)
                        current_time += frame_step
                        frame_idx += 1
                        self.update_progress_safe(int((current_time / total_dur) * 50))

                    f_concat.write(f"file '{last_concat_file}'\n")

                browser.close()
            self.log_safe("✅ 多轨道推演截图完毕！准备混音与剪辑...", "#a6e3a1")
            QTimer.singleShot(0, self.start_ffmpeg_qprocess)
        except Exception as e:
            self.log_safe(f"❌ 绘制失败: {str(e)}", "#f38ba8")
            QTimer.singleShot(0, self._handle_render_stage_failed)

    def start_ffmpeg_qprocess(self):
        self.log_safe("🚀 [阶段 2/2] 唤醒 FFmpeg 引擎，执行混合压制...", "#f9e2af")
        clips = self.project_state.get("video_clips", [])
        a_path = self.project_state.get("audio_path")
        target_dur = float(self.spin_duration.value())

        v_scale = self.project_state.get("v_scale", 100) / 100.0
        v_vol = self.project_state.get("v_volume", 100) / 100.0
        a_vol = self.project_state.get("a_volume", 100) / 100.0

        res_text = self.project_state.get("resolution", "自动检测")
        proj_w, proj_h = 1080, 1920
        if "1920x1080" in res_text:
            proj_w, proj_h = 1920, 1080
        elif "1080x1080" in res_text:
            proj_w, proj_h = 1080, 1080
        elif "自动跟随" in res_text and clips:
            proj_w, proj_h = get_video_dimensions(clips[0]["path"])

        video_concat_path = ""
        has_audio = False
        if clips:
            try:
                flags = 0x08000000 if os.name == 'nt' else 0
                res = subprocess.run([get_ffmpeg_cmd(), "-i", clips[0]["path"]], stderr=subprocess.PIPE, stdout=subprocess.PIPE, creationflags=flags, text=True, encoding='utf-8', errors='ignore')
                if "Audio:" in res.stderr:
                    has_audio = True
            except Exception:
                pass

            video_concat_path = os.path.join(self.temp_dir, "v_blocks.txt").replace("\\", "/")
            with open(video_concat_path, "w", encoding="utf-8") as f:
                written_video_dur = 0.0

                def write_looped_clip(clip, duration):
                    clip_path = clip.get("path", "")
                    if not clip_path or duration <= 0:
                        return 0.0
                    media_dur = get_video_stream_duration(clip_path) or float(clip.get("dur", 0.0) or 0.0) or get_exact_duration(clip_path) or 5.0
                    media_dur = max(0.1, media_dur)
                    remaining = duration
                    written = 0.0
                    while remaining > 0.001:
                        part_dur = min(remaining, media_dur)
                        safe_path = clip_path.replace("\\", "/")
                        f.write(f"file '{safe_path}'\n")
                        f.write("inpoint 0\n")
                        f.write(f"outpoint {part_dur:.3f}\n")
                        remaining -= part_dur
                        written += part_dur
                    return written

                for clip in clips:
                    c_start = float(clip.get("start", 0))
                    c_end = float(clip.get("end", 5.0))
                    c_dur = max(0.001, c_end - c_start)
                    written_video_dur += write_looped_clip(clip, c_dur)
                if clips and written_video_dur < target_dur - 0.01:
                    fill_dur = target_dur - written_video_dur
                    write_looped_clip(clips[0], fill_dur)
                    self.log_safe(f"🔁 视频轨短于导出时长，已自动循环补齐 {fill_dur:.1f}s。", "#a6e3a1")
            self.log_safe("🛠️ 已生成物理拼接流: 精确修剪时间点挂载完毕！", "#89b4fa")

        self.render_process = QProcess(self)
        self.render_process.readyReadStandardError.connect(self.on_render_ready_read_error)
        self.render_process.finished.connect(self.on_render_finished)

        args = ["-y"]
        if video_concat_path:
            args.extend(["-f", "concat", "-safe", "0", "-i", video_concat_path])
        args.extend(["-f", "concat", "-safe", "0", "-i", self.concat_path])
        if a_path:
            args.extend(["-i", a_path])

        sub_idx = 1 if video_concat_path else 0
        fc_parts = []
        audio_map = None

        if video_concat_path:
            vf_scale = f"scale={proj_w}*{v_scale}:{proj_h}*{v_scale}:force_original_aspect_ratio=increase"
            vf_crop = f"crop={proj_w}:{proj_h}"
            video_guard = f"tpad=stop_mode=clone:stop_duration={target_dur:.3f},trim=duration={target_dur:.3f},setpts=PTS-STARTPTS"
            sub_guard = f"tpad=stop_mode=clone:stop_duration={target_dur:.3f},trim=duration={target_dur:.3f},setpts=PTS-STARTPTS"
            fc_parts.append(f"[0:v]{vf_scale},{vf_crop},format=rgba,{video_guard}[bg];[{sub_idx}:v]format=rgba,scale={proj_w}:{proj_h}:flags=lanczos,{sub_guard}[sub];[bg][sub]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[outv]")
            if a_path:
                if has_audio:
                    fc_parts.append(f"[0:a]volume={v_vol}[va]")
                else:
                    fc_parts.append("anullsrc=r=44100:cl=stereo[va]")
                fc_parts.append(f"[2:a]volume={a_vol}[aa]")
                fc_parts.append("[va][aa]amix=inputs=2:duration=longest[aout]")
                audio_map = "[aout]"
            elif has_audio:
                fc_parts.append(f"[0:a]volume={v_vol}[va]")
                audio_map = "[va]"
        else:
            fc_parts.append(f"[{sub_idx}:v]format=rgba,scale={proj_w}:{proj_h}:flags=lanczos,tpad=stop_mode=clone:stop_duration={target_dur:.3f},trim=duration={target_dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[outv]")
            if a_path:
                fc_parts.append(f"[1:a]volume={a_vol}[aout]")
                audio_map = "[aout]"

        if fc_parts:
            args.extend(["-filter_complex", ";".join(fc_parts)])

        args.extend(["-map", "[outv]"])

        if audio_map:
            args.extend(["-map", audio_map, "-c:a", "aac", "-b:a", "192k"])
        else:
            args.append("-an")

        # 👑 极速高压引擎：锁定 30 帧(-r 30)，画质降低冗余(-crf 24)，并开启极速预设(-preset superfast)
        render_profile = get_render_profile()
        encoder_label = render_profile.get("encoder_label") or render_profile.get("encoder", "CPU x264")
        args.extend(build_video_encoder_args(render_profile, quality="deliver"))
        args.extend(["-r", "30", "-max_muxing_queue_size", "1024", "-t", str(target_dur), self.out_file_path])
        
        self.log_safe(f"⚙️ 渲染配置: {encoder_label}", "#89b4fa")
        self.log_safe("🧾 FFmpeg 参数已生成，开始压制...", "#89b4fa")
        self.render_process.start(get_ffmpeg_cmd(), args)

    def on_render_ready_read_error(self):
        err_out = str(self.render_process.readAllStandardError(), encoding="utf-8", errors="ignore")
        time_match = re.search(r"time=(\d+:\d+:\d+\.\d+)", err_out)
        if time_match:
            time_str = time_match.group(1)
            h, m, s = map(float, time_str.split(":"))
            curr_sec = h * 3600 + m * 60 + s
            total_sec = max(0.1, self.spin_duration.value())
            percent = 50 + int((curr_sec / total_sec) * 50)
            self.progress_bar.setValue(min(100, percent))
        if err_out.strip():
            self.log_console.append(f"<span style='color:#6c7086'>{err_out.strip()}</span>")
            self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def on_render_finished(self, exit_code, exit_status):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass
        if self.batch_rendering:
            project_name = os.path.basename(self.current_batch_project_path) if self.current_batch_project_path else "工程"
            if exit_code == 0:
                self.log_safe(f"✅ 完成: {project_name}", "#a6e3a1")
            else:
                self.log_safe(f"❌ 失败: {project_name}，错误代码 {exit_code}", "#f38ba8")
            self.batch_render_index += 1
            QTimer.singleShot(0, self._start_next_batch_render)
            return

        self.btn_render.setEnabled(True)
        if exit_code == 0:
            self.progress_bar.setValue(100)
            self.log_safe("🎉 渲染完美收官！视频已成功输出。", "#a6e3a1")
            QMessageBox.information(self, "出片完成", "字幕、音频、画面已按当前工程成功导出。")
        else:
            self.log_safe(f"❌ 渲染崩塌，错误代码: {exit_code}", "#f38ba8")
            QMessageBox.critical(self, "失败", "FFmpeg 渲染发生错误，请查看日志！")
