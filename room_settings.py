# ==========================================
# 文件名: room_settings.py (账号池与负载均衡全开版)
# ==========================================
import os
import json
import threading
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                             QTextEdit, QPushButton, QMessageBox, QFrame,
<<<<<<< HEAD
                             QHBoxLayout, QLineEdit, QScrollArea)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
import requests

from core import DEFAULT_SYNC_URL, CLOUD_SECRET
from app_theme import apply_tinted_styles
from font_assets import ensure_fonts_dir, font_asset_summary, register_bundled_fonts
=======
                             QHBoxLayout, QLineEdit)
from PyQt6.QtCore import pyqtSignal
import requests

from core import DEFAULT_SYNC_URL, CLOUD_SECRET
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
from render_config import (
    cpu_safe_profile,
    describe_render_profile,
    detect_hardware_profile,
    peek_render_profile,
)
<<<<<<< HEAD
from font_registry import FONT_REGISTRY_FILE, STATUS_NONCOMMERCIAL, load_font_registry, reset_to_open_font_policy, upsert_approved_fonts

CONFIG_FILE = os.path.join(os.getcwd(), "settings.json")


def load_cloud_secret():
    cloud_secret = CLOUD_SECRET
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            cloud_secret = config.get("cloud_secret") or cloud_secret
        except Exception:
            pass
    return (cloud_secret or "").strip()


