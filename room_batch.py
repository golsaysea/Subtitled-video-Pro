# ==========================================
# 文件名: room_batch.py (终极满血修复版 - 包含静音、抗锯齿、完美表格解析与独立预览)
# ==========================================
import os
import json
import tempfile
import threading
import subprocess
import requests
import re
import shutil
import csv
import io
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFrame, QProgressBar, QTextEdit, QFileDialog, 
                             QMessageBox, QComboBox, QTabWidget, QScrollArea, QLineEdit, QDialog, QDoubleSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QMetaObject, Q_ARG
from PyQt6.QtGui import QPixmap
from playwright.sync_api import sync_playwright

from core import get_ffmpeg_cmd
from render_config import build_video_encoder_args, get_render_profile
# 确保导入了 get_exact_duration
from ui_components import (
    get_exact_duration, get_video_dimensions, render_subtitle_html,
    rebalance_subtitle_layout, tokenize_display_text,
    normalize_word_timestamps, align_reference_text_to_timestamps
)
from project_io import create_reel, sync_project_assets_to_project_dir, update_room_state, save_project
from workspace_config import WORKSPACE_MODE_CLOUD, get_active_workspace, get_workspace_config

PRESETS_FILE = os.path.join(os.getcwd(), "style_presets.json") 

def natural_sort_key(path_or_name):
    name = os.path.basename(path_or_name or "")
    stem = os.path.splitext(name)[0].strip()
    prefix = re.match(r"^\s*(\d+)(?:[\s_.\-]+|$)", stem)
    if prefix:
        return (0, int(prefix.group(1)), re.sub(r"^\s*\d+(?:[\s_.\-]+|$)", "", stem).lower())
    return (1, [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", stem)])


def media_sequence_id(path_or_name):
    stem = os.path.splitext(os.path.basename(path_or_name or ""))[0].strip()
    match = re.match(r"^\s*0*(\d+)(?:[\s_.\-]+|$)", stem)
    return str(int(match.group(1))) if match else ""


def normalize_media_title(path_or_name):
    stem = os.path.splitext(os.path.basename(path_or_name or ""))[0].strip().lower()
    stem = re.sub(r"^\s*\d+(?:[\s_.\-]+|$)", "", stem)
    stem = re.sub(r"[\s_.\-]+", "", stem)
    return stem


def build_audio_lookup(input_dir):
    audio_files = sorted(
        [f for f in os.listdir(input_dir) if f.lower().endswith((".mp3", ".wav"))],
        key=natural_sort_key,
    )
    by_stem = {}
    by_seq = {}
    by_title = {}
    for name in audio_files:
        stem = os.path.splitext(name)[0]
        full_path = os.path.join(input_dir, name)
        by_stem.setdefault(stem.lower(), full_path)
        seq = media_sequence_id(name)
        if seq:
            by_seq.setdefault(seq, full_path)
        title = normalize_media_title(name)
        if title:
            by_title.setdefault(title, full_path)
    return {"by_stem": by_stem, "by_seq": by_seq, "by_title": by_title}


def match_audio_for_media(video_name, audio_lookup):
    base_name = os.path.splitext(video_name)[0]
    exact = audio_lookup["by_stem"].get(base_name.lower())
    if exact:
        return exact
    seq = media_sequence_id(video_name)
    if seq and seq in audio_lookup["by_seq"]:
        return audio_lookup["by_seq"][seq]
    title = normalize_media_title(video_name)
    if title and title in audio_lookup["by_title"]:
        return audio_lookup["by_title"][title]
    return ""


def local_get_cf_accounts():
    config_path = os.path.join(os.getcwd(), "settings.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("cf_accounts", [])
        except: pass
    return []

def get_browser_path():
    if os.name == 'nt': 
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]
    else: paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for p in paths:
        if os.path.exists(p): return p
    return None

class BatchTaskRow(QFrame):
    def __init__(self, parent_view=None, parent=None):
        super().__init__(parent)
        self.parent_view = parent_view
        self.video_path = ""
        self.audio_path = ""
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 6px; }")
        self.setFixedHeight(80)
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setSpacing(10)

        self.btn_vid = QPushButton("➕ 选画面")
        self.btn_vid.setFixedSize(90, 40)
        self.btn_vid.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_vid.clicked.connect(self.select_video)
        row_layout.addWidget(self.btn_vid)

        self.btn_aud = QPushButton("🎵 选配音")
        self.btn_aud.setFixedSize(90, 40)
        self.btn_aud.setStyleSheet("background-color: #cba6f7; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_aud.clicked.connect(self.select_audio)
        row_layout.addWidget(self.btn_aud)

        # 👑 新增：独立的高度调节器
        y_layout = QVBoxLayout()
        y_label = QLabel("字幕高度(Y)", styleSheet="color: #a6adc8; font-size: 10px; border: none;")
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-50.0, 50.0)
        self.spin_y.setValue(25.0) # 默认在靠下的位置
        self.spin_y.setSuffix("%")
        self.spin_y.setStyleSheet("background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;")
        self.spin_y.setFixedWidth(70)
        y_layout.addWidget(y_label)
        y_layout.addWidget(self.spin_y)
        row_layout.addLayout(y_layout)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("大标题 (可选)")
        self.txt_title.setStyleSheet("background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; padding: 5px;")
        self.txt_title.setFixedWidth(120)
        row_layout.addWidget(self.txt_title)

        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText("详细正文文案 (支持多行/不填则盲听)")
        self.txt_content.setStyleSheet("background-color: #11111b; color: #a6adc8; border: 1px solid #313244; padding: 5px;")
        row_layout.addWidget(self.txt_content, stretch=1)
        
        # 👑 新增：预览按钮
        self.btn_preview = QPushButton("👁️ 预览")
        self.btn_preview.setFixedSize(70, 40)
        self.btn_preview.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_preview.clicked.connect(self.preview_frame)
        row_layout.addWidget(self.btn_preview)

        self.lbl_status = QLabel("待处理")
        self.lbl_status.setFixedWidth(60)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #a6adc8; border: none;")
        row_layout.addWidget(self.lbl_status)

        self.btn_del = QPushButton("❌")
        self.btn_del.setFixedSize(40, 40)
        self.btn_del.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 4px; border: none;")
        self.btn_del.clicked.connect(self.deleteLater)
        row_layout.addWidget(self.btn_del)

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择画面", "", "Video Files (*.mp4 *.mov *.webm *.jpg *.png)")
        if path:
            self.video_path = path
            self.btn_vid.setText("✅ " + os.path.basename(path)[:4] + "..")
            self.btn_vid.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")

    def select_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择配音", "", "Audio Files (*.mp3 *.wav)")
        if path:
            self.audio_path = path
            self.btn_aud.setText("✅ " + os.path.basename(path)[:4] + "..")
            self.btn_aud.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")

    # 👑 核心魔法：单行截取中间帧预览
    def preview_frame(self):
        if not self.video_path:
            return QMessageBox.warning(self, "提示", "请先选择画面！")
        
        self.btn_preview.setText("加载中..")
        self.btn_preview.setEnabled(False)
        
        try:
            threading.Thread(target=self._generate_preview_thread, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"预览失败: {e}")
            self.btn_preview.setText("👁️ 预览")
            self.btn_preview.setEnabled(True)

    def _generate_preview_thread(self):
        try:
            temp_dir = tempfile.mkdtemp()
            frame_path = os.path.join(temp_dir, "preview_frame.jpg").replace("\\", "/")
            sub_path = os.path.join(temp_dir, "preview_sub.png").replace("\\", "/")
            
            # 1. 用 FFmpeg 提取中间那一帧
            dur = get_exact_duration(self.video_path)
            mid_time = dur / 2.0 if dur > 0 else 0
            subprocess.run([get_ffmpeg_cmd(), "-y", "-ss", str(mid_time), "-i", self.video_path, "-vframes", "1", "-q:v", "2", frame_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 2. 获取预设样式
            preset_style = {}
            if self.parent_view and hasattr(self.parent_view, 'preset_combo'):
                p_name = self.parent_view.preset_combo.currentText()
                if os.path.exists(PRESETS_FILE):
                    try:
                        with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                            preset_style = json.load(f).get(p_name, {})
                    except: pass
                
            # 3. 构造一个假字幕数据
            txt = self.txt_content.toPlainText().strip()
            if not txt: txt = "这是字幕高度位置预览测试"
            txt = txt.split('\n')[0][:15] 
            
            sub_data = {
                "text": txt,
                "words": [{"text": txt, "start": 0, "end": 1}],
                "pos_x": 0.0,
                "pos_y": self.spin_y.value(), 
                "style": preset_style
            }
            
            proj_w, proj_h = get_video_dimensions(self.video_path)
            
            # 4. 用 Playwright 渲染透明字幕截图（带抗锯齿）
            with sync_playwright() as p:
                b_path = get_browser_path()
                browser = p.chromium.launch(headless=True, executable_path=b_path) if b_path else p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": proj_w, "height": proj_h}, device_scale_factor=1)
                
                px = sub_data.get("pos_x", 0.0); py = sub_data.get("pos_y", 25.0)
                base_css = f"position: absolute; left: calc(50% + {px}%); top: calc(50% + {py}%); transform: translate(-50%, -50%); z-index: 10; width: max-content; max-width: 92%;"
                sub_html = render_subtitle_html(sub_data, 0.5, proj_w)
                html_content = f"<!DOCTYPE html><html><head><style>html, body {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; background: transparent; display: flex; justify-content: center; align-items: center; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }} #scale-wrapper {{ width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; filter: drop-shadow(0px 0px 0px transparent); }}</style></head><body><div id='scale-wrapper'><div style='{base_css}'>{sub_html}</div></div></body></html>"
                
                page.set_content(html_content)
                page.screenshot(path=sub_path, omit_background=True)
                browser.close()
                
            # 5. FFmpeg 合成最终预览图
            out_preview = os.path.join(temp_dir, "final_preview.jpg").replace("\\", "/")
            subprocess.run([get_ffmpeg_cmd(), "-y", "-i", frame_path, "-i", sub_path, "-filter_complex", "overlay=0:0", "-vframes", "1", out_preview], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 6. 通知 UI 线程展示
            QMetaObject.invokeMethod(self, "_show_preview_dialog", Qt.ConnectionType.QueuedConnection, Q_ARG(str, out_preview))
            
        except Exception as e:
            print(f"预览出错: {e}")
            QMetaObject.invokeMethod(self, "_reset_preview_btn", Qt.ConnectionType.QueuedConnection)
            
    @pyqtSlot(str)
    def _show_preview_dialog(self, img_path):
        self.btn_preview.setText("👁️ 预览")
        self.btn_preview.setEnabled(True)
        if os.path.exists(img_path):
            dlg = QDialog(self)
            dlg.setWindowTitle("字幕位置预览 (按 ESC 退出)")
            dlg.setFixedSize(400, 711)
            dlg.setStyleSheet("background-color: #11111b;")
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel()
            pixmap = QPixmap(img_path).scaled(400, 711, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pixmap)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            dlg.exec()
            
    @pyqtSlot()
    def _reset_preview_btn(self):
        self.btn_preview.setText("👁️ 预览")
        self.btn_preview.setEnabled(True)

class BatchView(QWidget):
    sig_log = pyqtSignal(str, str)
    sig_progress = pyqtSignal(int)
    sig_file_done = pyqtSignal()
    sig_all_done = pyqtSignal()
    sig_table_row_status = pyqtSignal(int, str, str) 
    sig_projects_done = pyqtSignal(int, int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_dir = ""
        self.output_dir = ""
        self.project_output_dir = ""
        self.task_queue = []
        self.current_idx = 0
        self.is_running = False
        
        self.sig_log.connect(self._append_log)
        self.sig_progress.connect(self._update_progress)
        self.sig_file_done.connect(self._on_file_done)
        self.sig_all_done.connect(self._on_all_done)
        self.sig_table_row_status.connect(self._update_table_row_status)
        self.sig_projects_done.connect(self._on_projects_done)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        top_header = QHBoxLayout()
        top_header.addWidget(QLabel("📦 工业级批量生成引擎 (Matrix Pipeline)", styleSheet="font-size: 22px; font-weight: bold; color: #cdd6f4;"))
        top_header.addStretch()
        
        # 👑 音频静音控制区
        top_header.addWidget(QLabel("🎵 音频处理:", styleSheet="color: #cba6f7; font-weight: bold;"))
        self.audio_mode = QComboBox()
        self.audio_mode.addItems(["🔇 替换/静音 (仅配音)", "🔉 混合原声与配音", "🔊 保留原声 (无视配音)"])
        self.audio_mode.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        top_header.addWidget(self.audio_mode)
        
        top_header.addWidget(QLabel("🎨 强制应用字幕预设:", styleSheet="color: #a6e3a1; font-weight: bold; margin-left: 15px;"))
        self.preset_combo = QComboBox()
        self.preset_combo.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        self.preset_combo.setFixedWidth(200)
        top_header.addWidget(self.preset_combo)
        
        top_header.addWidget(QLabel("✂️ AI断句:", styleSheet="color: #89b4fa; font-weight: bold; margin-left: 15px;"))
        self.chunk_mode = QComboBox()
        self.chunk_mode.addItems(["单字轰炸 (1字/句)", "短句快闪 (3-5字)", "长句大段 (约10字)"])
        self.chunk_mode.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        top_header.addWidget(self.chunk_mode)

        top_header.addWidget(QLabel("🎚️ 时间:", styleSheet="color: #cba6f7; font-weight: bold; margin-left: 10px;"))
        self.timing_mode = QComboBox()
        self.timing_mode.addItems(["L Cut (字幕提前进入)", "J Cut (字幕稍后收尾)", "对齐声音 (按停顿)"])
        self.timing_mode.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-weight: bold; border-radius: 5px;")
        top_header.addWidget(self.timing_mode)
        
        self.btn_set_out_dir = QPushButton("💾 设置全局输出目录")
        self.btn_set_out_dir.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; padding: 5px 15px; border-radius: 5px; margin-left: 15px;")
        self.btn_set_out_dir.clicked.connect(self.select_output_dir)
        top_header.addWidget(self.btn_set_out_dir)

        main_layout.addLayout(top_header)
        
        self.lbl_output = QLabel("当前输出路径: 未选择 (将默认存放在原视频同目录)")
        self.lbl_output.setStyleSheet("color: #a6adc8; font-size: 12px;")
        main_layout.addWidget(self.lbl_output)

        project_out_row = QHBoxLayout()
        self.lbl_project_output = QLabel("批量建工程目录: 未选择（默认当前工作区/批量工程_时间）")
        self.lbl_project_output.setStyleSheet("color: #a6adc8; font-size: 12px;")
        btn_project_out = QPushButton("选择工程目录")
        btn_project_out.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 5px 12px; border-radius: 5px;")
        btn_project_out.clicked.connect(self.select_project_output_dir)
        project_out_row.addWidget(self.lbl_project_output, stretch=1)
        project_out_row.addWidget(btn_project_out)
        main_layout.addLayout(project_out_row)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { background: #181825; color: #a6adc8; padding: 10px 20px; font-size: 15px; font-weight: bold; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #313244; color: #a6e3a1; }
            QTabWidget::pane { border: 2px solid #313244; border-radius: 8px; background: #181825; }
        """)
        
        self.tab_table = QWidget()
        self.init_table_tab()
        self.tabs.addTab(self.tab_table, "📑 多选排列 / 表格手工批量")

        self.tab_folder = QWidget()
        self.init_folder_tab()
        self.tabs.addTab(self.tab_folder, "📁 文件夹全自动匹配")

        main_layout.addWidget(self.tabs, stretch=1)

        bottom_layout = QHBoxLayout()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(120)
        self.log_console.setStyleSheet("background-color: #11111b; color: #a6adc8; font-family: Consolas; font-size: 13px; border: 1px solid #313244; border-radius: 5px; padding: 10px;")
        bottom_layout.addWidget(self.log_console, stretch=1)
        main_layout.addLayout(bottom_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setStyleSheet("QProgressBar { border: 2px solid #313244; border-radius: 5px; text-align: center; color: white; font-weight: bold; } QProgressBar::chunk { background-color: #a6e3a1; }")
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.refresh_presets()

    def open_paste_dialog(self, auto_add=False):
        dialog = QDialog(self)
        dialog.setWindowTitle("📥 智能表格粘贴器")
        dialog.resize(650, 450)
        dialog.setStyleSheet("background-color: #181825;")
        layout = QVBoxLayout(dialog)
        
        lbl = QLabel("去 Excel / 飞书 / 腾讯文档 选中内容按 Ctrl+C，在这里 Ctrl+V：\n👉 完美兼容带回车换行的单元格\n👉 单列：只填正文\n👉 两列：左列大标题，右列详细正文")
        lbl.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 14px; line-height: 1.5;")
        layout.addWidget(lbl)
        
        tb = QTextEdit()
        tb.setStyleSheet("background-color: #11111b; color: #cdd6f4; font-size: 14px; border: 1px solid #313244; border-radius: 5px; padding: 10px;")
        layout.addWidget(tb)
        
        btn = QPushButton("✅ 解析并填入表格")
        btn.setFixedHeight(45)
        btn.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; font-size: 16px; border-radius: 5px;")
        
        def apply_paste():
            content = tb.toPlainText().strip()
            if not content: return
            try:
                lines = list(csv.reader(io.StringIO(content), delimiter='\t'))
            except:
                lines = [line.split('\t') for line in content.split('\n')]
                
            row_widgets = []
            for i in range(self.table_layout.count()):
                w = self.table_layout.itemAt(i).widget()
                if isinstance(w, BatchTaskRow): row_widgets.append(w)
                    
            if auto_add:
                while len(row_widgets) < len(lines):
                    self.add_table_row()
                    w = self.table_layout.itemAt(self.table_layout.count()-1).widget()
                    row_widgets.append(w)
                    
            for i, parts in enumerate(lines):
                if i >= len(row_widgets): break
                if not parts: continue
                row_obj = row_widgets[i]
                
                if len(parts) >= 2:
                    row_obj.txt_title.setText(parts[0].strip())
                    row_obj.txt_content.setPlainText(parts[1].strip())
                elif len(parts) == 1:
                    row_obj.txt_content.setPlainText(parts[0].strip())
                    
            dialog.accept()
            
        btn.clicked.connect(apply_paste)
        layout.addWidget(btn)
        dialog.exec()

    def init_table_tab(self):
        layout = QVBoxLayout(self.tab_table)
        
        toolbar = QHBoxLayout()
        btn_batch_vid = QPushButton("🎞️ 1. 批量选视频"); btn_batch_vid.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        btn_batch_aud = QPushButton("🎵 2. 批量选音频"); btn_batch_aud.setStyleSheet("background-color: #cba6f7; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        btn_paste = QPushButton("📋 3. 从表格/Excel一键粘贴"); btn_paste.setStyleSheet("background-color: #b4befe; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px;")
        
        btn_batch_vid.clicked.connect(self.batch_select_videos)
        btn_batch_aud.clicked.connect(self.batch_select_audios)
        btn_paste.clicked.connect(lambda: self.open_paste_dialog(auto_add=True))
        
        btn_start_table = QPushButton("🚀 开始批量流水线")
        btn_start_table.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-size: 16px; font-weight: bold; padding: 8px 20px; border-radius: 4px;")
        btn_start_table.clicked.connect(self.start_table_batch)

        btn_build_projects = QPushButton("开始创建工程")
        btn_build_projects.setStyleSheet("background-color: #f9e2af; color: #11111b; font-size: 16px; font-weight: bold; padding: 8px 20px; border-radius: 4px;")
        btn_build_projects.clicked.connect(self.start_table_project_build)

        toolbar.addWidget(btn_batch_vid); toolbar.addWidget(btn_batch_aud); toolbar.addWidget(btn_paste)
        toolbar.addStretch(); toolbar.addWidget(btn_build_projects); toolbar.addWidget(btn_start_table)
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.table_content = QWidget()
        self.table_layout = QVBoxLayout(self.table_content)
        self.table_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.table_layout.setSpacing(5)
        scroll.setWidget(self.table_content)
        layout.addWidget(scroll, stretch=1)

        btn_add_row = QPushButton("➕ 新增空行")
        btn_add_row.setStyleSheet("background-color: #313244; color: #cdd6f4; font-weight: bold; padding: 10px; border-radius: 5px;")
        btn_add_row.clicked.connect(self.add_table_row)
        layout.addWidget(btn_add_row)
        
        self.add_table_row()

    def add_table_row(self):
        row = BatchTaskRow(parent_view=self) # 👑 修复：将父视图传给行，以便获取预设样式
        self.table_layout.addWidget(row)

    def _table_rows(self):
        rows = []
        for i in range(self.table_layout.count()):
            widget = self.table_layout.itemAt(i).widget()
            if isinstance(widget, BatchTaskRow):
                rows.append(widget)
        return rows

    def _ensure_table_rows(self, count):
        rows = self._table_rows()
        while len(rows) < count:
            self.add_table_row()
            rows = self._table_rows()
        return rows

    def batch_select_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "批量选择画面", "", "Video/Image Files (*.mp4 *.mov *.webm *.jpg *.png)")
        if not paths:
            return
        paths = sorted(paths, key=natural_sort_key)
        rows = self._ensure_table_rows(len(paths))
        for row, path in zip(rows, paths):
            row.video_path = path
            row.btn_vid.setText("✅ " + os.path.basename(path)[:4] + "..")
            row.btn_vid.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")
            if not row.txt_title.text().strip():
                row.txt_title.setText(os.path.splitext(os.path.basename(path))[0])

    def batch_select_audios(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "批量选择配音", "", "Audio Files (*.mp3 *.wav)")
        if not paths:
            return
        paths = sorted(paths, key=natural_sort_key)
        rows = self._ensure_table_rows(len(paths))
        for row, path in zip(rows, paths):
            row.audio_path = path
            row.btn_aud.setText("✅ " + os.path.basename(path)[:4] + "..")
            row.btn_aud.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px;")

    def init_folder_tab(self):
        layout = QVBoxLayout(self.tab_folder)
        layout.addWidget(QLabel("1. 选择一个包含视频的文件夹，系统会自动扫描并处理。"))
        layout.addWidget(QLabel("2. 如果文件夹内有同名的 .mp3 文件，系统会自动将其作为配音合成。"))
        
        self.btn_input = QPushButton("📂 选择输入文件夹")
        self.btn_input.setFixedHeight(50)
        self.btn_input.setStyleSheet("background-color: #313244; color: white; font-weight: bold; font-size: 16px; border-radius: 8px;")
        self.btn_input.clicked.connect(self.select_input_dir)
        self.lbl_input = QLabel("未选择")
        
        btn_start_folder = QPushButton("🚀 开始全自动扫盘")
        btn_start_folder.setFixedHeight(60)
        btn_start_folder.setStyleSheet("background-color: #f38ba8; color: #11111b; font-size: 18px; font-weight: bold; border-radius: 8px; margin-top: 20px;")
        btn_start_folder.clicked.connect(self.start_folder_batch)

        btn_build_folder_projects = QPushButton("开始创建工程")
        btn_build_folder_projects.setFixedHeight(52)
        btn_build_folder_projects.setStyleSheet("background-color: #f9e2af; color: #11111b; font-size: 16px; font-weight: bold; border-radius: 8px; margin-top: 12px;")
        btn_build_folder_projects.clicked.connect(self.start_folder_project_build)

        layout.addWidget(self.btn_input)
        layout.addWidget(self.lbl_input)
        layout.addStretch()
        layout.addWidget(btn_build_folder_projects)
        layout.addWidget(btn_start_folder)

    def refresh_presets(self):
        self.preset_combo.clear()
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
                    if presets: self.preset_combo.addItems(list(presets.keys()))
            except: pass
        if self.preset_combo.count() == 0: self.preset_combo.addItem("未找到预设，请先在 Edit 房间保存")

    def select_input_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择包含原视频的文件夹")
        if d: self.input_dir = d; self.lbl_input.setText(d)

    def select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择成品保存文件夹")
        if d: self.output_dir = d; self.lbl_output.setText(f"当前输出路径: {d}")

    def select_project_output_dir(self):
        workspace = get_active_workspace()
        os.makedirs(workspace, exist_ok=True)
        d = QFileDialog.getExistingDirectory(self, "选择批量工程保存目录", workspace)
        if d:
            self.project_output_dir = d
            self.lbl_project_output.setText(f"批量建工程目录: {d}")

    def prepare_project_builder(self, project_dir=None, source_label=""):
        self.refresh_presets()
        if project_dir:
            os.makedirs(project_dir, exist_ok=True)
            self.project_output_dir = project_dir
            self.lbl_project_output.setText(f"批量建工程目录: {project_dir}")
        elif not self.project_output_dir:
            self.lbl_project_output.setText("批量建工程目录: 未选择（默认当前工作区/批量工程_时间）")
        self.tabs.setCurrentIndex(0)
        rows = self._ensure_table_rows(1)
        for row in rows:
            row.lbl_status.setText("待建工程")
            row.lbl_status.setStyleSheet("color: #a6adc8; border: none;")
        self.log_console.clear()
        hint = f"已连接到工程「{source_label}」，可直接选择视频、音频、粘贴文案，再点开始创建工程。" if source_label else "可直接选择视频、音频、粘贴文案，再点开始创建工程。"
        self.sig_log.emit(hint, "#89b4fa")

    @pyqtSlot(str, str)
    def _append_log(self, msg, color):
        self.log_console.append(f"<span style='color:{color}'>{msg}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    @pyqtSlot(int)
    def _update_progress(self, val):
        self.progress_bar.setValue(val)
        
    @pyqtSlot(int, str, str)
    def _update_table_row_status(self, idx, text, color):
        if self.tabs.currentIndex() == 0:
            if idx < self.table_layout.count():
                row_widget = self.table_layout.itemAt(idx).widget()
                if isinstance(row_widget, BatchTaskRow):
                    row_widget.lbl_status.setText(text)
                    row_widget.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def start_table_batch(self):
        if self.is_running: return
        self.task_queue.clear()
        
        a_mode = self.audio_mode.currentText()
        for i in range(self.table_layout.count()):
            row_widget = self.table_layout.itemAt(i).widget()
            if isinstance(row_widget, BatchTaskRow):
                if row_widget.video_path:
                    self.task_queue.append({
                        "type": "table",
                        "idx": i,
                        "video": row_widget.video_path,
                        "audio": row_widget.audio_path,
                        "text": row_widget.txt_content.toPlainText().strip(),
                        "a_mode": a_mode,
                        "pos_y": row_widget.spin_y.value() # 👑 提取UI设置的Y轴参数传递给后台队列
                    })
                else:
                    row_widget.lbl_status.setText("略过:无画面")

        if not self.task_queue: return QMessageBox.warning(self, "提示", "表格中没有任何有效画面！")
        self._start_pipeline("📑 表格任务队列")

    def start_table_project_build(self):
        if self.is_running: return
        tasks = []
        for i in range(self.table_layout.count()):
            row_widget = self.table_layout.itemAt(i).widget()
            if isinstance(row_widget, BatchTaskRow):
                if row_widget.video_path:
                    tasks.append({
                        "idx": i,
                        "video": row_widget.video_path,
                        "audio": row_widget.audio_path,
                        "title": row_widget.txt_title.text().strip(),
                        "text": row_widget.txt_content.toPlainText().strip(),
                        "pos_y": row_widget.spin_y.value()
                    })
                else:
                    row_widget.lbl_status.setText("略过:无画面")
        if not tasks:
            return QMessageBox.warning(self, "提示", "表格中没有任何有效画面，无法建立工程。")
        self._start_project_build(tasks, "表格批量建工程")

    def start_folder_batch(self):
        if self.is_running: return
        if not self.input_dir: return QMessageBox.warning(self, "提示", "请先选择输入文件夹！")
        
        self.task_queue.clear()
        v_files = sorted(
            [f for f in os.listdir(self.input_dir) if f.lower().endswith(('.mp4', '.mov', '.webm', '.jpg', '.png'))],
            key=natural_sort_key,
        )
        audio_lookup = build_audio_lookup(self.input_dir)
        a_mode = self.audio_mode.currentText()
        
        for i, vf in enumerate(v_files):
            v_path = os.path.join(self.input_dir, vf)
            a_path = match_audio_for_media(vf, audio_lookup)
                
            self.task_queue.append({
                "type": "folder",
                "idx": i,
                "video": v_path,
                "audio": a_path,
                "text": "",
                "a_mode": a_mode,
                "pos_y": 25.0 # 文件夹模式默认高度
            })
            
        if not self.task_queue: return QMessageBox.warning(self, "提示", "文件夹中没找到视频/图片！")
        self._start_pipeline("📁 文件夹自动队列")

    def start_folder_project_build(self):
        if self.is_running: return
        if not self.input_dir:
            return QMessageBox.warning(self, "提示", "请先选择输入文件夹。")
        tasks = []
        v_files = sorted(
            [f for f in os.listdir(self.input_dir) if f.lower().endswith(('.mp4', '.mov', '.webm', '.jpg', '.png'))],
            key=natural_sort_key,
        )
        audio_lookup = build_audio_lookup(self.input_dir)
        for i, vf in enumerate(v_files):
            v_path = os.path.join(self.input_dir, vf)
            base_name = os.path.splitext(vf)[0]
            text_path = ""
            a_path = match_audio_for_media(vf, audio_lookup)
            for ext in ['.txt', '.md']:
                test_t = os.path.join(self.input_dir, base_name + ext)
                if os.path.exists(test_t):
                    text_path = test_t
                    break
            custom_text = ""
            if text_path:
                try:
                    with open(text_path, "r", encoding="utf-8") as f:
                        custom_text = f.read().strip()
                except Exception:
                    custom_text = ""
            tasks.append({
                "idx": i,
                "video": v_path,
                "audio": a_path,
                "title": base_name,
                "text": custom_text,
                "pos_y": 25.0
            })
        if not tasks:
            return QMessageBox.warning(self, "提示", "文件夹中没有找到视频/图片。")
        self._start_project_build(tasks, "文件夹批量建工程")

    def _start_project_build(self, tasks, mode_name):
        project_dir = self._resolve_project_output_dir()
        preset_style = self._load_selected_preset_style()
        c_mode = self.chunk_mode.currentText()
        timing_mode = self.timing_mode.currentText()
        batch_record = self._init_project_record(tasks, project_dir, mode_name, c_mode, timing_mode)
        self.is_running = True
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.sig_log.emit(f"{mode_name}启动，共 {len(tasks)} 个工程。", "#a6e3a1")
        self.sig_log.emit(f"批量工程记录已创建: {os.path.basename(batch_record['files']['json'])}", "#89b4fa")
        threading.Thread(
            target=self._project_build_worker,
            args=(tasks, project_dir, preset_style, c_mode, timing_mode, batch_record),
            daemon=True
        ).start()

    def _resolve_project_output_dir(self):
        if self.project_output_dir:
            os.makedirs(self.project_output_dir, exist_ok=True)
            return self.project_output_dir
        workspace = get_active_workspace()
        os.makedirs(workspace, exist_ok=True)
        project_dir = os.path.join(workspace, f"批量工程_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(project_dir, exist_ok=True)
        self.project_output_dir = project_dir
        self.lbl_project_output.setText(f"批量建工程目录: {project_dir}")
        return project_dir

    def _load_selected_preset_style(self):
        base_style = {"layout_mode": "standard", "box_layout": "fixed", "box_width": 74.0, "box_height": 0.0, "max_lines": 2}
        preset_name = self.preset_combo.currentText()
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    base_style.update(json.load(f).get(preset_name, {}))
                    return base_style
            except Exception:
                return base_style
        return base_style

    def _record_rel_path(self, base_dir, path):
        if not path:
            return ""
        try:
            return os.path.relpath(path, base_dir).replace("\\", "/")
        except Exception:
            return path

    def _init_project_record(self, tasks, project_dir, mode_name, c_mode, timing_mode):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(project_dir, f"批量工程记录_{run_id}.json")
        csv_path = os.path.join(project_dir, f"批量工程记录_{run_id}.csv")
        record = {
            "record_type": "subtitle_composer_batch_project_build",
            "version": 1,
            "run_id": run_id,
            "mode_name": mode_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": "",
            "project_dir": project_dir,
            "settings": {
                "preset_name": self.preset_combo.currentText(),
                "chunk_mode": c_mode,
                "timing_mode": timing_mode,
                "audio_mode": self.audio_mode.currentText(),
                "output_dir": self.output_dir,
                "input_dir": self.input_dir,
                "workspace_mode": get_workspace_config().get("mode", "local"),
            },
            "summary": {"total": len(tasks), "success": 0, "failed": 0},
            "files": {"json": json_path, "csv": csv_path},
            "rows": [],
        }
        for order, task in enumerate(tasks, start=1):
            task["batch_record"] = {
                "run_id": run_id,
                "row": order,
                "record_json": os.path.basename(json_path),
                "record_csv": os.path.basename(csv_path),
            }
            text = task.get("text", "") or ""
            record["rows"].append({
                "row": order,
                "ui_row": int(task.get("idx", order - 1)) + 1,
                "status": "pending",
                "title": task.get("title", ""),
                "video": task.get("video", ""),
                "audio": task.get("audio", ""),
                "subtitle_y": task.get("pos_y", 25.0),
                "text": text,
                "text_chars": len(text),
                "project_name": "",
                "project_path": "",
                "project_rel_path": "",
                "error": "",
                "started_at": "",
                "finished_at": "",
            })
        self._write_project_record(record)
        return record

    def _write_project_record(self, record):
        try:
            with open(record["files"]["json"], "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            fields = [
                "row", "ui_row", "status", "project_name", "project_rel_path",
                "video", "audio", "title", "subtitle_y", "text_chars", "error",
            ]
            with open(record["files"]["csv"], "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for row in record.get("rows", []):
                    writer.writerow({field: row.get(field, "") for field in fields})
        except Exception as e:
            self.sig_log.emit(f"工程记录写入失败: {e}", "#f38ba8")

    def _project_build_worker(self, tasks, project_dir, preset_style, c_mode, timing_mode, batch_record):
        success = 0
        failed = 0
        built_paths = []
        total = max(1, len(tasks))
        for i, task in enumerate(tasks):
            idx = task.get("idx", i)
            row_record = batch_record["rows"][i] if i < len(batch_record.get("rows", [])) else None
            try:
                if row_record is not None:
                    row_record["status"] = "building"
                    row_record["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._write_project_record(batch_record)
                self.sig_table_row_status.emit(idx, "建工程中", "#f9e2af")
                project_path = self._build_single_project(task, project_dir, preset_style, c_mode, timing_mode)
                success += 1
                if project_path:
                    built_paths.append(project_path)
                if row_record is not None:
                    row_record["status"] = "success"
                    row_record["project_name"] = os.path.splitext(os.path.basename(project_path))[0] if project_path else ""
                    row_record["project_path"] = project_path
                    row_record["project_rel_path"] = self._record_rel_path(project_dir, project_path)
                    row_record["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._write_project_record(batch_record)
                self.sig_table_row_status.emit(idx, "已建工程", "#a6e3a1")
                self.sig_log.emit(f"已建立工程: {os.path.basename(project_path)}", "#a6e3a1")
            except Exception as e:
                failed += 1
                if row_record is not None:
                    row_record["status"] = "failed"
                    row_record["error"] = str(e)
                    row_record["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._write_project_record(batch_record)
                self.sig_table_row_status.emit(idx, "失败", "#f38ba8")
                self.sig_log.emit(f"工程建立失败: {os.path.basename(task.get('video', ''))} | {e}", "#f38ba8")
            self.sig_progress.emit(int((i + 1) * 100 / total))
        batch_record["summary"] = {"total": len(tasks), "success": success, "failed": failed}
        batch_record["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_project_record(batch_record)
        payload = {"built_paths": built_paths, "record_json": batch_record["files"]["json"], "record_csv": batch_record["files"]["csv"]}
        self.sig_projects_done.emit(success, failed, project_dir, payload)

    def _build_single_project(self, task, project_dir, preset_style, c_mode, timing_mode):
        video_path = task.get("video", "")
        audio_path = task.get("audio", "")
        if not video_path or not os.path.exists(video_path):
            raise Exception("视频路径不存在")

        title = task.get("title", "").strip()
        base_name = title or os.path.splitext(os.path.basename(video_path))[0]
        reel_name = self._unique_reel_name(project_dir, base_name)
        project_data = create_reel(project_dir, reel_name, "edit_room")
        if task.get("batch_record"):
            project_data["batch_record"] = task.get("batch_record")

        video_dur = get_exact_duration(video_path) or 5.0
        audio_dur = get_exact_duration(audio_path) if audio_path and os.path.exists(audio_path) else 0.0
        total_dur = max(video_dur, audio_dur, 1.0)
        custom_text = task.get("text", "").strip()
        if not custom_text and title:
            custom_text = title

        sub_task = dict(task)
        sub_task["text"] = custom_text
        subs_data = self._generate_project_subs(sub_task, total_dur, c_mode, timing_mode)
        pos_y = float(task.get("pos_y", 25.0))
        for sub in subs_data:
            sub["style"] = preset_style.copy()
            sub["pos_x"] = 0.0
            sub["pos_y"] = pos_y
            sub["track"] = sub.get("track", 1)
        subs_data, _ = rebalance_subtitle_layout(
            subs_data,
            fallback_style=preset_style,
            default_pos=(0.0, pos_y),
            force_standard_box=True
        )

        edit_state = {
            "video_clips": [{"path": video_path, "start": 0.0, "end": total_dur, "dur": video_dur}],
            "audio_path": audio_path if audio_path and os.path.exists(audio_path) else "",
            "subs_data": subs_data,
            "a_trim": [0.0, audio_dur if audio_dur > 0 else total_dur],
            "duration": total_dur,
            "resolution": "原画检测 (自动跟随)",
            "v_scale": 100,
            "v_volume": 100,
            "a_volume": 100,
            "chunk_mode": c_mode,
            "timing_mode": timing_mode,
            "custom_text": custom_text,
            "default_pos_x": 0.0,
            "default_pos_y": pos_y,
            "default_style": preset_style.copy()
        }
        project_data = update_room_state(project_data, "edit_room", edit_state)
        if task.get("batch_record"):
            project_data["batch_record"] = task.get("batch_record")
            save_project(project_data["project_path"], project_data)
        if get_workspace_config().get("mode") == WORKSPACE_MODE_CLOUD:
            project_data, _ = sync_project_assets_to_project_dir(project_data)
        self._try_generate_project_cover(project_data, video_path)
        return project_data.get("project_path", "")

    def _generate_project_subs(self, task, total_dur, c_mode, timing_mode):
        custom_text = task.get("text", "").strip()
        target_path = task.get("audio") if task.get("audio") else task.get("video")
        words = []

        if target_path and os.path.exists(target_path):
            try:
                words = self._transcribe_words(target_path)
            except Exception:
                if not custom_text:
                    raise

        if custom_text:
            if words:
                words = self._align_user_text_to_ai_words(words, custom_text)
            else:
                words = self._rough_words_from_text(custom_text, total_dur)

        if not words:
            raise Exception("没有可用的文案或 AI 打轴结果")

        return self.process_words(words, c_mode, timing_mode)

    def _transcribe_words(self, target_path):
        accounts = local_get_cf_accounts()
        if not accounts:
            raise Exception("未配置 Cloudflare API 凭证")

        temp_audio = os.path.join(tempfile.gettempdir(), f"sh_project_build_{threading.get_ident()}.mp3")
        try:
            cmd = [get_ffmpeg_cmd(), "-y", "-i", target_path, "-vn", "-map", "a:0?", "-ar", "16000", "-ac", "1", "-b:a", "16k", temp_audio]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            if not os.path.exists(temp_audio) or os.path.getsize(temp_audio) <= 100:
                raise Exception("音频抽取失败")
            with open(temp_audio, "rb") as f:
                data = f.read()

            res_json = None
            last_err = ""
            for acc in accounts:
                if acc.get("id") and acc.get("token"):
                    try:
                        res = requests.post(
                            f"https://api.cloudflare.com/client/v4/accounts/{acc['id']}/ai/run/@cf/openai/whisper",
                            headers={"Authorization": f"Bearer {acc['token']}", "Content-Type": "application/octet-stream"},
                            data=data,
                            timeout=60,
                            verify=False
                        )
                        if res.status_code == 200 and res.json().get("success"):
                            res_json = res.json()
                            break
                        last_err = f"HTTP {res.status_code}: {res.text[:100]}"
                    except Exception as e:
                        last_err = str(e)
            if not res_json:
                raise Exception(f"AI 请求失败: {last_err}")
            return normalize_word_timestamps([
                {"word": re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).replace(".mp3", "").replace(".wav", "").strip(), "start": w["start"], "end": w["end"]}
                for w in res_json["result"]["words"]
                if re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip()
            ])
        finally:
            if os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass

    def _rough_words_from_text(self, raw_text, total_dur):
        tokens = self._tokenize_user_text_for_alignment(raw_text)
        if len(tokens) <= 1:
            cleaned = raw_text.strip()
            if re.search(r"\s", cleaned):
                tokens = cleaned.split()
            else:
                tokens = [ch for ch in cleaned if not ch.isspace()]
        if not tokens:
            return []
        step = max(0.05, float(total_dur) / len(tokens))
        words = []
        for i, token in enumerate(tokens):
            start = i * step
            end = min(float(total_dur), start + step * 0.92)
            if end <= start:
                end = start + 0.05
            words.append({"word": token, "start": start, "end": end})
        return words

    def _unique_reel_name(self, project_dir, base_name):
        safe = "".join(c for c in base_name.strip() if c not in r'\/:*?"<>|') or "批量Reel"
        candidate = safe
        n = 2
        while os.path.exists(os.path.join(project_dir, f"{candidate}.scomp")):
            candidate = f"{safe}-{n}"
            n += 1
        return candidate

    def _try_generate_project_cover(self, project_data, video_path):
        try:
            project_dir = project_data.get("project_dir", "")
            project_name = project_data.get("project_name", "untitled")
            if not project_dir or not video_path or not os.path.exists(video_path):
                return
            cover_filename = f"{project_name}_cover.jpg"
            cover_path = os.path.join(project_dir, cover_filename)
            flags = 0x08000000 if os.name == 'nt' else 0
            subprocess.run(
                [get_ffmpeg_cmd(), "-y", "-ss", "00:00:01", "-i", video_path, "-vframes", "1", "-q:v", "2", cover_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                timeout=15
            )
            if os.path.exists(cover_path):
                project_data["cover_img"] = cover_filename
                save_project(project_data["project_path"], project_data)
        except Exception:
            pass

    def _on_projects_done(self, success, failed, project_dir, built_paths):
        self.is_running = False
        self.progress_bar.setValue(100)
        record_json = ""
        record_csv = ""
        if isinstance(built_paths, dict):
            record_json = built_paths.get("record_json", "")
            record_csv = built_paths.get("record_csv", "")
            built_paths = built_paths.get("built_paths", [])
        self.sig_log.emit(f"批量建工程完成: 成功 {success} 个，失败 {failed} 个。目录: {project_dir}", "#a6e3a1" if success else "#f38ba8")
        if record_json:
            self.sig_log.emit(f"工程记录文件: {record_json}", "#89b4fa")
        parent = self.parent()
        while parent is not None and not hasattr(parent, "room_project"):
            parent = parent.parent()
        if parent and hasattr(parent, "room_project"):
            try:
                parent.room_project.refresh_folders(select_name=os.path.basename(project_dir))
            except Exception:
                pass
        handed_off = False
        if success and parent and hasattr(parent, "room_deliver"):
            output_dir = self.output_dir or os.path.join(project_dir, "批量成品")
            try:
                parent.room_deliver.set_batch_projects(built_paths, source_label=os.path.basename(project_dir), output_dir=output_dir)
                parent.switch_room(4)
                handed_off = True
                self.sig_log.emit("已接入导出房间，可直接开始批量导出。", "#89b4fa")
            except Exception as e:
                self.sig_log.emit(f"接入导出房间失败: {e}", "#f38ba8")
        handoff_text = "\n\n已把成功工程送到导出房间。" if handed_off else ""
        record_text = f"\n\n工程记录:\n{record_json}\n{record_csv}" if record_json else ""
        QMessageBox.information(self, "批量建工程完成", f"成功建立 {success} 个工程，失败 {failed} 个。\n目录:\n{project_dir}{record_text}{handoff_text}")

    def _start_pipeline(self, mode_name):
        self.preset_name = self.preset_combo.currentText()
        self.preset_style = self._load_selected_preset_style()

        self.is_running = True
        self.current_idx = 0
        self.log_console.clear()
        self.sig_log.emit(f"🚀 {mode_name} 启动！共发现 {len(self.task_queue)} 个生产任务。", "#a6e3a1")
        self.process_next()

    def process_next(self):
        if self.current_idx >= len(self.task_queue):
            self.sig_all_done.emit()
            return
            
        task = self.task_queue[self.current_idx]
        v_path = task["video"]
        a_path = task["audio"]
        
        out_dir = self.output_dir if self.output_dir else os.path.dirname(v_path)
        out_name = f"Pro_{os.path.basename(v_path).rsplit('.', 1)[0]}.mp4"
        out_path = os.path.join(out_dir, out_name)
        
        c_mode = self.chunk_mode.currentText()
        timing_mode = self.timing_mode.currentText()
        
        self.sig_table_row_status.emit(task["idx"], "🔄 正在渲染", "#f9e2af")
        self.sig_progress.emit(0)
        
        threading.Thread(target=self.pipeline_worker, args=(task, out_path, c_mode, timing_mode), daemon=True).start()

    def pipeline_worker(self, task, out_path, c_mode, timing_mode):
        temp_dir = tempfile.mkdtemp()
        try:
            v_path = task["video"]
            a_path = task["audio"]
            custom_text = task["text"]
            t_idx = task["idx"]
            a_mode = task.get("a_mode", "🔇 替换/静音 (仅配音)")
            
            self.sig_log.emit(f"▶ 开始装配视频: {os.path.basename(v_path)}", "#89b4fa")
            
            subs_data = []
            
            target_path = a_path if a_path else v_path
            use_custom_text = bool(custom_text.strip())

            self.sig_log.emit(f"  [1/4] 抽取音频供 AI 识别{'并对齐手工文案' if use_custom_text else ''}...", "#cdd6f4")
            temp_audio = os.path.join(temp_dir, "temp.mp3")
            subprocess.run([get_ffmpeg_cmd(), "-y", "-i", target_path, "-vn", "-map", "a:0", "-ar", "16000", "-ac", "1", "-b:a", "16k", "-t", "600", temp_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            
            if os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 10 * 1024 * 1024:
                raise Exception(f"源文件音频轨道异常，已被系统拦截！")
                
            self.sig_progress.emit(10)
            self.sig_log.emit(f"  [2/4] 呼叫 Cloudflare 大模型...", "#cdd6f4")

            accounts = local_get_cf_accounts()
            if not accounts: raise Exception("未配置 Cloudflare API 凭证！")

            res_json = None; last_err = ""
            with open(temp_audio, 'rb') as f: data = f.read()
            for acc in accounts:
                if acc.get("id") and acc.get("token"):
                    try:
                        res = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc['id']}/ai/run/@cf/openai/whisper", headers={"Authorization": f"Bearer {acc['token']}", "Content-Type": "application/octet-stream"}, data=data, timeout=60) 
                        if res.status_code == 200 and res.json().get("success"): res_json = res.json(); break 
                    except Exception as e: last_err = str(e)
            if not res_json: raise Exception(f"AI 请求失败: {last_err}")

            clean_words = normalize_word_timestamps([
                {"word": re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip(), "start": w["start"], "end": w["end"]}
                for w in res_json["result"]["words"]
                if re.sub(r'(?i)stereo_[^\s]+', '', w["word"]).strip()
            ])

            if use_custom_text:
                self.sig_log.emit("  [2.5/4] 检测到手工文案，正在把文案对齐到 AI 时间轴...", "#a6e3a1")
                clean_words = self._align_user_text_to_ai_words(clean_words, custom_text)

            subs_data = self.process_words(clean_words, c_mode, timing_mode)
            row_custom_y = task.get("pos_y", 25.0) # 👑 应用你调整好的独立高度参数
            for sub in subs_data:
                sub["style"] = self.preset_style.copy()
                sub["pos_y"] = row_custom_y        # 👑 强制覆盖
            subs_data, _ = rebalance_subtitle_layout(
                subs_data,
                fallback_style=self.preset_style,
                default_pos=(0.0, row_custom_y),
                force_standard_box=True
            )

            self.sig_progress.emit(30)

            self.sig_log.emit(f"  [3/4] 启动 30FPS 特效物理引擎...", "#cdd6f4")
            concat_path = os.path.join(temp_dir, "subs_concat.txt").replace("\\", "/")
            blank_path = os.path.join(temp_dir, "blank.png").replace("\\", "/")
            
            try: proj_w, proj_h = get_video_dimensions(v_path)
            except: proj_w, proj_h = 1080, 1920
            
            v_dur = get_exact_duration(v_path)
            a_dur = get_exact_duration(a_path) if a_path else 0
            total_dur = max(max(v_dur, a_dur), 5.0)

            with sync_playwright() as p:
                b_path = get_browser_path()
                browser = p.chromium.launch(headless=True, executable_path=b_path) if b_path else p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": proj_w, "height": proj_h}, device_scale_factor=1)
                page.set_content("<html><body style='background:transparent;'></body></html>")
                page.screenshot(path=blank_path, omit_background=True)

                with open(concat_path, "w", encoding="utf-8") as f_concat:
                    current_time = 0.0; frame_idx = 0; frame_step = 1.0 / 30.0
                    
                    while current_time < total_dur:
                        active_subs = [s for s in subs_data if float(s.get('start', 0)) <= current_time <= float(s.get('end', 1))]
                        if not active_subs:
                            future_starts = [float(s.get('start', 0)) for s in subs_data if float(s.get('start', 0)) > current_time]
                            if future_starts:
                                next_start = min(future_starts)
                                f_concat.write(f"file '{blank_path}'\nduration {(next_start - current_time):.3f}\n")
                                current_time = next_start
                            else:
                                gap = total_dur - current_time
                                if gap > 0: f_concat.write(f"file '{blank_path}'\nduration {gap:.3f}\n")
                                current_time = total_dur
                            continue
                        
                        html_subs = ""
                        for s in active_subs:
                            px = s.get("pos_x", 0.0); py = s.get("pos_y", 25.0)
                            base_css = f"position: absolute; left: calc(50% + {px}%); top: calc(50% + {py}%); transform: translate(-50%, -50%); z-index: 10; width: max-content; max-width: 92%;"
                            sub_html = render_subtitle_html(s, current_time, proj_w)
                            html_subs += f"<div style='{base_css}'>{sub_html}</div>\n"
                        
                        # 👑 全局抗锯齿平滑渲染参数
                        html_content = f"<!DOCTYPE html><html><head><style>html, body {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; background: transparent; display: flex; justify-content: center; align-items: center; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }} #scale-wrapper {{ width: 100vw; height: 100vh; position: absolute; left: 0; top: 0; filter: drop-shadow(0px 0px 0px transparent); }}</style></head><body><div id='scale-wrapper'>{html_subs}</div></body></html>"
                        page.set_content(html_content)
                        frame_path = os.path.join(temp_dir, f"f_{frame_idx}.png").replace("\\", "/")
                        page.screenshot(path=frame_path, omit_background=True)
                        f_concat.write(f"file '{frame_path}'\nduration {frame_step:.3f}\n")
                        current_time += frame_step; frame_idx += 1
                        
            self.sig_progress.emit(70)

            self.sig_log.emit(f"  [4/4] 最终封装: 根据 {a_mode.split(' ')[0]} 压制中...", "#cdd6f4")
            
            v_loop_path = os.path.join(temp_dir, "v_loop.txt").replace("\\", "/")
            with open(v_loop_path, 'w', encoding='utf-8') as f:
                loop_count = int(total_dur / max(0.1, v_dur)) + 1
                for _ in range(loop_count): f.write(f"file '{v_path.replace('\\', '/')}'\n")

            has_audio_file = bool(a_path and os.path.exists(a_path))
            render_profile = get_render_profile()
            encoder_label = render_profile.get("encoder_label") or render_profile.get("encoder", "CPU x264")
            video_args = build_video_encoder_args(render_profile, quality="batch")
            self.sig_log.emit(f"  ⚙️ 渲染配置: {encoder_label}", "#89b4fa")
            
            args = ["-y", "-f", "concat", "-safe", "0", "-i", v_loop_path, "-f", "concat", "-safe", "0", "-i", concat_path]
            if has_audio_file: args.extend(["-i", a_path])
            
            vf = f"[0:v]scale={proj_w}:{proj_h}:force_original_aspect_ratio=increase,crop={proj_w}:{proj_h},format=yuv420p[bg];[bg][1:v]overlay=0:0:shortest=1,format=yuv420p[outv]"
            
            if "混合" in a_mode and has_audio_file:
                af = "[0:a][2:a]amix=inputs=2:duration=longest[outa]"
                args.extend(["-filter_complex", f"{vf};{af}", "-map", "[outv]", "-map", "[outa]"] + video_args + ["-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
            elif "保留" in a_mode:
                args.extend(["-filter_complex", vf, "-map", "[outv]", "-map", "0:a?"] + video_args + ["-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
            else:
                if has_audio_file:
                    args.extend(["-filter_complex", vf, "-map", "[outv]", "-map", "2:a:0"] + video_args + ["-c:a", "aac", "-b:a", "192k", "-t", str(total_dur), out_path])
                else:
                    args.extend(["-filter_complex", vf, "-map", "[outv]"] + video_args + ["-an", "-t", str(total_dur), out_path])
            
            proc = subprocess.run([get_ffmpeg_cmd()] + args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=0x08000000 if os.name == 'nt' else 0)
            if proc.returncode != 0: raise Exception(f"FFmpeg 渲染失败!")
            
            self.sig_log.emit(f"✅ {os.path.basename(v_path)} 交付成功！", "#a6e3a1")
            self.sig_progress.emit(100)
            self.sig_table_row_status.emit(t_idx, "✅ 完成", "#a6e3a1")

        except Exception as e:
            self.sig_log.emit(f"❌ 任务失败: {str(e)}", "#f38ba8")
            self.sig_table_row_status.emit(task["idx"], "❌ 失败", "#f38ba8")
        finally:
            try: shutil.rmtree(temp_dir)
            except: pass
            self.sig_file_done.emit()

    def _load_nlp_dict(self):
        dict_path = os.path.join(os.getcwd(), "nlp_dictionary.txt")
        default_words = [
            "a", "an", "the", "to", "in", "on", "at", "of", "for", "with", "from", "by", "about", 
            "as", "into", "like", "through", "after", "over", "between", "out", "against", "during", 
            "without", "before", "under", "around", "among", "and", "but", "or", "so", "because",
            "my", "your", "his", "her", "its", "our", "their", "this", "that", "these", "those",
            "is", "am", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", 
            "does", "did", "will", "would", "shall", "should", "can", "could", "may", "might", "must",
            "very", "too", "not"
        ]
        
        if not os.path.exists(dict_path):
            try:
                with open(dict_path, 'w', encoding='utf-8') as f:
                    for w in default_words: f.write(f"{w}\n")
            except: pass
            return set(default_words)
            
        custom_words = set()
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean_line = line.split('#')[0].strip().lower() 
                    if clean_line: custom_words.add(clean_line)
            return custom_words if custom_words else set(default_words)
        except: return set(default_words)

    def _tokenize_user_text_for_alignment(self, raw_text):
        return tokenize_display_text(raw_text)

    def _align_user_text_to_ai_words(self, ai_words, raw_text):
        return align_reference_text_to_timestamps(ai_words, raw_text)

    def process_words(self, words, mode, timing_mode=None):
        words = normalize_word_timestamps(words)
        NON_END_WORDS = self._load_nlp_dict()
        subs = []; curr = {"words": []}; puncts = ['.', '!', '?', ',', '，', '。', '！', '？']
        timing_mode = timing_mode or "J Cut (字幕稍后收尾)"
        sound_aligned = "对齐声音" in timing_mode
        
        for i, w in enumerate(words):
            if not curr["words"]: curr["start"] = w["start"]
            curr["words"].append({"text": w["word"], "start": w["start"], "end": w["end"]})
            curr["end"] = w["end"]
            
            clean_w = re.sub(r'[^a-zA-Z0-9\']', '', w["word"]).lower()
            has_punct = any(w["word"].endswith(p) for p in puncts)
            is_last_word = (i == len(words) - 1)
            next_start = words[i + 1]["start"] if i + 1 < len(words) else 9999.0
            silence_gap = next_start - curr["end"]
            curr_dur = curr["end"] - curr["start"]
            
            if "单字" in mode: is_break = True
            elif sound_aligned:
                is_break = (
                    (silence_gap > 0.55 and curr_dur >= 0.25) or
                    (silence_gap > 0.34 and len(curr["words"]) >= 2) or
                    (has_punct and silence_gap > 0.18 and curr_dur > 0.75) or
                    curr_dur >= 3.8 or
                    len(curr["words"]) >= 13
                )
            elif "3-5字" in mode:
                if has_punct or len(curr["words"]) >= 4:
                    if clean_w in NON_END_WORDS and not is_last_word and len(curr["words"]) < 8: is_break = False
                    else: is_break = True
                else: is_break = False
            else: 
                if has_punct or len(curr["words"]) >= 10:
                    if clean_w in NON_END_WORDS and not is_last_word and len(curr["words"]) < 15: is_break = False
                    else: is_break = True
                else: is_break = False
                    
            if is_break: 
                if sound_aligned and len(curr["words"]) >= 6:
                    mid = len(curr["words"]) // 2
                    curr["words"][mid]["text"] = "\n" + curr["words"][mid]["text"].lstrip()
                curr["text"] = " ".join([x["text"] for x in curr["words"]])
                curr["text"] = curr["text"].replace(" \n", "\n").replace("\n ", "\n")
                curr["pos_x"] = 0.0; curr["pos_y"] = 25.0; curr["track"] = 1
                subs.append(curr); curr = {"words": []}
                
        if curr["words"]: 
            if sound_aligned and len(curr["words"]) >= 6:
                mid = len(curr["words"]) // 2
                curr["words"][mid]["text"] = "\n" + curr["words"][mid]["text"].lstrip()
            curr["text"] = " ".join([x["text"] for x in curr["words"]])
            curr["text"] = curr["text"].replace(" \n", "\n").replace("\n ", "\n")
            curr["pos_x"] = 0.0; curr["pos_y"] = 25.0; curr["track"] = 1
            subs.append(curr)
            
        return self._apply_timing_mode(subs, timing_mode)

    def _apply_timing_mode(self, subs, timing_mode):
        if not subs:
            return subs
        if "对齐声音" in timing_mode:
            start_pad, end_pad = 0.0, 0.03
        elif "L Cut" in timing_mode:
            start_pad, end_pad = 0.12, 0.04
        else:
            start_pad, end_pad = 0.02, 0.16

        original_starts = [float(s.get("start", 0.0)) for s in subs]
        for i, s in enumerate(subs):
            raw_start = float(s.get("start", 0.0))
            raw_end = float(s.get("end", raw_start + 0.3))
            new_start = max(0.0, raw_start - start_pad)
            new_end = raw_end + end_pad
            if i + 1 < len(subs):
                next_start = max(0.0, original_starts[i + 1] - start_pad)
                new_end = min(new_end, max(new_start + 0.05, next_start - 0.01))
            if new_end <= new_start:
                new_end = new_start + 0.05
            s["start"] = new_start
            s["end"] = new_end
        return subs

    @pyqtSlot()
    def _on_file_done(self):
        self.current_idx += 1
        self.process_next()

    @pyqtSlot()
    def _on_all_done(self):
        self.is_running = False
        btn_start_table = self.findChild(QPushButton, "🚀 开始批量流水线")
        if btn_start_table: btn_start_table.setEnabled(True)
        self.log_console.append("🎉 所有矩阵任务圆满完成！")
        QMessageBox.information(self, "批量完成", "恭喜，矩阵批量生成完毕！")
