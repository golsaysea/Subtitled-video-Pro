import csv
import json
import os
import re
import threading
import wave

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QMessageBox, QFrame, QStackedWidget, QLineEdit, QComboBox, QCheckBox,
    QDoubleSpinBox, QProgressBar, QFileDialog, QScrollArea
)

from elevenlabs_web_tool import create_elevenlabs_tool
from elevenlabs_assist_tool import create_elevenlabs_assist_tool
from app_theme import apply_tinted_styles
from project_io import update_room_state


SETTINGS_FILE = os.path.join(os.getcwd(), "settings.json")
ELEVEN_ICON = r"C:\Users\User\Documents\tools\ElevenLabs_批量语音生成\icon.png"
ELEVEN_ASSIST_ICON = r"C:\Users\User\Documents\tools\ElevenLabs_辅助语音生成\icon.png"


def _safe_filename(text, fallback="voice"):
    clean = re.sub(r'[\r\n\t]+', " ", text or "").strip()
    clean = re.sub(r'[\\/:*?"<>|]', "_", clean)
    clean = re.sub(r"\s+", " ", clean)[:36].strip()
    return clean or fallback


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


class ElevenLabsTool(QWidget):
    sig_status = pyqtSignal(str)
    sig_log = pyqtSignal(str, str)
    sig_progress = pyqtSignal(int)
    sig_voices = pyqtSignal(object)
    sig_quota = pyqtSignal(object)
    sig_account_quota = pyqtSignal(str, object)
    sig_clear_text = pyqtSignal()
    sig_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.voice_items = []
        self.accounts = []
        self.current_account_key = ""
        self.is_running = False
        self.init_ui()
        self.load_settings()

        self.sig_status.connect(self.lbl_status.setText)
        self.sig_log.connect(self.append_log)
        self.sig_progress.connect(self.progress.setValue)
        self.sig_voices.connect(self.apply_voices)
        self.sig_quota.connect(self.apply_quota)
        self.sig_account_quota.connect(self.apply_account_quota)
        self.sig_clear_text.connect(self.text_editor.clear)
        self.sig_finished.connect(self.on_generation_finished)

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #11111b; color: #cdd6f4; }
            QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox {
                background-color: #11111b; color: #cdd6f4; border: 1px solid #313244;
                border-radius: 6px; padding: 7px;
            }
            QCheckBox { color: #cdd6f4; }
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFixedWidth(380)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        settings_panel = QFrame()
        settings_panel.setFixedWidth(360)
        settings_panel.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 10px; }")
        left = QVBoxLayout(settings_panel)
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(10)

        brand = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(44, 44)
        if os.path.exists(ELEVEN_ICON):
            icon.setPixmap(QPixmap(ELEVEN_ICON).scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title = QLabel("ElevenLabs 批量语音")
        title.setStyleSheet("font-size: 18px; font-weight: 900; color: #cdd6f4;")
        brand.addWidget(icon)
        brand.addWidget(title, stretch=1)
        left.addLayout(brand)

        left.addWidget(self._label("账号切换 / 管理"))
        self.account_combo = QComboBox()
        self.account_combo.setToolTip("选择当前使用的 ElevenLabs 账号")
        self.account_combo.currentIndexChanged.connect(self.on_account_changed)
        left.addWidget(self.account_combo)

        alias_row = QHBoxLayout()
        self.account_alias_input = QLineEdit()
        self.account_alias_input.setPlaceholderText("账号备注，例如 主号 / 客户A")
        btn_save_account = QPushButton("添加/更新")
        btn_save_account.clicked.connect(self.add_or_update_account)
        alias_row.addWidget(self.account_alias_input, stretch=1)
        alias_row.addWidget(btn_save_account)
        left.addLayout(alias_row)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("粘贴 ElevenLabs API Key")
        left.addWidget(self._label("API Key"))
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_input, stretch=1)
        btn_save_key = QPushButton("保存")
        btn_save_key.clicked.connect(self.save_settings)
        btn_check = QPushButton("查余额")
        btn_check.clicked.connect(self.check_quota)
        key_row.addWidget(btn_save_key)
        key_row.addWidget(btn_check)
        left.addLayout(key_row)

        account_action_row = QHBoxLayout()
        btn_delete_account = QPushButton("删除")
        btn_delete_account.clicked.connect(self.delete_current_account)
        btn_refresh_all = QPushButton("查全部余额")
        btn_refresh_all.clicked.connect(self.refresh_all_account_quotas)
        account_action_row.addWidget(btn_delete_account)
        account_action_row.addWidget(btn_refresh_all)
        left.addLayout(account_action_row)

        csv_action_row = QHBoxLayout()
        btn_import_csv = QPushButton("导入 CSV")
        btn_import_csv.clicked.connect(self.import_accounts_csv)
        btn_export_csv = QPushButton("导出 CSV")
        btn_export_csv.clicked.connect(self.export_accounts_csv)
        csv_action_row.addWidget(btn_import_csv)
        csv_action_row.addWidget(btn_export_csv)
        left.addLayout(csv_action_row)

        left.addWidget(self._label("Voice"))
        voice_row = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.addItem("请先刷新声音", "")
        self.btn_refresh_voice = QPushButton("刷新")
        self.btn_refresh_voice.clicked.connect(self.refresh_voices)
        voice_row.addWidget(self.voice_combo, stretch=1)
        voice_row.addWidget(self.btn_refresh_voice)
        left.addLayout(voice_row)
        self.voice_id_input = QLineEdit()
        self.voice_id_input.setPlaceholderText("可选: 直接粘贴 Voice ID，优先使用")
        left.addWidget(self.voice_id_input)

        left.addWidget(self._label("Model"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "eleven_multilingual_v2",
            "eleven_turbo_v2_5",
            "eleven_flash_v2_5",
            "eleven_v3"
        ])
        left.addWidget(self.model_combo)

        left.addWidget(self._label("Output Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("MP3 标准 128k", "mp3_44100_128")
        self.format_combo.addItem("MP3 高质 192k", "mp3_44100_192")
        self.format_combo.addItem("WAV 无损 PCM", "pcm_44100")
        self.format_combo.addItem("MP4 伪装格式 / Canva", "mp3_as_mp4")
        left.addWidget(self.format_combo)

        self.stability_spin = self._spin(0.50)
        self.similarity_spin = self._spin(0.75)
        self.style_spin = self._spin(0.00)
        self.boost_check = QCheckBox("Speaker Boost")
        self.boost_check.setChecked(True)
        left.addLayout(self._spin_row("Stability", self.stability_spin))
        left.addLayout(self._spin_row("Similarity", self.similarity_spin))
        left.addLayout(self._spin_row("Style", self.style_spin))
        left.addWidget(self.boost_check)

        left.addWidget(self._label("输出目录"))
        out_row = QHBoxLayout()
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("默认 MyWorkspace/ElevenLabs_语音")
        btn_out = QPushButton("选择")
        btn_out.clicked.connect(self.select_output_dir)
        out_row.addWidget(self.output_dir_input, stretch=1)
        out_row.addWidget(btn_out)
        left.addLayout(out_row)

        left.addWidget(self._label("分段方式"))
        self.split_combo = QComboBox()
        self.split_combo.addItems(["按空行分段", "每一行一段", "全文一段"])
        left.addWidget(self.split_combo)
        self.clear_after_check = QCheckBox("生成完成后清空文案")
        left.addWidget(self.clear_after_check)

        self.lbl_quota = QLabel("额度: --")
        self.lbl_quota.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #f9e2af;")
        left.addWidget(self.lbl_quota)
        left.addWidget(self.lbl_status)
        left.addStretch()

        content_panel = QFrame()
        content_panel.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 10px; }")
        right = QVBoxLayout(content_panel)
        right.setContentsMargins(16, 16, 16, 16)
        right.setSpacing(10)

        toolbar = QHBoxLayout()
        heading = QLabel("文案列表")
        heading.setStyleSheet("font-size: 18px; font-weight: 900; color: #cdd6f4;")
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self.clear_text)
        toolbar.addWidget(heading)
        toolbar.addStretch()
        toolbar.addWidget(btn_clear)
        right.addLayout(toolbar)

        self.text_editor = QTextEdit()
        self.text_editor.setPlaceholderText("输入要生成的文案。\n\n按空行分段时，每个段落会生成一个音频文件。\n每一行一段时，适合批量短句。")
        self.text_editor.textChanged.connect(self.update_stats)
        right.addWidget(self.text_editor, stretch=1)

        footer = QHBoxLayout()
        self.lbl_stats = QLabel("0 字 · 0 段")
        self.lbl_stats.setStyleSheet("color: #a6adc8; font-weight: bold;")
        self.btn_generate = QPushButton("开始批量生成")
        self.btn_generate.setFixedHeight(44)
        self.btn_generate.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-size: 15px; font-weight: bold; border-radius: 7px;")
        self.btn_generate.clicked.connect(self.start_generation)
        footer.addWidget(self.lbl_stats)
        footer.addStretch()
        footer.addWidget(self.btn_generate)
        right.addLayout(footer)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setStyleSheet("QProgressBar { border: 1px solid #313244; border-radius: 5px; text-align: center; color: white; } QProgressBar::chunk { background-color: #89b4fa; }")
        right.addWidget(self.progress)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(120)
        self.log_console.setStyleSheet("background-color: #11111b; color: #a6adc8; border: 1px solid #313244; border-radius: 8px; font-family: Consolas;")
        right.addWidget(self.log_console)

        settings_scroll.setWidget(settings_panel)
        root.addWidget(settings_scroll)
        root.addWidget(content_panel, stretch=1)
        self.update_stats()

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #89b4fa; font-weight: bold; margin-top: 4px;")
        return lbl

    def _spin(self, value):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.01)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    def _spin_row(self, label, spin):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(spin)
        return row

    def load_settings(self):
        data = _load_app_settings().get("elevenlabs_tool", {})
        self.accounts = list(data.get("accounts", []) or [])
        legacy_key = data.get("api_key", "")
        if legacy_key and not any(a.get("key") == legacy_key for a in self.accounts):
            self.accounts.append({"alias": "账号 1", "key": legacy_key})
        self.current_account_key = data.get("current_account_key") or legacy_key or (self.accounts[0].get("key", "") if self.accounts else "")
        self.render_account_combo()
        current_account = self.current_account()
        self.account_alias_input.setText(current_account.get("alias", "") if current_account else "")
        self.key_input.setText(self.current_account_key)
        self.voice_id_input.setText(data.get("voice_id", ""))
        self.model_combo.setCurrentText(data.get("model", "eleven_multilingual_v2"))
        self.output_dir_input.setText(data.get("output_dir", ""))
        self.stability_spin.setValue(float(data.get("stability", 0.5)))
        self.similarity_spin.setValue(float(data.get("similarity", 0.75)))
        self.style_spin.setValue(float(data.get("style", 0.0)))
        self.boost_check.setChecked(bool(data.get("speaker_boost", True)))
        self.clear_after_check.setChecked(bool(data.get("clear_after", False)))
        fmt = data.get("format", "mp3_44100_128")
        idx = self.format_combo.findData(fmt)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        split_idx = int(data.get("split_mode", 0))
        self.split_combo.setCurrentIndex(max(0, min(self.split_combo.count() - 1, split_idx)))

    def save_settings(self):
        self._sync_account_from_inputs()
        all_settings = _load_app_settings()
        all_settings["elevenlabs_tool"] = self.collect_settings()
        _save_app_settings(all_settings)
        self.sig_status.emit("设置已保存")

    def collect_settings(self):
        return {
            "api_key": self.key_input.text().strip(),
            "accounts": self.accounts,
            "current_account_key": self.api_key(),
            "voice_id": self.voice_id_input.text().strip(),
            "model": self.model_combo.currentText(),
            "format": self.format_combo.currentData(),
            "output_dir": self.output_dir_input.text().strip(),
            "stability": self.stability_spin.value(),
            "similarity": self.similarity_spin.value(),
            "style": self.style_spin.value(),
            "speaker_boost": self.boost_check.isChecked(),
            "clear_after": self.clear_after_check.isChecked(),
            "split_mode": self.split_combo.currentIndex(),
        }

    def select_output_dir(self):
        default_dir = self.output_dir_input.text().strip() or os.path.join(os.getcwd(), "MyWorkspace")
        os.makedirs(default_dir, exist_ok=True)
        path = QFileDialog.getExistingDirectory(self, "选择 ElevenLabs 音频输出目录", default_dir)
        if path:
            self.output_dir_input.setText(path)
            self.save_settings()

    def api_key(self):
        return self.key_input.text().strip()

    def _sync_account_from_inputs(self):
        key = self.api_key()
        if not key:
            return False

        alias = self.account_alias_input.text().strip()
        changed = False
        found = None
        for account in self.accounts:
            if account.get("key") == key:
                found = account
                break

        if found:
            if alias and found.get("alias") != alias:
                found["alias"] = alias
                changed = True
        else:
            self.accounts.append({"alias": alias or f"账号 {len(self.accounts) + 1}", "key": key})
            changed = True

        self.current_account_key = key
        if changed:
            self.render_account_combo()
        return changed

    def current_account(self):
        key = self.current_account_key or self.api_key()
        for account in self.accounts:
            if account.get("key") == key:
                return account
        return {}

    def account_label(self, account):
        alias = account.get("alias") or "未命名账号"
        key = account.get("key", "")
        tail = key[-4:] if len(key) >= 4 else "----"
        left = account.get("quota_left")
        if isinstance(left, int):
            return f"{alias} · 剩 {left:,} 字 · ••••{tail}"
        return f"{alias} · 未查余额 · ••••{tail}"

    def render_account_combo(self):
        if not hasattr(self, "account_combo"):
            return
        current_key = self.current_account_key or self.api_key()
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        if not self.accounts:
            self.account_combo.addItem("未保存账号", "")
        else:
            for account in self.accounts:
                self.account_combo.addItem(self.account_label(account), account.get("key", ""))
            idx = self.account_combo.findData(current_key)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)
        self.account_combo.blockSignals(False)

    def on_account_changed(self, index):
        if index < 0:
            return
        key = self.account_combo.itemData(index) or ""
        if not key:
            return
        self.current_account_key = key
        account = self.current_account()
        self.account_alias_input.setText(account.get("alias", ""))
        self.key_input.setText(key)
        if isinstance(account.get("quota_left"), int):
            self.lbl_quota.setText(f"额度: 剩 {account.get('quota_left'):,} / 总 {account.get('quota_limit', 0):,} 字")
        self.save_settings()
        self.check_quota()
        self.refresh_voices()

    def add_or_update_account(self):
        key = self.api_key()
        if not key:
            QMessageBox.warning(self, "提示", "请先填写 API Key。")
            return
        alias = self.account_alias_input.text().strip() or f"账号 {len(self.accounts) + 1}"
        found = None
        for account in self.accounts:
            if account.get("key") == key:
                found = account
                break
        if found:
            found["alias"] = alias
        else:
            self.accounts.append({"alias": alias, "key": key})
        self.current_account_key = key
        self.render_account_combo()
        self.save_settings()
        self.sig_status.emit(f"已保存账号: {alias}")

    def delete_current_account(self):
        key = self.api_key()
        if not key or not self.accounts:
            return
        account = self.current_account()
        alias = account.get("alias", "当前账号")
        reply = QMessageBox.warning(self, "删除账号", f"确认删除账号「{alias}」吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.accounts = [a for a in self.accounts if a.get("key") != key]
        self.current_account_key = self.accounts[0].get("key", "") if self.accounts else ""
        self.key_input.setText(self.current_account_key)
        self.account_alias_input.setText(self.current_account().get("alias", "") if self.accounts else "")
        self.render_account_combo()
        self.save_settings()
        self.sig_status.emit("账号已删除")

    def export_accounts_csv(self):
        if not self.accounts:
            QMessageBox.information(self, "没有账号", "当前没有可导出的账号。")
            return
        default_path = os.path.join(os.getcwd(), "ElevenLabs_账号.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出 ElevenLabs 账号 CSV", default_path, "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["备注名", "API_Key", "剩余字数", "总额度"])
                for account in self.accounts:
                    writer.writerow([
                        account.get("alias", ""),
                        account.get("key", ""),
                        account.get("quota_left", ""),
                        account.get("quota_limit", ""),
                    ])
            self.sig_status.emit(f"CSV 已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def import_accounts_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入 ElevenLabs 账号", os.getcwd(), "Key Files (*.csv *.txt);;All Files (*.*)")
        if not path:
            return
        added = 0
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                sample = f.read()
            rows = []
            if path.lower().endswith(".csv") or "," in sample:
                for row in csv.reader(sample.splitlines()):
                    if not row:
                        continue
                    if row[0].strip() in ("备注名", "alias", "Alias"):
                        continue
                    if len(row) == 1:
                        rows.append((f"账号 {len(self.accounts) + added + 1}", row[0].strip()))
                    else:
                        rows.append((row[0].strip() or f"账号 {len(self.accounts) + added + 1}", row[1].strip()))
            else:
                rows = [(f"账号 {len(self.accounts) + i + 1}", line.strip()) for i, line in enumerate(sample.splitlines()) if line.strip()]

            existing = {account.get("key") for account in self.accounts}
            for alias, key in rows:
                if len(key) < 10 or key in existing:
                    continue
                self.accounts.append({"alias": alias, "key": key})
                existing.add(key)
                added += 1
            if added:
                self.current_account_key = self.accounts[-1].get("key", "")
                self.key_input.setText(self.current_account_key)
                self.account_alias_input.setText(self.accounts[-1].get("alias", ""))
                self.render_account_combo()
                self.save_settings()
            self.sig_status.emit(f"已导入 {added} 个账号")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def refresh_all_account_quotas(self):
        if not self.accounts:
            QMessageBox.information(self, "没有账号", "请先添加账号。")
            return
        self.save_settings()
        self.sig_status.emit("正在刷新全部账号余额...")
        threading.Thread(target=self._refresh_all_account_quotas_worker, daemon=True).start()

    def _refresh_all_account_quotas_worker(self):
        try:
            import requests
            for account in list(self.accounts):
                key = account.get("key", "")
                if not key:
                    continue
                try:
                    res = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=30)
                    if not res.ok:
                        raise Exception(f"HTTP {res.status_code}")
                    self.sig_account_quota.emit(key, res.json())
                except Exception as e:
                    self.sig_log.emit(f"{account.get('alias', '账号')} 余额刷新失败: {e}", "#f38ba8")
            self.sig_status.emit("全部账号余额刷新完成")
        except Exception as e:
            self.sig_log.emit(f"余额刷新失败: {e}", "#f38ba8")

    def selected_voice_id(self):
        manual = self.voice_id_input.text().strip()
        if manual:
            return manual
        return self.voice_combo.currentData() or ""

    def refresh_voices(self):
        key = self.api_key()
        if not key:
            QMessageBox.warning(self, "提示", "请先填写 ElevenLabs API Key。")
            return
        self.save_settings()
        self.btn_refresh_voice.setEnabled(False)
        self.sig_status.emit("正在拉取声音列表...")
        threading.Thread(target=self._fetch_voices_worker, args=(key,), daemon=True).start()

    def _fetch_voices_worker(self, key):
        try:
            import requests
            res = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=30)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:180]}")
            self.sig_voices.emit(res.json().get("voices", []))
            self.sig_status.emit("声音列表已更新")
        except Exception as e:
            self.sig_log.emit(f"声音列表获取失败: {e}", "#f38ba8")
            self.sig_status.emit("声音列表获取失败")
            self.sig_voices.emit(self.voice_items)

    def apply_voices(self, voices):
        self.btn_refresh_voice.setEnabled(True)
        self.voice_items = voices or []
        self.voice_combo.clear()
        if not self.voice_items:
            self.voice_combo.addItem("没有可用声音", "")
            return
        for voice in sorted(self.voice_items, key=lambda v: v.get("name", "")):
            name = voice.get("name", "Unnamed")
            category = voice.get("category", "")
            label = f"{name} · {category}" if category else name
            self.voice_combo.addItem(label, voice.get("voice_id", ""))

    def check_quota(self):
        key = self.api_key()
        if not key:
            QMessageBox.warning(self, "提示", "请先填写 ElevenLabs API Key。")
            return
        self.save_settings()
        self.sig_status.emit("正在检查额度...")
        threading.Thread(target=self._quota_worker, args=(key,), daemon=True).start()

    def _quota_worker(self, key):
        try:
            import requests
            res = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=30)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:180]}")
            data = res.json()
            self.sig_quota.emit(data)
            self.sig_account_quota.emit(key, data)
            self.sig_status.emit("额度已刷新")
        except Exception as e:
            self.sig_log.emit(f"额度检查失败: {e}", "#f38ba8")
            self.sig_status.emit("额度检查失败")

    def apply_quota(self, data):
        limit = int(data.get("character_limit", 0) or 0)
        used = int(data.get("character_count", 0) or 0)
        left = max(0, limit - used)
        self.lbl_quota.setText(f"额度: 剩 {left:,} / 总 {limit:,} 字")

    def apply_account_quota(self, key, data):
        limit = int(data.get("character_limit", 0) or 0)
        used = int(data.get("character_count", 0) or 0)
        left = max(0, limit - used)
        for account in self.accounts:
            if account.get("key") == key:
                account["quota_left"] = left
                account["quota_limit"] = limit
                break
        if key == self.api_key():
            self.lbl_quota.setText(f"额度: 剩 {left:,} / 总 {limit:,} 字")
        self.render_account_combo()
        self.save_settings()

    def parse_segments(self):
        text = self.text_editor.toPlainText().strip()
        if not text:
            return []
        mode = self.split_combo.currentIndex()
        if mode == 2:
            return [text]
        if mode == 1:
            return [line.strip() for line in text.splitlines() if line.strip()]
        return [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]

    def update_stats(self):
        segments = self.parse_segments()
        total_chars = sum(len(s) for s in segments)
        self.lbl_stats.setText(f"{total_chars} 字 · {len(segments)} 段")

    def clear_text(self):
        self.text_editor.clear()

    def start_generation(self):
        if self.is_running:
            return
        key = self.api_key()
        voice_id = self.selected_voice_id()
        segments = self.parse_segments()
        if not key:
            return QMessageBox.warning(self, "提示", "请先填写 ElevenLabs API Key。")
        if not voice_id:
            return QMessageBox.warning(self, "提示", "请先选择声音，或手动填写 Voice ID。")
        if not segments:
            return QMessageBox.warning(self, "提示", "请先输入要生成的文案。")

        output_dir = self.output_dir_input.text().strip() or os.path.join(os.getcwd(), "MyWorkspace", "ElevenLabs_语音")
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir_input.setText(output_dir)
        self.save_settings()
        api_format, file_ext = self._format_config()
        model = self.model_combo.currentText()
        voice_settings = {
            "stability": self.stability_spin.value(),
            "similarity_boost": self.similarity_spin.value(),
        }
        if model == "eleven_multilingual_v2":
            voice_settings["style"] = self.style_spin.value()
            voice_settings["use_speaker_boost"] = self.boost_check.isChecked()
        cfg = {
            "key": key,
            "voice_id": voice_id,
            "api_format": api_format,
            "file_ext": file_ext,
            "model": model,
            "voice_settings": voice_settings,
            "clear_after": self.clear_after_check.isChecked(),
        }

        self.is_running = True
        self.btn_generate.setEnabled(False)
        self.btn_refresh_voice.setEnabled(False)
        self.progress.setValue(0)
        self.log_console.clear()
        self.sig_status.emit(f"开始生成 {len(segments)} 段...")
        threading.Thread(target=self._generate_worker, args=(segments, output_dir, cfg), daemon=True).start()

    def _format_config(self):
        raw_format = self.format_combo.currentData()
        if raw_format == "mp3_as_mp4":
            return "mp3_44100_128", "mp4"
        if raw_format == "pcm_44100":
            return raw_format, "wav"
        return raw_format, "mp3"

    def _write_audio_file(self, path, content, api_format):
        if api_format == "pcm_44100":
            with wave.open(path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(content)
            return
        with open(path, "wb") as f:
            f.write(content)

    def _generate_worker(self, segments, output_dir, cfg):
        try:
            import requests
            total = max(1, len(segments))
            for idx, text in enumerate(segments, start=1):
                self.sig_status.emit(f"生成 {idx}/{total} ...")
                self.sig_log.emit(f"[{idx}/{total}] {text[:48]}", "#89b4fa")
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}?output_format={cfg['api_format']}"
                res = requests.post(
                    url,
                    headers={"xi-api-key": cfg["key"], "Content-Type": "application/json"},
                    json={"text": text, "model_id": cfg["model"], "voice_settings": cfg["voice_settings"]},
                    timeout=180
                )
                if not res.ok:
                    detail = res.text[:300]
                    try:
                        data = res.json()
                        detail = data.get("detail", {}).get("message", detail) if isinstance(data.get("detail"), dict) else str(data.get("detail", detail))
                    except Exception:
                        pass
                    raise Exception(f"第 {idx} 段失败: HTTP {res.status_code} {detail}")
                filename = f"{idx:03d}_{_safe_filename(text)}.{cfg['file_ext']}"
                out_path = os.path.join(output_dir, filename)
                self._write_audio_file(out_path, res.content, cfg["api_format"])
                self.sig_log.emit(f"已保存: {out_path}", "#a6e3a1")
                self.sig_progress.emit(int(idx * 100 / total))
            self.sig_status.emit("全部生成完成")
            if cfg.get("clear_after"):
                self.sig_clear_text.emit()
        except Exception as e:
            self.sig_log.emit(str(e), "#f38ba8")
            self.sig_status.emit("生成失败")
        finally:
            self.sig_finished.emit()

    def on_generation_finished(self):
        self.is_running = False
        self.btn_generate.setEnabled(True)
        self.btn_refresh_voice.setEnabled(True)

    def append_log(self, msg, color):
        self.log_console.append(f"<span style='color:{color}'>{msg}</span>")
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())