class SettingsSection(QWidget):
    def __init__(self, title, content_widget, accent="#89b4fa", expanded=True, parent=None):
        super().__init__(parent)
        self.title = title
        self.content_widget = content_widget
        self.accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(bool(expanded))
        self.toggle_button.clicked.connect(self.sync_state)
        layout.addWidget(self.toggle_button)

        self.content_widget.setVisible(bool(expanded))
        layout.addWidget(self.content_widget)
        self.sync_state()

    def sync_state(self, checked=None):
        expanded = self.toggle_button.isChecked()
        self.toggle_button.setText(f"{'▼' if expanded else '▶'}  {self.title}")
        self.content_widget.setVisible(expanded)

    def apply_section_theme(self, colors):
        self.toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['panel_2']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 10px 14px;
                text-align: left;
                font-size: 14px;
                font-weight: 900;
            }}
            QPushButton:hover {{
                background-color: {colors['card_hover']};
                border-color: {self.accent};
            }}
            QPushButton:checked {{
                color: {self.accent};
            }}
        """)


=======

CONFIG_FILE = os.path.join(os.getcwd(), "settings.json")

>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
class SettingsView(QWidget):
    sig_sync_finished = pyqtSignal(bool, str, object)
    sig_hardware_finished = pyqtSignal(bool, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.sig_sync_finished.connect(self.on_sync_finished)
        self.sig_hardware_finished.connect(self.on_hardware_finished)
        self.load_config()

    def init_ui(self):
<<<<<<< HEAD
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.settings_content = QWidget()
        self.settings_scroll.setWidget(self.settings_content)
        root_layout.addWidget(self.settings_scroll)

        layout = QVBoxLayout(self.settings_content)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        self.setting_sections = []
=======
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

        # 👑 顶部标题
        title = QLabel("⚙️ 全局设置与引擎管控 (Global Settings)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        cloud_frame = QFrame()
        cloud_frame.setStyleSheet("background-color: #181825; border-radius: 10px; border: 1px solid #89b4fa;")
        cloud_layout = QVBoxLayout(cloud_frame)
        cloud_layout.setContentsMargins(25, 20, 25, 20)
        cloud_layout.setSpacing(10)

        lbl_cloud_title = QLabel("Cloudflare Workers 云端同步链接")
        lbl_cloud_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa; border: none;")
        cloud_layout.addWidget(lbl_cloud_title)

        lbl_cloud_desc = QLabel("填写 Workers 链接后，点击“获取/识别 API”，软件会从云端读取 cf_accounts 并同步到下方账号池。")
        lbl_cloud_desc.setStyleSheet("color: #a6adc8; font-size: 13px; border: none;")
        cloud_layout.addWidget(lbl_cloud_desc)

        url_row = QHBoxLayout()
        self.txt_sync_url = QLineEdit()
        self.txt_sync_url.setPlaceholderText("例如: https://你的-worker.workers.dev/")
        self.txt_sync_url.setStyleSheet("""
            QLineEdit {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        btn_sync = QPushButton("获取/识别 API")
        btn_sync.setFixedHeight(40)
        btn_sync.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 0 16px;
                border: none;
            }
            QPushButton:hover { background-color: #74c7ec; }
        """)
        btn_sync.clicked.connect(self.sync_from_worker)
        url_row.addWidget(self.txt_sync_url, stretch=1)
        url_row.addWidget(btn_sync)
        cloud_layout.addLayout(url_row)

        self.lbl_sync_status = QLabel("就绪")
        self.lbl_sync_status.setStyleSheet("color: #f9e2af; font-size: 12px; border: none;")
        cloud_layout.addWidget(self.lbl_sync_status)

<<<<<<< HEAD
        self.cloud_section = self._add_section(layout, "云端同步链接", cloud_frame, "#89b4fa", expanded=True)
=======
        layout.addWidget(cloud_frame)
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

        hardware_frame = QFrame()
        hardware_frame.setStyleSheet("background-color: #181825; border-radius: 10px; border: 1px solid #a6e3a1;")
        hardware_layout = QVBoxLayout(hardware_frame)
        hardware_layout.setContentsMargins(25, 18, 25, 18)
        hardware_layout.setSpacing(10)

        lbl_hardware_title = QLabel("⚙️ 硬件扫描与渲染优化")
        lbl_hardware_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a6e3a1; border: none;")
        hardware_layout.addWidget(lbl_hardware_title)

        lbl_hardware_desc = QLabel("自动识别 CPU、内存、显卡和 FFmpeg 编码器，优先使用可用硬件加速；不稳定时可一键切回 CPU 安全模式。")
        lbl_hardware_desc.setWordWrap(True)
        lbl_hardware_desc.setStyleSheet("color: #a6adc8; font-size: 13px; border: none;")
        hardware_layout.addWidget(lbl_hardware_desc)

        self.lbl_hardware_profile = QLabel("尚未扫描。点击下方按钮后会写入 settings.json，导出和批量流水线都会使用这份配置。")
        self.lbl_hardware_profile.setWordWrap(True)
        self.lbl_hardware_profile.setStyleSheet("""
            QLabel {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.4;
            }
        """)
        hardware_layout.addWidget(self.lbl_hardware_profile)

        hardware_btn_row = QHBoxLayout()
        self.btn_scan_hardware = QPushButton("🔍 扫描显卡/CPU并自动配置")
        self.btn_scan_hardware.setFixedHeight(38)
        self.btn_scan_hardware.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 0 16px;
                border: none;
            }
            QPushButton:hover { background-color: #94d38f; }
            QPushButton:disabled { background-color: #45475a; color: #a6adc8; }
        """)
        self.btn_scan_hardware.clicked.connect(self.scan_hardware_profile)

        self.btn_cpu_safe = QPushButton("🧯 使用 CPU 安全模式")
        self.btn_cpu_safe.setFixedHeight(38)
        self.btn_cpu_safe.setStyleSheet("""
            QPushButton {
                background-color: #f9e2af;
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 0 16px;
                border: none;
            }
            QPushButton:hover { background-color: #f5d58b; }
            QPushButton:disabled { background-color: #45475a; color: #a6adc8; }
        """)
        self.btn_cpu_safe.clicked.connect(self.use_cpu_render_profile)

        hardware_btn_row.addWidget(self.btn_scan_hardware)
        hardware_btn_row.addWidget(self.btn_cpu_safe)
        hardware_layout.addLayout(hardware_btn_row)

