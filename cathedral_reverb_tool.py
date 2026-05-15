import html
import json
import math
import os
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    MULTIMEDIA_AVAILABLE = True
except Exception:
    QAudioOutput = None
    QMediaPlayer = None
    MULTIMEDIA_AVAILABLE = False
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QMessageBox, QFrame, QLineEdit, QComboBox, QDoubleSpinBox, QProgressBar,
    QFileDialog, QSlider, QSpinBox, QScrollArea, QStackedWidget
)

from core import get_ffmpeg_cmd


SETTINGS_FILE = os.path.join(os.getcwd(), "settings.json")
TOOL_SETTINGS_KEY = "cathedral_reverb_tool"
SUPPORTED_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}


def _load_app_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_app_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class CathedralReverbTool(QWidget):
    sig_status = pyqtSignal(str)
    sig_log = pyqtSignal(str, str)
    sig_progress = pyqtSignal(int)
    sig_finished = pyqtSignal(str, bool)
    sig_preview_ready = pyqtSignal(str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_files = []
        self.is_running = False
        self.cancel_requested = False
        self.current_process = None
        self.preview_rendering = False
        self.preview_player = None
        self.preview_audio_output = None

        self.init_ui()
        self.load_settings()

        self.sig_status.connect(self.lbl_status.setText)
        self.sig_log.connect(self.append_log)
        self.sig_progress.connect(self.progress.setValue)
        self.sig_finished.connect(self.on_finished)
        self.sig_preview_ready.connect(self.on_preview_ready)

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #0f1117; color: #e7edf3; font-family: 'Segoe UI', Arial; }
            QScrollArea { background: transparent; border: none; }
            QFrame#panel { background-color: #151922; border: 1px solid #252c38; border-radius: 10px; }
            QFrame#card { background-color: #181e29; border: 1px solid #2d3748; border-radius: 8px; }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #10141c; color: #e7edf3; border: 1px solid #2d3748;
                border-radius: 7px; padding: 8px;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color: #7dd3fc; }
            QSpinBox, QDoubleSpinBox {
                background-color: #f4f8fb; color: #111827; border: 1px solid #b9c6d3;
                border-radius: 7px; padding: 6px; font-weight: 900;
            }
            QSlider::groove:horizontal { height: 7px; background: #2d3748; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #7dd3fc; border-radius: 3px; }
            QSlider::handle:horizontal { width: 18px; height: 18px; margin: -6px 0; background: #f8d98b; border-radius: 9px; }
            QProgressBar { border: 1px solid #2d3748; border-radius: 6px; text-align: center; color: #e7edf3; height: 22px; background: #10141c; }
            QProgressBar::chunk { background-color: #8ee59c; border-radius: 5px; }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFixedWidth(460)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        settings_panel = QFrame()
        settings_panel.setObjectName("panel")
        left = QVBoxLayout(settings_panel)
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(12)

        title = QLabel("DaVinci Cathedral")
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #f2f6fb; border: none; letter-spacing: 0px;")
        subtitle = QLabel("大教堂混响 · 批量音频空间生成")
        subtitle.setStyleSheet("font-size: 13px; color: #9aa7b8; border: none; margin-bottom: 4px;")
        left.addWidget(title)
        left.addWidget(subtitle)

        self.lbl_status = QLabel("准备就绪")
        self.lbl_status.setStyleSheet("color: #f8d98b; font-weight: 900; border: none;")
        self.progress = QProgressBar()
        self.progress.setValue(0)

        quick_card, quick_layout = self._card("快捷操作")
        quick_layout.addWidget(self.lbl_status)
        quick_layout.addWidget(self.progress)
        action_row = QHBoxLayout()
        self.btn_preview = self._button("预览试听", "#93c5fd", dark_text=True)
        self.btn_preview.setFixedHeight(42)
        self.btn_preview.clicked.connect(lambda checked=False: self.preview_first_file())
        self.btn_start = self._button("开始批量渲染", "#8ee59c", dark_text=True)
        self.btn_start.setFixedHeight(42)
        self.btn_start.clicked.connect(lambda checked=False: self.start_processing())
        self.btn_cancel = self._button("停止", "#fca5a5", dark_text=True)
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda checked=False: self.cancel_processing())
        action_row.addWidget(self.btn_preview)
        action_row.addWidget(self.btn_start, stretch=2)
        action_row.addWidget(self.btn_cancel)
        quick_layout.addLayout(action_row)
        left.addWidget(quick_card)

        nav_row = QHBoxLayout()
        self.section_buttons = []
        for idx, text in enumerate(["来源", "混响", "速度", "输出"]):
            btn = self._button(text, "#253145")
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda checked=False, i=idx: self.switch_section(i))
            nav_row.addWidget(btn)
            self.section_buttons.append(btn)
        left.addLayout(nav_row)

        self.section_stack = QStackedWidget()

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_card, source_card_layout = self._card("音频来源")
        self.input_dir_input = QLineEdit()
        self.input_dir_input.setPlaceholderText("可选择文件夹，也可选择多个音频文件")
        source_card_layout.addWidget(self.input_dir_input)
        source_buttons = QHBoxLayout()
        btn_input = self._button("选择文件夹", "#5c8a6b")
        btn_input.clicked.connect(lambda checked=False: self.select_input_dir())
        btn_files = self._button("选择多个文件", "#4a789c")
        btn_files.clicked.connect(lambda checked=False: self.select_input_files())
        btn_clear = self._button("清空文件", "#5b6170")
        btn_clear.clicked.connect(lambda checked=False: self.clear_selected_files())
        source_buttons.addWidget(btn_input)
        source_buttons.addWidget(btn_files)
        source_buttons.addWidget(btn_clear)
        source_card_layout.addLayout(source_buttons)
        self.lbl_source_summary = QLabel("未选择音频")
        self.lbl_source_summary.setWordWrap(True)
        self.lbl_source_summary.setStyleSheet("color: #cbd5e1; border: none; font-weight: 700;")
        source_card_layout.addWidget(self.lbl_source_summary)
        source_layout.addWidget(source_card)
        source_layout.addStretch()
        self.section_stack.addWidget(source_page)

        reverb_page = QWidget()
        reverb_layout = QVBoxLayout(reverb_page)
        reverb_layout.setContentsMargins(0, 0, 0, 0)
        reverb_card, reverb_card_layout = self._card("大教堂混响参数")
        reverb_card_layout.addLayout(self._int_slider_row("预延迟", "ms", 0, 200, 40, "pre_delay_spin", "pre_delay_slider"))
        reverb_card_layout.addLayout(self._float_slider_row("混响尺寸", "", 0.0, 0.99, 0.40, "room_spin", "room_slider", step=0.01))
        reverb_card_layout.addLayout(self._int_slider_row("早期反射低切", "Hz", 20, 1000, 300, "low_cut_spin", "low_cut_slider", step=10))
        reverb_card_layout.addLayout(self._int_slider_row("早期反射高切", "Hz", 5000, 20000, 10000, "high_cut_spin", "high_cut_slider", step=100))
        reverb_card_layout.addLayout(self._float_slider_row("干/湿比例", "", 0.0, 1.0, 0.10, "wet_spin", "wet_slider", step=0.01))
        reverb_layout.addWidget(reverb_card)
        reverb_layout.addStretch()
        self.section_stack.addWidget(reverb_page)

        motion_page = QWidget()
        motion_layout = QVBoxLayout(motion_page)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        motion_card, motion_card_layout = self._card("速度与音调")
        motion_card_layout.addLayout(self._float_slider_row("速度", "x", 0.50, 2.00, 1.00, "speed_spin", "speed_slider", step=0.01))
        motion_card_layout.addLayout(self._float_slider_row("音调", "半音", -12.0, 12.0, 0.0, "pitch_spin", "pitch_slider", step=0.5, scale=10))
        motion_layout.addWidget(motion_card)
        motion_layout.addStretch()
        self.section_stack.addWidget(motion_page)

        output_page = QWidget()
        output_layout = QVBoxLayout(output_page)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_card, output_card_layout = self._card("输出")
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("默认 MyWorkspace/大教堂混响输出")
        output_card_layout.addWidget(self.output_dir_input)
        output_row = QHBoxLayout()
        btn_output = self._button("选择输出目录", "#5c8a6b")
        btn_output.clicked.connect(lambda checked=False: self.select_output_dir())
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItem("WAV 无损", "wav")
        self.output_mode_combo.addItem("MP3 192k", "mp3")
        self.output_mode_combo.addItem("MP4 / Canva 音频", "mp4")
        self.output_mode_combo.addItem("WAV + MP3 + MP4", "all")
        self.output_mode_combo.addItem("打包 ZIP (WAV+MP3+MP4)", "zip")
        output_row.addWidget(btn_output)
        output_row.addWidget(self.output_mode_combo, stretch=1)
        output_card_layout.addLayout(output_row)
        output_layout.addWidget(output_card)
        output_layout.addStretch()
        self.section_stack.addWidget(output_page)

        left.addWidget(self.section_stack, stretch=1)
        self.switch_section(0)

        settings_scroll.setWidget(settings_panel)

        log_panel = QFrame()
        log_panel.setObjectName("panel")
        right = QVBoxLayout(log_panel)
        right.setContentsMargins(18, 18, 18, 18)
        right.setSpacing(12)
        log_title = QLabel("处理日志")
        log_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #8ee59c; border: none;")
        right.addWidget(log_title)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #10141c; color: #cbd5e1; border: 1px solid #2d3748; border-radius: 8px; font-family: Consolas; font-size: 13px;")
        right.addWidget(self.log_console, stretch=1)

        root.addWidget(settings_scroll)
        root.addWidget(log_panel, stretch=1)

    def _card(self, title):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setStyleSheet("color: #93c5fd; font-size: 15px; font-weight: 900; border: none;")
        layout.addWidget(label)
        return card, layout

    def _button(self, text, color, dark_text=False):
        btn = QPushButton(text)
        text_color = "#10131a" if dark_text else "#f2f6fb"
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: {text_color}; border: none; "
            "font-weight: 900; padding: 8px 10px; border-radius: 7px; }}"
            "QPushButton:hover:enabled { background-color: #7dd3fc; }"
            "QPushButton:checked { background-color: #8ee59c; color: #10131a; }"
            "QPushButton:disabled { background-color: #293241; color: #758195; }"
        )
        return btn

    def switch_section(self, index):
        if hasattr(self, "section_stack"):
            self.section_stack.setCurrentIndex(index)
        for i, btn in enumerate(getattr(self, "section_buttons", [])):
            btn.setChecked(i == index)

    def _int_slider_row(self, label, unit, minimum, maximum, default, spin_attr, slider_attr, step=1):
        row = QVBoxLayout()
        top = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #d8e7dc; font-weight: 800; border: none;")
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(default)
        spin.setFixedWidth(110)
        if unit:
            spin.setSuffix(f" {unit}")
        top.addWidget(lbl)
        top.addStretch()
        top.addWidget(spin)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setSingleStep(step)
        slider.setPageStep(step)
        slider.setValue(default)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        setattr(self, spin_attr, spin)
        setattr(self, slider_attr, slider)
        row.addLayout(top)
        row.addWidget(slider)
        return row

    def _float_slider_row(self, label, unit, minimum, maximum, default, spin_attr, slider_attr, step=0.01, scale=100):
        row = QVBoxLayout()
        top = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #d8e7dc; font-weight: 800; border: none;")
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2 if step < 0.1 else 1)
        spin.setValue(default)
        spin.setFixedWidth(110)
        if unit:
            spin.setSuffix(f" {unit}")
        top.addWidget(lbl)
        top.addStretch()
        top.addWidget(spin)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(minimum * scale), int(maximum * scale))
        slider.setSingleStep(max(1, int(step * scale)))
        slider.setValue(int(default * scale))
        slider.valueChanged.connect(lambda value: spin.setValue(value / scale))
        spin.valueChanged.connect(lambda value: slider.setValue(int(round(value * scale))))
        setattr(self, spin_attr, spin)
        setattr(self, slider_attr, slider)
        row.addLayout(top)
        row.addWidget(slider)
        return row

    def load_settings(self):
        data = _load_app_settings().get(TOOL_SETTINGS_KEY, {})
        default_output = os.path.join(os.getcwd(), "MyWorkspace", "大教堂混响输出")
        self.input_dir_input.setText(data.get("input_dir", ""))
        self.output_dir_input.setText(data.get("output_dir", default_output))
        self.selected_files = [p for p in data.get("input_files", []) if p and os.path.exists(p)]
        self.pre_delay_spin.setValue(int(data.get("pre_delay", 40)))
        self.room_spin.setValue(float(data.get("room", 0.40)))
        self.low_cut_spin.setValue(int(data.get("low_cut", 300)))
        self.high_cut_spin.setValue(int(data.get("high_cut", 10000)))
        self.wet_spin.setValue(float(data.get("wet", 0.10)))
        self.speed_spin.setValue(float(data.get("speed", 1.0)))
        self.pitch_spin.setValue(float(data.get("pitch_semitones", 0.0)))
        output_mode = data.get("output_mode", "all")
        idx = self.output_mode_combo.findData(output_mode)
        self.output_mode_combo.setCurrentIndex(idx if idx >= 0 else 3)
        self.refresh_source_summary()

    def save_settings(self):
        all_settings = _load_app_settings()
        all_settings[TOOL_SETTINGS_KEY] = self.collect_settings()
        _save_app_settings(all_settings)

    def collect_settings(self):
        return {
            "input_dir": self.input_dir_input.text().strip(),
            "input_files": list(self.selected_files),
            "output_dir": self.output_dir_input.text().strip(),
            "output_mode": self.output_mode_combo.currentData(),
            "output_mode_label": self.output_mode_combo.currentText(),
            "pre_delay": self.pre_delay_spin.value(),
            "room": self.room_spin.value(),
            "low_cut": self.low_cut_spin.value(),
            "high_cut": self.high_cut_spin.value(),
            "wet": self.wet_spin.value(),
            "speed": self.speed_spin.value(),
            "pitch_semitones": self.pitch_spin.value(),
        }

    def select_input_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输入音频文件夹", self.input_dir_input.text().strip() or os.getcwd())
        if path:
            self.input_dir_input.setText(path)
            self.save_settings()
            self.refresh_source_summary()

    def select_input_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择多个音频文件",
            self.input_dir_input.text().strip() or os.getcwd(),
            "Audio Files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.wma);;All Files (*.*)"
        )
        if files:
            seen = set()
            merged = []
            for path in self.selected_files + files:
                key = os.path.normcase(os.path.abspath(path))
                if key not in seen and Path(path).suffix.lower() in SUPPORTED_AUDIO_EXTS and os.path.exists(path):
                    seen.add(key)
                    merged.append(path)
            self.selected_files = merged
            self.save_settings()
            self.refresh_source_summary()

    def clear_selected_files(self):
        self.selected_files = []
        self.save_settings()
        self.refresh_source_summary()

    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择大教堂混响输出文件夹", self.output_dir_input.text().strip() or os.getcwd())
        if path:
            self.output_dir_input.setText(path)
            self.save_settings()

    def refresh_source_summary(self):
        config = self.collect_settings()
        files = self._audio_files_from_config(config, limit=501)
        count_text = "500+" if len(files) > 500 else str(len(files))
        parts = []
        if config["input_dir"]:
            parts.append(f"文件夹: {config['input_dir']}")
        if self.selected_files:
            parts.append(f"多选文件: {len(self.selected_files)} 个")
        parts.append(f"可处理音频: {count_text} 个")
        self.lbl_source_summary.setText(" | ".join(parts))

    def _ensure_preview_player(self):
        if not MULTIMEDIA_AVAILABLE:
            return False
        if self.preview_player is not None:
            return True
        try:
            self.preview_player = QMediaPlayer(self)
            self.preview_audio_output = QAudioOutput(self)
            self.preview_audio_output.setVolume(0.9)
            self.preview_player.setAudioOutput(self.preview_audio_output)
            self.preview_player.playbackStateChanged.connect(self.on_preview_state_changed)
            return True
        except Exception as exc:
            self.sig_log.emit(f"预览播放器初始化失败: {exc}", "#f38ba8")
            self.preview_player = None
            self.preview_audio_output = None
            return False

    def preview_first_file(self):
        if self.preview_player and self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.stop()
            self.btn_preview.setText("预览试听")
            return
        if self.is_running or self.preview_rendering:
            return
        if not self._ensure_preview_player():
            return QMessageBox.warning(self, "提示", "当前运行环境缺少 QtMultimedia，音频工具可以批量处理，但暂时不能直接试听预览。重新打包时我已经补了对应依赖。")

        config = self.collect_settings()
        files = self._audio_files_from_config(config)
        if not files:
            return QMessageBox.warning(self, "提示", "请先选择文件夹或多个音频文件。")

        self.save_settings()
        if self.preview_player:
            self.preview_player.stop()
            self.preview_player.setSource(QUrl())
        self.preview_rendering = True
        self.btn_preview.setEnabled(False)
        self.sig_status.emit(f"正在生成预览: {files[0].name}")
        threading.Thread(target=self._preview_worker, args=(config, files[0]), daemon=True).start()

    def _preview_worker(self, config, source):
        try:
            preview_dir = Path(tempfile.gettempdir()) / "subtitle_composer_audio_preview"
            preview_dir.mkdir(parents=True, exist_ok=True)
            target = preview_dir / "cathedral_reverb_preview.wav"
            self._remove_partial_file(target)
            ok, err = self._run_ffmpeg(get_ffmpeg_cmd(), source, target, config, limit_seconds=15)
            if ok:
                self.sig_preview_ready.emit(str(target), True, f"正在预览: {source.name}")
            else:
                self.sig_preview_ready.emit("", False, self._tail_error(err) or "预览生成失败。")
        except Exception as exc:
            self.sig_preview_ready.emit("", False, f"预览失败: {exc}")

    def on_preview_ready(self, path, success, message):
        self.preview_rendering = False
        self.btn_preview.setEnabled(True)
        if not success:
            self.btn_preview.setText("预览试听")
            self.sig_status.emit("预览生成失败")
            self.sig_log.emit(message, "#f38ba8")
            return

        if not self._ensure_preview_player():
            self.btn_preview.setText("预览试听")
            self.sig_status.emit("预览已生成，但当前环境不能直接播放")
            self.sig_log.emit(f"预览文件: {path}", "#89b4fa")
            return

        self.preview_player.stop()
        self.preview_player.setSource(QUrl.fromLocalFile(path))
        self.preview_player.play()
        self.btn_preview.setText("停止预览")
        self.sig_status.emit(message)
        self.sig_log.emit(message, "#89b4fa")

    def on_preview_state_changed(self, state):
        if QMediaPlayer and state == QMediaPlayer.PlaybackState.StoppedState and not self.preview_rendering:
            self.btn_preview.setText("预览试听")

    def start_processing(self):
        if self.is_running:
            return

        config = self.collect_settings()
        files = self._audio_files_from_config(config)
        if not files:
            return QMessageBox.warning(self, "提示", "请先选择文件夹或多个音频文件。")
        if not config["output_dir"]:
            return QMessageBox.warning(self, "提示", "请先选择输出文件夹。")

        self.save_settings()
        self.log_console.clear()
        self.progress.setValue(0)
        if self.preview_player:
            self.preview_player.stop()
        self.cancel_requested = False
        self.is_running = True
        self.btn_preview.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.sig_status.emit("正在准备渲染...")

        threading.Thread(target=self._process_worker, args=(config, files), daemon=True).start()

    def cancel_processing(self):
        self.cancel_requested = True
        self.sig_status.emit("正在停止...")
        process = self.current_process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _process_worker(self, config, files):
        try:
            output_dir = Path(config["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            output_mode = config["output_mode"]
            formats = ["wav", "mp3", "mp4"] if output_mode in {"all", "zip"} else [output_mode]
            total_steps = len(files) * len(formats)
            done_steps = 0
            success_count = 0
            generated_for_zip = []
            ffmpeg = get_ffmpeg_cmd()

            self.sig_log.emit(f"找到 {len(files)} 个音频文件，输出模式: {config.get('output_mode_label', output_mode)}。", "#a6e3a1")
            work_context = tempfile.TemporaryDirectory(prefix="cathedral_reverb_") if output_mode == "zip" else None

            try:
                base_output_dir = Path(work_context.name) if work_context else output_dir
                for index, source in enumerate(files, start=1):
                    if self.cancel_requested:
                        self.sig_log.emit("任务已停止。", "#f9e2af")
                        break

                    file_ok = True
                    for fmt in formats:
                        if self.cancel_requested:
                            break

                        target = self._unique_output_path(base_output_dir, source, fmt)
                        self.sig_status.emit(f"渲染中 ({index}/{len(files)}): {source.name} -> {fmt.upper()}")
                        self.sig_log.emit(f"[{index}/{len(files)}] {source.name} -> {target.name}", "#cdd6f4")

                        ok, err = self._run_ffmpeg(ffmpeg, source, target, config)
                        if ok:
                            generated_for_zip.append(target)
                            self.sig_log.emit(f"完成: {target.name}", "#a6e3a1")
                        elif self.cancel_requested:
                            self._remove_partial_file(target)
                            file_ok = False
                            self.sig_log.emit(f"已停止: {source.name}", "#f9e2af")
                        else:
                            self._remove_partial_file(target)
                            file_ok = False
                            self.sig_log.emit(f"失败: {source.name}", "#f38ba8")
                            if err:
                                self.sig_log.emit(self._tail_error(err), "#6c7086")

                        done_steps += 1
                        self.sig_progress.emit(int(done_steps * 100 / max(total_steps, 1)))

                    if file_ok:
                        success_count += 1

                if output_mode == "zip" and generated_for_zip and not self.cancel_requested:
                    zip_path = self._unique_zip_path(output_dir)
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for path in generated_for_zip:
                            zip_file.write(path, path.name)
                    self.sig_log.emit(f"ZIP 已生成: {zip_path.name}", "#a6e3a1")
            finally:
                if work_context:
                    work_context.cleanup()

            if self.cancel_requested:
                self.sig_finished.emit(f"已停止，完成 {success_count}/{len(files)} 个。", False)
            else:
                self.sig_finished.emit(f"渲染完成，成功 {success_count}/{len(files)} 个。", True)
        except Exception as exc:
            self.sig_finished.emit(f"渲染失败: {exc}", False)

    def _audio_files_from_config(self, config, limit=None):
        files = []
        seen = set()

        for path in config.get("input_files", []) or []:
            candidate = Path(path)
            key = os.path.normcase(os.path.abspath(candidate))
            if key not in seen and candidate.is_file() and candidate.suffix.lower() in SUPPORTED_AUDIO_EXTS:
                seen.add(key)
                files.append(candidate)
                if limit and len(files) >= limit:
                    return files

        input_dir = config.get("input_dir", "")
        if input_dir and Path(input_dir).is_dir():
            candidates = Path(input_dir).iterdir()
            if limit is None:
                candidates = sorted(candidates)
            for candidate in candidates:
                key = os.path.normcase(os.path.abspath(candidate))
                if key not in seen and candidate.is_file() and candidate.suffix.lower() in SUPPORTED_AUDIO_EXTS:
                    seen.add(key)
                    files.append(candidate)
                    if limit and len(files) >= limit:
                        return files

        return files

    def _run_ffmpeg(self, ffmpeg, source, target, config, limit_seconds=None):
        filter_complex = self._build_filter_complex(config)
        args = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
        ]
        if limit_seconds:
            args.extend(["-t", str(limit_seconds)])
        args.extend(["-filter_complex", filter_complex, "-map", "[out]", "-vn"])
        args.extend(self._codec_args(target.suffix.lower()))
        args.append(str(target))

        flags = 0x08000000 if os.name == "nt" else 0
        try:
            self.current_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=flags,
            )
            _, stderr = self.current_process.communicate()
            return self.current_process.returncode == 0 and target.exists(), stderr or ""
        finally:
            self.current_process = None

    def _build_filter_complex(self, config):
        pre_delay = max(0, min(200, int(config["pre_delay"])))
        room = max(0.0, min(0.99, float(config["room"])))
        low_cut = max(20, min(1000, int(config["low_cut"])))
        high_cut = max(5000, min(20000, int(config["high_cut"])))
        wet = max(0.0, min(1.0, float(config["wet"])))
        dry = max(0.0, 1.0 - wet)
        speed = max(0.5, min(2.0, float(config.get("speed", 1.0))))
        pitch = math.pow(2.0, float(config.get("pitch_semitones", 0.0)) / 12.0)
        stretch_filter = ""
        if abs(speed - 1.0) > 0.001 or abs(pitch - 1.0) > 0.001:
            stretch_filter = f"rubberband=tempo={speed:.4f}:pitch={pitch:.4f},"

        d1 = int(80 + room * 220)
        d2 = int(150 + room * 480)
        d3 = int(280 + room * 900)
        c1 = round(0.12 + room * 0.26, 2)
        c2 = round(0.08 + room * 0.20, 2)
        c3 = round(0.04 + room * 0.16, 2)

        return (
            f"[0:a]aformat=channel_layouts=stereo,{stretch_filter}asplit=2[drysrc][wetsrc];"
            f"[drysrc]volume={dry:.3f}[dry];"
            f"[wetsrc]adelay={pre_delay}|{pre_delay},"
            f"highpass=f={low_cut},lowpass=f={high_cut},"
            f"aecho=0.8:0.88:{d1}|{d2}|{d3}:{c1}|{c2}|{c3},"
            f"volume={wet:.3f}[wet];"
            "[dry][wet]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.98[out]"
        )

    def _codec_args(self, suffix):
        if suffix == ".wav":
            return ["-c:a", "pcm_s16le"]
        if suffix == ".mp3":
            return ["-c:a", "libmp3lame", "-b:a", "192k"]
        if suffix == ".mp4":
            return ["-c:a", "aac", "-b:a", "192k", "-f", "mp4"]
        return ["-c:a", "pcm_s16le"]

    def _unique_output_path(self, output_dir, source, fmt):
        suffix = f".{fmt}"
        base = output_dir / f"Reverb_{source.stem}{suffix}"
        if not base.exists():
            return base

        counter = 2
        while True:
            candidate = output_dir / f"Reverb_{source.stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _unique_zip_path(self, output_dir):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = output_dir / f"Cathedral_Reverb_{stamp}.zip"
        if not base.exists():
            return base

        counter = 2
        while True:
            candidate = output_dir / f"Cathedral_Reverb_{stamp}_{counter}.zip"
            if not candidate.exists():
                return candidate
            counter += 1

    def _remove_partial_file(self, path):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    def _tail_error(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[-4:])[:1200]

    def append_log(self, msg, color):
        safe = html.escape(msg).replace("\n", "<br>")
        self.log_console.append(f"<span style='color:{color}'>{safe}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def on_finished(self, message, success):
        self.is_running = False
        self.current_process = None
        self.btn_preview.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.sig_status.emit(message)
        self.sig_log.emit(message, "#a6e3a1" if success else "#f9e2af")


def create_cathedral_reverb_tool(parent=None):
    return CathedralReverbTool(parent)