class ScrollView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.state = {"pages": []}
        self.tool_buttons = []
        self.init_ui()
        self.load_from_project(self.project_data)

    def init_ui(self):
        self.setStyleSheet("QWidget { background-color: #11111b; color: #cdd6f4; font-family: 'Segoe UI', Arial; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("🧰 小工具房间")
        title.setStyleSheet("font-size: 26px; font-weight: 900; color: #cdd6f4;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 10px; }")
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(10, 10, 10, 10)
        side_layout.setSpacing(8)
        side_title = QLabel("工具列表")
        side_title.setStyleSheet("color: #89b4fa; font-size: 15px; font-weight: bold; padding: 6px;")
        side_layout.addWidget(side_title)

        self.stack = QStackedWidget()
        self.scroll_tool_page = self._build_scroll_tool()
        self.elevenlabs_tool_page = create_elevenlabs_tool(self, ElevenLabsTool)
        self.elevenlabs_assist_tool_page = create_elevenlabs_assist_tool(self)
        self.stack.addWidget(self.scroll_tool_page)
        self.stack.addWidget(self.elevenlabs_tool_page)
        self.stack.addWidget(self.elevenlabs_assist_tool_page)

        self._add_tool_button(side_layout, "工具 01", "滚动字幕", 0)
        self._add_tool_button(side_layout, "工具 02", "ElevenLabs 语音", 1, ELEVEN_ICON)
        self._add_tool_button(side_layout, "工具 03", "网页授权语音", 2, ELEVEN_ASSIST_ICON)
        side_layout.addStretch()

        body.addWidget(self.sidebar)
        body.addWidget(self.stack, stretch=1)
        layout.addLayout(body, stretch=1)
        self.switch_tool(0)

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        apply_tinted_styles(self, colors)
        for page in (getattr(self, "elevenlabs_tool_page", None), getattr(self, "elevenlabs_assist_tool_page", None)):
            if hasattr(page, "apply_theme"):
                page.apply_theme(colors, self._theme_key)

    def _add_tool_button(self, layout, badge, name, index, icon_path=None):
        btn = QPushButton(f"{badge}\n{name}")
        btn.setCheckable(True)
        btn.setMinimumHeight(62)
        if icon_path and os.path.exists(icon_path):
            btn.setIcon(QIcon(icon_path))
        btn.setStyleSheet("""
            QPushButton { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; border-radius: 8px; padding: 8px; text-align: left; font-weight: bold; }
            QPushButton:hover { border-color: #89b4fa; background-color: #242438; }
            QPushButton:checked { background-color: #313244; color: #a6e3a1; border-color: #a6e3a1; }
        """)
        btn.clicked.connect(lambda: self.switch_tool(index))
        self.tool_buttons.append(btn)
        layout.addWidget(btn)

    def switch_tool(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.tool_buttons):
            btn.setChecked(i == index)

    def _build_scroll_tool(self):
        page = QFrame()
        page.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 10px; }")
        tool_layout = QVBoxLayout(page)
        tool_layout.setContentsMargins(16, 16, 16, 16)
        tool_layout.setSpacing(12)

        tool_header = QHBoxLayout()
        tool_name = QLabel("工具 01 · 滚动字幕")
        tool_name.setStyleSheet("font-size: 18px; font-weight: bold; color: #f9e2af; border: none;")
        tool_header.addWidget(tool_name)
        tool_header.addStretch()
        tool_layout.addLayout(tool_header)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("每一行当作一页滚动字幕。")
        self.editor.setStyleSheet("background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; border-radius: 8px; padding: 10px;")
        self.btn_save = QPushButton("💾 保存到工程")
        self.btn_save.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-size: 15px; font-weight: bold; padding: 10px 16px; border-radius: 6px;")
        self.btn_save.clicked.connect(self.manual_save)
        tool_layout.addWidget(self.editor, stretch=1)
        tool_layout.addWidget(self.btn_save)
        return page

    def load_from_project(self, project_data):
        self.project_data = project_data or self.project_data or {}
        pages = []
        if isinstance(self.project_data, dict):
            pages = self.project_data.get("room_state", {}).get("scroll_room", {}).get("pages", [])
            if not pages:
                pages = self.project_data.get("scroll_pages", [])
        self.state["pages"] = list(pages or [])
        self.editor.setPlainText("\n".join(self.state["pages"]))

    def export_state(self):
        pages = [line.strip() for line in self.editor.toPlainText().splitlines() if line.strip()]
        self.state = {"pages": pages}
        return self.state

    def parent_window(self):
        parent = self.parent()
        while parent is not None and not hasattr(parent, "project"):
            parent = parent.parent()
        return parent

    def manual_save(self):
        parent = self.parent_window()
        if parent and hasattr(parent, "project"):
            parent.project = update_room_state(parent.project, "scroll_room", self.export_state())
            self.project_data = parent.project
        QMessageBox.information(self, "保存成功", "小工具内容已写入工程文件。")