<<<<<<< HEAD
        self.hardware_section = self._add_section(layout, "硬件扫描与渲染优化", hardware_frame, "#a6e3a1", expanded=True)

        font_frame = QFrame()
        font_frame.setStyleSheet("background-color: #181825; border-radius: 10px; border: 1px solid #f9e2af;")
        font_layout = QVBoxLayout(font_frame)
        font_layout.setContentsMargins(25, 18, 25, 18)
        font_layout.setSpacing(10)

        lbl_font_title = QLabel("字体版权登记")
        lbl_font_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f9e2af; border: none;")
        font_layout.addWidget(lbl_font_title)

        lbl_font_desc = QLabel("把已经由团队确认可商用的字体写在这里，每行一个字体名。工程体检会用这份登记表标记字体风险。系统字体和未登记字体仍会提示复核。")
        lbl_font_desc.setWordWrap(True)
        lbl_font_desc.setStyleSheet("color: #a6adc8; font-size: 13px; border: none;")
        font_layout.addWidget(lbl_font_desc)

        self.lbl_font_registry = QLabel("")
        self.lbl_font_registry.setStyleSheet("color: #cdd6f4; background-color: #11111b; border: 1px solid #45475a; border-radius: 6px; padding: 8px; font-size: 12px;")
        font_layout.addWidget(self.lbl_font_registry)

        self.lbl_font_assets = QLabel("")
        self.lbl_font_assets.setWordWrap(True)
        self.lbl_font_assets.setStyleSheet("color: #a6adc8; background-color: #11111b; border: 1px solid #313244; border-radius: 6px; padding: 8px; font-size: 12px;")
        font_layout.addWidget(self.lbl_font_assets)

        self.txt_approved_fonts = QTextEdit()
        self.txt_approved_fonts.setPlaceholderText("例如:\nNoto Sans SC\nSource Han Sans SC\n你的品牌授权字体")
        self.txt_approved_fonts.setMaximumHeight(92)
        self.txt_approved_fonts.setStyleSheet("background-color: #11111b; color: #f9e2af; border: 1px solid #45475a; border-radius: 6px; padding: 8px; font-family: Consolas, 'Microsoft YaHei';")
        font_layout.addWidget(self.txt_approved_fonts)

        font_btn_row = QHBoxLayout()
        self.btn_save_fonts = QPushButton("保存已确认字体")
        self.btn_save_fonts.setFixedHeight(36)
        self.btn_save_fonts.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none;")
        self.btn_save_fonts.clicked.connect(self.save_font_registry_ui)
        self.btn_open_only_fonts = QPushButton("整理为开源字体库")
        self.btn_open_only_fonts.setFixedHeight(36)
        self.btn_open_only_fonts.setStyleSheet("background-color: #313244; color: #f9e2af; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none;")
        self.btn_open_only_fonts.clicked.connect(self.reset_open_font_policy_ui)
        self.btn_refresh_font_assets = QPushButton("刷新内置字体包")
        self.btn_refresh_font_assets.setFixedHeight(36)
        self.btn_refresh_font_assets.setStyleSheet("background-color: #313244; color: #a6e3a1; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none;")
        self.btn_refresh_font_assets.clicked.connect(self.refresh_font_assets_ui)
        self.btn_open_fonts_dir = QPushButton("打开字体文件夹")
        self.btn_open_fonts_dir.setFixedHeight(36)
        self.btn_open_fonts_dir.setStyleSheet("background-color: #313244; color: #89b4fa; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none;")
        self.btn_open_fonts_dir.clicked.connect(self.open_fonts_dir_ui)
        font_btn_row.addWidget(self.btn_save_fonts)
        font_btn_row.addWidget(self.btn_open_only_fonts)
        font_btn_row.addWidget(self.btn_refresh_font_assets)
        font_btn_row.addWidget(self.btn_open_fonts_dir)
        font_btn_row.addStretch()
        font_layout.addLayout(font_btn_row)

        self.font_section = self._add_section(layout, "字体版权登记", font_frame, "#f9e2af", expanded=False)
=======
        layout.addWidget(hardware_frame)
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

        # 👑 账号池大框架
        pool_frame = QFrame()
        pool_frame.setStyleSheet("background-color: #181825; border-radius: 10px; border: 1px solid #313244;")
        pool_layout = QVBoxLayout(pool_frame)
        pool_layout.setContentsMargins(25, 25, 25, 25)
        pool_layout.setSpacing(15)

        # 提示信息
        lbl_pool_title = QLabel("🤖 Cloudflare Whisper AI 账号池 (支持自动负载均衡与故障轮询)")
        lbl_pool_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa; border: none;")
        pool_layout.addWidget(lbl_pool_title)

        lbl_desc = QLabel("为了突破单账号免费额度与并发限制，请在下方【批量填入】您的云端账号矩阵。\n"
                          "👉 格式要求：每行填写一个账号，Account ID 和 API Token 之间用【英文逗号】或【空格】隔开。\n"
                          "👉 底层引擎在打轴时，遇到请求上限或报错会瞬间无缝切换下一个账号！完全不卡顿！")
        lbl_desc.setStyleSheet("color: #a6adc8; line-height: 1.5; font-size: 13px; border: none;")
        pool_layout.addWidget(lbl_desc)

        # 多行输入文本框
        self.txt_accounts = QTextEdit()
        self.txt_accounts.setPlaceholderText("粘贴您的账号阵列，例如:\nf48b2db71fc565c2abfc..., abcdefg1234567890...\n1234567890abcdef..., xyz0987654321...")
        self.txt_accounts.setStyleSheet("""
            QTextEdit {
                background-color: #11111b; 
                color: #a6e3a1; 
                font-family: Consolas; 
                font-size: 14px; 
                border: 1px solid #45475a; 
                border-radius: 6px; 
                padding: 10px;
            }
        """)
        pool_layout.addWidget(self.txt_accounts, stretch=1)

        # 保存按钮
        btn_save = QPushButton("💾 保存全局账号阵列")
        btn_save.setFixedHeight(45)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b; 
                color: #11111b; 
                font-size: 16px; 
                font-weight: bold; 
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        btn_save.clicked.connect(self.save_config)
        pool_layout.addWidget(btn_save)

<<<<<<< HEAD
        self.pool_section = self._add_section(layout, "Cloudflare Whisper AI 账号池", pool_frame, "#89b4fa", expanded=False)
        layout.addStretch(1)

    def _add_section(self, layout, title, frame, accent, expanded=True):
        section = SettingsSection(title, frame, accent=accent, expanded=expanded, parent=self.settings_content)
        self.setting_sections.append(section)
        layout.addWidget(section)
        return section

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        apply_tinted_styles(self, colors)
        self.settings_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {colors['bg']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {colors['panel']};
                width: 12px;
                margin: 4px 2px 4px 2px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {colors['accent']};
                border-radius: 5px;
                min-height: 42px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        for section in getattr(self, "setting_sections", []):
            section.apply_section_theme(colors)
=======
        layout.addWidget(pool_frame, stretch=1)
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.txt_sync_url.setText(config.get("sync_url", DEFAULT_SYNC_URL))
                    accounts = config.get("cf_accounts", [])
                    if accounts:
                        # 将 JSON 里的账号还原为多行文本展示
                        lines = [f"{acc.get('id', '')},{acc.get('token', '')}" for acc in accounts]
                        self.txt_accounts.setPlainText("\n".join(lines))
            except: pass
        else:
            self.txt_sync_url.setText(DEFAULT_SYNC_URL)
<<<<<<< HEAD
        self.load_font_registry_ui()
        self.refresh_font_asset_label()
        self.refresh_hardware_profile_label()

    def load_font_registry_ui(self):
        if not hasattr(self, "txt_approved_fonts"):
            return
        try:
            data = load_font_registry()
            fonts = data.get("fonts", {})
            approved = [
                name for name, record in sorted(fonts.items(), key=lambda item: item[0].casefold())
                if isinstance(record, dict) and record.get("status") == "approved"
            ]
            self.txt_approved_fonts.setPlainText("\n".join(approved))
            open_count = sum(1 for record in fonts.values() if isinstance(record, dict) and record.get("status") == "open")
            restricted_count = sum(1 for record in fonts.values() if isinstance(record, dict) and record.get("status") == STATUS_NONCOMMERCIAL)
            review_count = sum(1 for record in fonts.values() if isinstance(record, dict) and record.get("status") == "review")
            self.lbl_font_registry.setText(f"登记文件: {FONT_REGISTRY_FILE}\n开源白名单 {open_count} 个；手动确认 {len(approved)} 个；待确认 {review_count} 个。")
            if restricted_count:
                self.lbl_font_registry.setText(self.lbl_font_registry.text() + f"\nRestricted/non-commercial {restricted_count} fonts.")
        except Exception as e:
            self.lbl_font_registry.setText(f"字体登记读取失败: {e}")

    def refresh_font_asset_label(self):
        if not hasattr(self, "lbl_font_assets"):
            return
        try:
            summary = font_asset_summary()
            families = summary.get("families", [])
            family_text = ", ".join(families[:10])
            if len(families) > 10:
                family_text += f" ... +{len(families) - 10}"
            if not family_text:
                family_text = "尚未放入字体文件"
            self.lbl_font_assets.setText(
                f"内置字体包: {summary.get('font_file_count', 0)} 个字体文件 / "
                f"{summary.get('family_count', 0)} 个字体族\n"
                f"目录: {summary.get('fonts_dir')}\n"
                f"已识别: {family_text}"
            )
        except Exception as e:
            self.lbl_font_assets.setText(f"读取内置字体包失败: {e}")

    def refresh_font_assets_ui(self):
        try:
            loaded = register_bundled_fonts()
            self.load_font_registry_ui()
            self.refresh_font_asset_label()
            family_count = sum(len(item.get("families", [])) for item in loaded)
            QMessageBox.information(self, "内置字体包已刷新", f"已扫描并注册 {len(loaded)} 个字体文件，识别 {family_count} 个字体族。")
        except Exception as e:
            QMessageBox.warning(self, "刷新失败", str(e))

    def open_fonts_dir_ui(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(ensure_fonts_dir()))

    def save_font_registry_ui(self):
        names = [line.strip() for line in self.txt_approved_fonts.toPlainText().splitlines() if line.strip()]
        try:
            upsert_approved_fonts(names)
            self.load_font_registry_ui()
            QMessageBox.information(self, "已保存", "已更新字体版权登记。工程大厅体检会按这份清单标记字体状态。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def reset_open_font_policy_ui(self):
        reply = QMessageBox.question(
            self,
            "整理为开源字体库",
            "这会保留内置开源字体白名单，并移除你手动标记的“已确认字体”。\n\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            reset_to_open_font_policy()
            self.load_font_registry_ui()
            QMessageBox.information(self, "已整理", "已切换为开源字体白名单策略。系统字体和未登记字体会继续在体检中提示复核。")
        except Exception as e:
            QMessageBox.critical(self, "整理失败", str(e))

=======
        self.refresh_hardware_profile_label()

>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
    def refresh_hardware_profile_label(self, profile=None):
        profile = profile if profile is not None else peek_render_profile()
        if not profile or not profile.get("encoder"):
            self.lbl_hardware_profile.setText("尚未扫描。点击“扫描显卡/CPU并自动配置”后会写入 settings.json；如果没有手动扫描，首次渲染也会自动生成配置。")
            return
        self.lbl_hardware_profile.setText(describe_render_profile(profile))

    def scan_hardware_profile(self):
        self.btn_scan_hardware.setEnabled(False)
        self.btn_cpu_safe.setEnabled(False)
        self.lbl_hardware_profile.setText("正在扫描显卡、CPU、内存和 FFmpeg 编码器，请稍候...")
        threading.Thread(target=self._scan_hardware_thread, daemon=True).start()

    def _scan_hardware_thread(self):
        try:
            profile = detect_hardware_profile(save=True)
            message = describe_render_profile(profile)
            self.sig_hardware_finished.emit(True, message, profile)
        except Exception as e:
            self.sig_hardware_finished.emit(False, str(e), {})

    def use_cpu_render_profile(self):
        try:
            profile = cpu_safe_profile(save=True)
            self.refresh_hardware_profile_label(profile)
            QMessageBox.information(self, "CPU 安全模式已启用", "已切换为 CPU x264 渲染。导出和批量流水线都会使用这个安全配置。")
        except Exception as e:
            QMessageBox.critical(self, "切换失败", f"无法保存 CPU 安全模式：\n{str(e)}")

    def on_hardware_finished(self, ok, message, profile):
        self.btn_scan_hardware.setEnabled(True)
        self.btn_cpu_safe.setEnabled(True)
        if ok:
            self.refresh_hardware_profile_label(profile)
            QMessageBox.information(self, "硬件配置完成", f"已根据当前设备自动选择渲染配置：\n\n{message}")
        else:
            self.refresh_hardware_profile_label()
            QMessageBox.critical(self, "硬件扫描失败", message)

    def save_config(self):
        raw_text = self.txt_accounts.toPlainText().strip()
        lines = raw_text.split('\n')
        
        valid_accounts = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # 智能兼容：把中文逗号替换成英文逗号
            line = line.replace('，', ',')
            
            # 智能拆分：逗号或空格隔开的都能识别
            if ',' in line:
                parts = line.split(',', 1)
            else:
                parts = line.split(maxsplit=1)
                
            if len(parts) == 2:
                acc_id = parts[0].strip()
                acc_token = parts[1].strip()
                if acc_id and acc_token:
                    valid_accounts.append({"id": acc_id, "token": acc_token})

        if not valid_accounts and raw_text:
            QMessageBox.warning(self, "格式错误", "没有解析到有效的账号！\n请确保 Account ID 和 Token 之间有逗号或空格分隔。")
            return

        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except: pass
                
        # 写入 cf_accounts 数组，完美对接房间 1 和 2 的负载均衡
        config["cf_accounts"] = valid_accounts
        config["sync_url"] = self.txt_sync_url.text().strip() or DEFAULT_SYNC_URL
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "保存成功", f"✅ 成功入库 {len(valid_accounts)} 个 AI 账号！\n底层引擎现已火力全开，无缝负载均衡机制已激活！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存配置文件：\n{str(e)}")

    def sync_from_worker(self):
        url = self.txt_sync_url.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先填写 Cloudflare Workers 链接。")
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
            self.txt_sync_url.setText(url)

        self.lbl_sync_status.setText("正在连接 Workers 并识别 API...")
        self.save_sync_url_only(url)
        threading.Thread(target=self._sync_worker_thread, args=(url,), daemon=True).start()

    def save_sync_url_only(self, url):
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
        config["sync_url"] = url
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _sync_worker_thread(self, url):
        try:
<<<<<<< HEAD
            cloud_secret = load_cloud_secret()
            if not cloud_secret:
                raise Exception("Cloud sync secret is not configured. Set SUBTITLE_COMPOSER_CLOUD_SECRET or add cloud_secret in local settings.json.")
=======
            cloud_secret = CLOUD_SECRET
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    cloud_secret = (config.get("cloud_secret") or cloud_secret).strip()
                except Exception:
                    pass
            if not cloud_secret:
                raise Exception("未配置云端同步密钥。请设置环境变量 SUBTITLE_COMPOSER_CLOUD_SECRET，或在本地 settings.json 中添加 cloud_secret。")
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
            headers = {"X-App-Auth": cloud_secret}
            res = requests.get(url, headers=headers, timeout=12, verify=False)
            if res.status_code == 401:
                raise Exception("云端拒绝访问：密钥错误或 Workers 鉴权不通过。")
            res.raise_for_status()
            data = res.json()
            accounts = data.get("cf_accounts", [])
            if not isinstance(accounts, list):
                raise Exception("Workers 返回格式不正确：cf_accounts 不是数组。")

            valid_accounts = []
            for item in accounts:
                if isinstance(item, dict) and item.get("id") and item.get("token"):
                    valid_accounts.append({"id": item.get("id"), "token": item.get("token")})
            if not valid_accounts:
                raise Exception("没有识别到有效 Cloudflare API 账号。Workers 需要返回 cf_accounts。")

            config = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    config = {}
            config["sync_url"] = url
            config["cf_accounts"] = valid_accounts
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.sig_sync_finished.emit(True, f"成功识别并同步 {len(valid_accounts)} 个 Cloudflare API 账号。", valid_accounts)
        except Exception as e:
            self.sig_sync_finished.emit(False, str(e), [])

    def on_sync_finished(self, ok, message, accounts):
        if ok:
            lines = [f"{acc.get('id', '')},{acc.get('token', '')}" for acc in accounts]
            self.txt_accounts.setPlainText("\n".join(lines))
            self.lbl_sync_status.setText(message)
            QMessageBox.information(self, "同步成功", message)
        else:
            self.lbl_sync_status.setText("同步失败")
            QMessageBox.critical(self, "同步失败", message)
 
