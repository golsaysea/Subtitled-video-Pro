# ==========================================
# 文件名: room_project.py (加入项目重命名与删除功能)
# ==========================================
import os
import shutil
import zipfile
import html
import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QFrame, QScrollArea, QGridLayout, QInputDialog, QGraphicsDropShadowEffect, QSplitter,
    QFileDialog, QDialog, QComboBox, QTextEdit, QLineEdit, QDialogButtonBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QPixmap, QCursor, QFont, QIcon, QDesktopServices

from project_io import create_reel, load_project, get_project_folders, get_reels_in_folder, sync_project_assets_to_project_dir
from workspace_config import (
    CLOUD_LINK_MODE_COLLAB,
    CLOUD_LINK_MODE_COPY,
    CLOUD_LINK_MODE_RENDER,
    WORKSPACE_MODE_CLOUD,
    WORKSPACE_MODE_LOCAL,
    get_active_workspace,
    get_workspace_config,
    save_workspace_config,
)
from cloud_workspace import (
    acquire_project_lock,
    ensure_cloud_workspace,
    get_cloud_identity,
    get_share_config,
    release_project_lock,
    save_cloud_identity,
    set_share_config,
    update_manifest_from_workspace,
)


GOOGLE_DRIVE_HINT_NAMES = (
    "Google Drive",
    "My Drive",
    "Shared drives",
    "Il mio Drive",
    "Drive condivisi",
    "Mi unidad",
    "Mon Drive",
    "Meine Ablage",
)


def _parse_google_drive_link(url):
    text = (url or "").strip()
    if not text:
        return {"kind": "", "id": "", "is_drive": False}
    patterns = [
        ("folder", r"/folders/([A-Za-z0-9_-]+)"),
        ("file", r"/file/d/([A-Za-z0-9_-]+)"),
        ("open", r"[?&]id=([A-Za-z0-9_-]+)"),
        ("resource", r"/drive/(?:u/\d+/)?(?:folders|shared-drives)/([A-Za-z0-9_-]+)"),
    ]
    for kind, pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return {"kind": kind, "id": match.group(1), "is_drive": "drive.google.com" in text.lower()}
    return {"kind": "unknown", "id": "", "is_drive": "drive.google.com" in text.lower() or "docs.google.com" in text.lower()}


def _cloud_link_mode_label(mode):
    return {
        CLOUD_LINK_MODE_COLLAB: "协作编辑",
        CLOUD_LINK_MODE_COPY: "复制到我的云盘",
        CLOUD_LINK_MODE_RENDER: "仅渲染下载",
    }.get(mode, "协作编辑")


def _is_path_inside(child, parent):
    try:
        child_abs = os.path.abspath(child)
        parent_abs = os.path.abspath(parent)
        return os.path.commonpath([child_abs, parent_abs]) == parent_abs
    except Exception:
        return False


def _looks_like_google_drive_path(path):
    if not path:
        return False
    norm = os.path.normcase(os.path.abspath(path))
    return any(os.path.normcase(name) in norm for name in GOOGLE_DRIVE_HINT_NAMES)


def _find_google_drive_candidates():
    candidates = []
    seen = set()

    def add(path):
        if path and os.path.isdir(path):
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                candidates.append(os.path.abspath(path))

    home = os.path.expanduser("~")
    for name in GOOGLE_DRIVE_HINT_NAMES:
        add(os.path.join(home, name))
        add(os.path.join(home, "Google Drive", name))

    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if not os.path.exists(root):
                continue
            for name in GOOGLE_DRIVE_HINT_NAMES:
                add(os.path.join(root, name))

    return candidates


def _scan_workspace_summary(workspace):
    folders = get_project_folders(workspace)
    reel_count = 0
    missing_media = 0
    external_media = 0

    for folder_name in folders:
        folder_path = os.path.join(workspace, folder_name)
        for reel_path in get_reels_in_folder(folder_path):
            reel_count += 1
            try:
                project = load_project(reel_path)
            except Exception:
                continue

            edit_state = project.get("room_state", {}).get("edit_room", {})
            media_paths = []
            for clip in edit_state.get("video_clips", []) or []:
                media_paths.append(clip.get("path", ""))
            media_paths.append(edit_state.get("audio_path", ""))

            for media_path in media_paths:
                if not media_path:
                    continue
                if not os.path.exists(media_path):
                    missing_media += 1
                elif not _is_path_inside(media_path, workspace):
                    external_media += 1

    return {
        "folder_count": len(folders),
        "reel_count": reel_count,
        "missing_media": missing_media,
        "external_media": external_media,
    }


class CloudJoinWizard(QDialog):
    def __init__(self, workspace_cfg, parent=None):
        super().__init__(parent)
        self.workspace_cfg = workspace_cfg or {}
        self.setWindowTitle("加入云端团队工程")
        self.resize(760, 620)
        self.setStyleSheet("""
            QDialog { background-color: #11111b; color: #cdd6f4; }
            QLabel { color: #cdd6f4; }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 7px; padding: 8px;
            }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: none; border-radius: 7px; padding: 8px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45475a; }
        """)
        self.init_ui()
        self.run_checks()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("云端团队工程向导")
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #89b4fa;")
        layout.addWidget(title)

        intro = QLabel(
            "粘贴 Google Drive 工程链接后，选择使用方式：有编辑权限就加入协作工程；只有查看权限就复制到自己的云盘；"
            "只想渲染成品时可以走仅渲染下载。当前稳定版优先使用 Google Drive 桌面版同步目录，Google API 自动复制/下载接口会在此入口继续接入。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #a6adc8; background-color: #181825; border-radius: 8px; padding: 10px;")
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.invite_input = QLineEdit()
        self.invite_input.setText(self.workspace_cfg.get("cloud_link", ""))
        self.invite_input.setPlaceholderText("粘贴 Google Drive 工程文件夹链接")
        self.invite_input.textChanged.connect(self.run_checks)
        invite_row = QHBoxLayout()
        invite_row.addWidget(self.invite_input, stretch=1)
        self.btn_open_invite = QPushButton("打开链接")
        self.btn_open_invite.clicked.connect(self.open_invite_link)
        invite_row.addWidget(self.btn_open_invite)
        form.addRow("共享链接", invite_row)

        self.link_mode_combo = QComboBox()
        self.link_mode_combo.addItem("有编辑权限：加入协作工程（推荐团队成员）", CLOUD_LINK_MODE_COLLAB)
        self.link_mode_combo.addItem("只有查看权限：复制到我的云盘后修改", CLOUD_LINK_MODE_COPY)
        self.link_mode_combo.addItem("只渲染下载：临时缓存工程素材", CLOUD_LINK_MODE_RENDER)
        saved_mode = self.workspace_cfg.get("cloud_link_mode", CLOUD_LINK_MODE_COLLAB)
        idx = self.link_mode_combo.findData(saved_mode)
        self.link_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.link_mode_combo.currentIndexChanged.connect(self.on_link_mode_changed)
        form.addRow("使用方式", self.link_mode_combo)

        identity = get_cloud_identity()
        self.email_input = QLineEdit(identity.get("email", ""))
        self.email_input.setPlaceholderText("每个成员自己的 Gmail，用于编辑锁和协作记录")
        self.name_input = QLineEdit(identity.get("name", ""))
        self.name_input.setPlaceholderText("显示名称，例如 Mia / Luca / Team-A")
        form.addRow("个人 Gmail", self.email_input)
        form.addRow("显示名称", self.name_input)

        self.folder_input = QLineEdit(self.workspace_cfg.get("cloud_path", ""))
        self.folder_input.setPlaceholderText("选择 Google Drive 桌面版同步出来的团队工程文件夹")
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_input, stretch=1)
        self.btn_pick_folder = QPushButton("选择文件夹")
        self.btn_pick_folder.clicked.connect(self.select_workspace_folder)
        folder_row.addWidget(self.btn_pick_folder)
        form.addRow("云端文件夹", folder_row)

        layout.addLayout(form)

        action_row = QHBoxLayout()
        self.btn_open_drive_desktop = QPushButton("安装 Google Drive 桌面版")
        self.btn_open_drive_desktop.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.google.com/drive/download/")))
        self.btn_open_my_drive = QPushButton("登录/打开我的 Google Drive")
        self.btn_open_my_drive.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://drive.google.com/drive/my-drive")))
        action_row.addWidget(self.btn_open_drive_desktop)
        action_row.addWidget(self.btn_open_my_drive)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.mode_hint = QLabel("")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setStyleSheet("color: #f9e2af; background-color: #1e1e2e; border-radius: 8px; padding: 10px;")
        layout.addWidget(self.mode_hint)

        step_box = QFrame()
        step_box.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #313244; border-radius: 8px; }")
        step_layout = QVBoxLayout(step_box)
        step_layout.setContentsMargins(12, 12, 12, 12)
        step_layout.setSpacing(6)
        steps = [
            "1. 协作编辑：打开共享链接，确认自己是 Editor，然后选择 Google Drive 桌面版同步出来的工程目录。",
            "2. 复制修改：如果只是 Viewer，但允许下载/复制，可以先在 Google Drive 里复制到自己的云盘，再选择自己的同步目录。",
            "3. 仅渲染：后续 Google API 模块会直接下载到临时缓存；当前可以先手动下载工程包再导入渲染。",
            "4. 每个成员使用自己的 Gmail，软件用它写入编辑锁和协作记录，不建议多人共用一个账号。",
            "5. 完成检测后，软件会切换到云端版，并创建 .subtitle_cloud 协作元数据。",
        ]
        for text in steps:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #a6adc8;")
            step_layout.addWidget(lbl)
        layout.addWidget(step_box)

        check_header = QHBoxLayout()
        check_title = QLabel("检测结果")
        check_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f9e2af;")
        check_header.addWidget(check_title)
        check_header.addStretch()
        self.btn_recheck = QPushButton("重新检测")
        self.btn_recheck.clicked.connect(self.run_checks)
        check_header.addWidget(self.btn_recheck)
        layout.addLayout(check_header)

        self.check_log = QTextEdit()
        self.check_log.setReadOnly(True)
        self.check_log.setMinimumHeight(150)
        layout.addWidget(self.check_log, stretch=1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("完成加入")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.on_link_mode_changed()

    def current_link_mode(self):
        return self.link_mode_combo.currentData() or CLOUD_LINK_MODE_COLLAB

    def on_link_mode_changed(self, *args):
        mode = self.current_link_mode()
        hints = {
            CLOUD_LINK_MODE_COLLAB: "协作编辑模式：需要对方给你编辑权限，并建议安装 Google Drive 桌面版。软件会直接读取同步目录里的同一份工程。",
            CLOUD_LINK_MODE_COPY: "复制副本模式：适合只有查看权限但允许复制/下载的用户。先把工程复制到自己的云盘，再选择自己的同步目录，修改不会影响原工程。",
            CLOUD_LINK_MODE_RENDER: "仅渲染下载模式：目标是不安装桌面版也能渲染。当前稳定版会记录链接和模式，Google API 下载模块接入后可直接下载到临时缓存。",
        }
        self.mode_hint.setText(hints.get(mode, hints[CLOUD_LINK_MODE_COLLAB]))
        if hasattr(self, "buttons"):
            ok_text = "保存渲染入口" if mode == CLOUD_LINK_MODE_RENDER else "完成加入"
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        self.run_checks()

    def _append_check(self, status, message):
        safe = html.escape(message)
        color = {
            "PASS": "#a6e3a1",
            "WARN": "#f9e2af",
            "FAIL": "#f38ba8",
            "INFO": "#89b4fa",
        }.get(status, "#cdd6f4")
        self.check_log.append(f"<span style='color:{color}; font-weight:700'>[{status}]</span> {safe}")

    def open_invite_link(self):
        url = self.invite_input.text().strip()
        if not url:
            QMessageBox.information(self, "需要链接", "请先粘贴管理员发来的 Google Drive 共享链接。")
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        QDesktopServices.openUrl(QUrl(url))

    def select_workspace_folder(self):
        candidates = _find_google_drive_candidates()
        default_dir = self.folder_input.text().strip() or (candidates[0] if candidates else os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self, "选择 Google Drive 团队工程文件夹", default_dir)
        if folder:
            self.folder_input.setText(folder)
            self.run_checks()

    def run_checks(self, *args):
        if not hasattr(self, "check_log"):
            return False
        self.check_log.clear()
        mode = self.current_link_mode() if hasattr(self, "link_mode_combo") else CLOUD_LINK_MODE_COLLAB
        link = self.invite_input.text().strip() if hasattr(self, "invite_input") else ""
        link_info = _parse_google_drive_link(link)
        if link:
            if link_info["is_drive"]:
                detail = f"，ID: {link_info['id']}" if link_info.get("id") else ""
                self._append_check("PASS", f"已识别 Google Drive 链接（{link_info.get('kind') or 'unknown'}{detail}）。")
            else:
                self._append_check("WARN", "已填写链接，但不像 Google Drive 链接；仍可保存，建议确认链接来源。")
        else:
            self._append_check("INFO", "可以粘贴 Google Drive 工程链接，软件会保存到云端入口记录里。")
        self._append_check("INFO", f"当前使用方式：{_cloud_link_mode_label(mode)}。")

        candidates = _find_google_drive_candidates()
        if candidates:
            self._append_check("PASS", f"检测到 Google Drive 本地目录：{candidates[0]}")
        else:
            self._append_check("WARN", "没有自动找到 Google Drive 目录；如果已经安装，也可以手动选择同步文件夹。")

        email = self.email_input.text().strip()
        if email and "@" in email:
            self._append_check("PASS", f"协作身份：{email}")
        else:
            self._append_check("WARN", "还没有填写个人 Gmail。每个成员应使用自己的 Gmail，不建议共用一个账号。")

        folder = self.folder_input.text().strip()
        if not folder:
            if mode == CLOUD_LINK_MODE_RENDER:
                self._append_check("INFO", "仅渲染下载模式暂时可以先保存链接；Google API 下载模块接入后会直接下载到临时缓存。")
                return True
            self._append_check("WARN", "还没有选择云端工程文件夹。协作编辑/复制副本模式需要选择 Google Drive 桌面版同步出来的本地目录。")
            return False

        if not os.path.isdir(folder):
            self._append_check("FAIL", f"文件夹不存在：{folder}")
            return False

        if _looks_like_google_drive_path(folder):
            self._append_check("PASS", "路径看起来是 Google Drive 同步目录。")
        else:
            self._append_check("WARN", "路径不像常见 Google Drive 目录；仍可使用，但请确认它会自动同步到团队云端。")

        try:
            meta_dir = os.path.join(folder, ".subtitle_cloud")
            os.makedirs(meta_dir, exist_ok=True)
            probe_path = os.path.join(meta_dir, "_write_test.tmp")
            with open(probe_path, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe_path)
            self._append_check("PASS", "读写权限正常，可以创建协作锁和工程索引。")
        except Exception as e:
            self._append_check("FAIL", f"无法写入该文件夹：{e}")
            return False

        try:
            ensure_cloud_workspace(folder)
            update_manifest_from_workspace(folder)
            summary = _scan_workspace_summary(folder)
            self._append_check("PASS", f"工程扫描完成：{summary['folder_count']} 个项目文件夹，{summary['reel_count']} 个 Reel。")
            if summary["external_media"]:
                self._append_check("WARN", f"发现 {summary['external_media']} 个素材路径在云端文件夹外；其他用户可能打不开这些本机素材。")
            if summary["missing_media"]:
                self._append_check("WARN", f"发现 {summary['missing_media']} 个素材路径当前不可访问。")
        except Exception as e:
            self._append_check("FAIL", f"云端工程初始化失败：{e}")
            return False

        return True

    def accept(self):
        folder = self.folder_input.text().strip()
        email = self.email_input.text().strip()
        name = self.name_input.text().strip()
        link = self.invite_input.text().strip()
        mode = self.current_link_mode()
        self.completed_cloud_workspace = False

        if mode != CLOUD_LINK_MODE_RENDER and (not email or "@" not in email):
            QMessageBox.warning(self, "需要个人 Gmail", "请填写当前成员自己的 Gmail，用于协作身份和工程编辑锁。")
            return
        if mode != CLOUD_LINK_MODE_RENDER and (not folder or not os.path.isdir(folder)):
            QMessageBox.warning(self, "需要云端文件夹", "请选择 Google Drive 桌面版同步出来的团队工程文件夹。")
            return

        if not self.run_checks():
            QMessageBox.warning(self, "检测未通过", "请先处理检测结果里的红色错误，再完成加入。")
            return

        try:
            if email and "@" in email:
                save_cloud_identity(email, name or email.split("@")[0])
            if folder and os.path.isdir(folder):
                ensure_cloud_workspace(folder)
                update_manifest_from_workspace(folder)
                save_workspace_config(
                    mode=WORKSPACE_MODE_CLOUD,
                    cloud_path=folder,
                    cloud_link=link,
                    cloud_link_mode=mode,
                )
                self.completed_cloud_workspace = True
            else:
                save_workspace_config(cloud_link=link, cloud_link_mode=mode)
        except Exception as e:
            QMessageBox.critical(self, "加入失败", str(e))
            return

        super().accept()


class CloudShareDialog(QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("云端共享设置")
        self.resize(560, 420)
        self.setStyleSheet("QDialog { background-color: #181825; color: #cdd6f4; } QLabel { color: #cdd6f4; }")
        self.identity = get_cloud_identity()
        self.share = get_share_config(workspace)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("云端共享工程")
        title.setStyleSheet("font-size: 22px; font-weight: 900; color: #89b4fa;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.email_input = QLineEdit(self.identity.get("email", ""))
        self.email_input.setPlaceholderText("你的 Google 邮箱，用于编辑锁和协作身份")
        self.name_input = QLineEdit(self.identity.get("name", ""))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("私有：只有自己", "private")
        self.mode_combo.addItem("指定成员可编辑", "members_edit")
        self.mode_combo.addItem("链接可查看", "link_view")
        self.mode_combo.addItem("链接可编辑（谨慎）", "link_edit")
        current_mode = self.share.get("mode", "private")
        idx = self.mode_combo.findData(current_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.members_input = QTextEdit()
        self.members_input.setPlaceholderText("每行一个 Google 邮箱")
        self.members_input.setPlainText("\n".join(self.share.get("members", []) or []))

        self.link_input = QLineEdit(self.share.get("link", ""))
        self.link_input.setPlaceholderText("后续接入 Google Drive API 后自动生成共享链接")

        for widget in (self.email_input, self.name_input, self.mode_combo, self.members_input, self.link_input):
            widget.setStyleSheet("background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; border-radius: 6px; padding: 8px;")

        form.addRow("我的邮箱", self.email_input)
        form.addRow("我的名称", self.name_input)
        form.addRow("共享权限", self.mode_combo)
        form.addRow("成员邮箱", self.members_input)
        form.addRow("共享链接", self.link_input)
        layout.addLayout(form)

        note = QLabel("当前版本会把共享配置写入云端工作区的 .subtitle_cloud/manifest.json。后续 Google 登录/API 接入后，会用这里的配置创建 Drive 权限和共享链接。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #a6adc8; background-color: #11111b; border-radius: 8px; padding: 10px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        email = self.email_input.text().strip()
        name = self.name_input.text().strip()
        members = [line.strip() for line in self.members_input.toPlainText().splitlines() if line.strip()]
        save_cloud_identity(email, name)
        set_share_config(
            self.workspace,
            self.mode_combo.currentData(),
            members=members,
            link=self.link_input.text().strip(),
        )
        super().accept()

class ReelCard(QFrame):
    clicked = pyqtSignal(str) 
    delete_clicked = pyqtSignal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self.scomp_path = project_data.get("project_path", "")
        self.init_ui()

    def init_ui(self):
        self.setFixedSize(200, 280)
        self.setStyleSheet("""
            QFrame { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 12px; }
            QFrame:hover { border: 2px solid #89b4fa; background-color: #313244; }
        """)
        shadow = QGraphicsDropShadowEffect(); shadow.setBlurRadius(15); shadow.setColor(Qt.GlobalColor.black); shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self.lbl_cover = QLabel()
        self.lbl_cover.setFixedSize(200, 210)
        self.lbl_cover.setStyleSheet("background-color: #11111b; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;")
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        cover_rel = self.project_data.get("cover_img", "")
        p_dir = self.project_data.get("project_dir", "")
        cover_path = os.path.join(p_dir, cover_rel) if p_dir and cover_rel else ""
        
        if cover_path and os.path.exists(cover_path):
            pixmap = QPixmap(cover_path)
            self.lbl_cover.setPixmap(pixmap.scaled(200, 210, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_cover.setText("🎬\n无封面\n(在精修室保存后生成)")
            self.lbl_cover.setStyleSheet("background-color: #11111b; color: #45475a; font-size: 16px; font-weight: bold; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;")

        layout.addWidget(self.lbl_cover)

        info_frame = QFrame(); info_frame.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info_frame); info_layout.setContentsMargins(12, 10, 12, 10); info_layout.setSpacing(4)

        title_row = QHBoxLayout()
        p_name = self.project_data.get("project_name", "未命名Reel")
        lbl_title = QLabel(p_name)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cdd6f4;")
        
        btn_del = QPushButton("🗑️")
        btn_del.setFixedSize(24, 24)
        btn_del.setStyleSheet("background: transparent; border: none; color: #f38ba8; font-size: 14px;")
        btn_del.clicked.connect(self._on_del_clicked)

        title_row.addWidget(lbl_title, stretch=1); title_row.addWidget(btn_del)
        info_layout.addLayout(title_row)

        lbl_date = QLabel(self.project_data.get("updated_at", "").split(" ")[0])
        lbl_date.setStyleSheet("font-size: 12px; color: #a6adc8;")
        info_layout.addWidget(lbl_date)

        layout.addWidget(info_frame)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.scomp_path)
        super().mousePressEvent(event)
        
    def _on_del_clicked(self, event):
        self.delete_clicked.emit(self.scomp_path)

class ProjectView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.workspace_cfg = get_workspace_config()
        self.workspace = get_active_workspace()
        if not os.path.exists(self.workspace): os.makedirs(self.workspace)
        self.current_folder = ""
        self.active_lock_project_path = ""
        self.setAcceptDrops(True)
        self.init_ui()
        self.refresh_workspace_controls()
        self.refresh_folders()

    def init_ui(self):
        self.setStyleSheet("QWidget { background-color: #11111b; color: #cdd6f4; font-family: 'Segoe UI', Arial; }")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        title = QLabel("🎬 Reels 视频工程大厅")
        title.setStyleSheet("font-size: 28px; font-weight: 900; color: #cdd6f4;")
        header.addWidget(title)
        
        self.lbl_current = QLabel("当前加载: 无")
        self.lbl_current.setStyleSheet("color: #a6e3a1; font-size: 14px; font-weight: bold; background: #1e1e2e; padding: 5px 15px; border-radius: 15px; margin-left: 20px;")
        header.addWidget(self.lbl_current)

        self.btn_local_workspace = QPushButton("本地版")
        self.btn_cloud_workspace = QPushButton("云端版")
        self.btn_cloud_join = QPushButton("加入云端链接")
        self.btn_pick_cloud_workspace = QPushButton("选择云端文件夹")
        self.btn_cloud_share = QPushButton("共享设置")
        mode_btn_style = """
            QPushButton { background-color: #1e1e2e; color: #a6adc8; border: 1px solid #313244; border-radius: 8px; padding: 7px 12px; font-weight: bold; }
            QPushButton:hover { border-color: #89b4fa; color: #cdd6f4; }
            QPushButton:checked { background-color: #89b4fa; color: #11111b; }
        """
        for btn in (self.btn_local_workspace, self.btn_cloud_workspace):
            btn.setCheckable(True)
            btn.setStyleSheet(mode_btn_style)
        self.btn_cloud_join.setStyleSheet("background-color: #a6e3a1; color: #11111b; border: none; border-radius: 8px; padding: 7px 12px; font-weight: bold;")
        self.btn_pick_cloud_workspace.setStyleSheet("background-color: #313244; color: #f9e2af; border: none; border-radius: 8px; padding: 7px 12px; font-weight: bold;")
        self.btn_cloud_share.setStyleSheet("background-color: #313244; color: #a6e3a1; border: none; border-radius: 8px; padding: 7px 12px; font-weight: bold;")
        self.btn_local_workspace.clicked.connect(lambda: self.switch_workspace_mode(WORKSPACE_MODE_LOCAL))
        self.btn_cloud_workspace.clicked.connect(lambda: self.switch_workspace_mode(WORKSPACE_MODE_CLOUD))
        self.btn_cloud_join.clicked.connect(self.open_cloud_join_wizard)
        self.btn_pick_cloud_workspace.clicked.connect(lambda: self.choose_cloud_workspace(True))
        self.btn_cloud_share.clicked.connect(self.open_cloud_share_settings)
        header.addWidget(self.btn_local_workspace)
        header.addWidget(self.btn_cloud_workspace)
        header.addWidget(self.btn_cloud_join)
        header.addWidget(self.btn_pick_cloud_workspace)
        header.addWidget(self.btn_cloud_share)
        header.addStretch()
        main_layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #313244; width: 2px; }")
        
        # 👑 左侧：项目文件夹列表
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #181825; border-radius: 10px;")
        left_layout = QVBoxLayout(left_panel)
        
        left_header = QHBoxLayout()
        list_title = QLabel("📁 项目列表")
        list_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        left_header.addWidget(list_title)
        
        # 👑 新增：左侧操作按钮
        btn_new_folder = QPushButton("➕"); btn_new_folder.setFixedSize(30, 30)
        btn_new_folder.setStyleSheet("background-color: #313244; color: white; border-radius: 15px;")
        btn_new_folder.setToolTip("新建项目"); btn_new_folder.clicked.connect(self.create_new_folder)
        
        btn_rename_folder = QPushButton("✏️"); btn_rename_folder.setFixedSize(30, 30)
        btn_rename_folder.setStyleSheet("background-color: #313244; color: white; border-radius: 15px;")
        btn_rename_folder.setToolTip("重命名选中项目"); btn_rename_folder.clicked.connect(self.rename_current_folder)

        btn_delete_folder = QPushButton("🗑️"); btn_delete_folder.setFixedSize(30, 30)
        btn_delete_folder.setStyleSheet("background-color: #313244; color: #f38ba8; border-radius: 15px;")
        btn_delete_folder.setToolTip("删除选中项目"); btn_delete_folder.clicked.connect(self.delete_current_folder)

        btn_import_folder = QPushButton("📥"); btn_import_folder.setFixedSize(30, 30)
        btn_import_folder.setStyleSheet("background-color: #313244; color: #a6e3a1; border-radius: 15px;")
        btn_import_folder.setToolTip("导入/拖入外部项目文件夹"); btn_import_folder.clicked.connect(self.import_project_folder_dialog)

        btn_package_folder = QPushButton("📦"); btn_package_folder.setFixedSize(30, 30)
        btn_package_folder.setStyleSheet("background-color: #313244; color: #f9e2af; border-radius: 15px;")
        btn_package_folder.setToolTip("打包当前项目文件夹，方便上传云盘协作"); btn_package_folder.clicked.connect(self.package_current_folder)

        btn_batch_create = QPushButton("🧩"); btn_batch_create.setFixedSize(30, 30)
        btn_batch_create.setStyleSheet("background-color: #313244; color: #b4befe; border-radius: 15px;")
        btn_batch_create.setToolTip("在当前工程文件夹里批量创建 Reel"); btn_batch_create.clicked.connect(self.open_batch_project_builder)

        left_header.addWidget(btn_new_folder)
        left_header.addWidget(btn_rename_folder)
        left_header.addWidget(btn_delete_folder)
        left_header.addWidget(btn_import_folder)
        left_header.addWidget(btn_package_folder)
        left_header.addWidget(btn_batch_create)
        left_layout.addLayout(left_header)

        drop_hint = QLabel("拖入含 .scomp 的项目文件夹可导入\n📦 打包后可上传 Google Drive 共享")
        drop_hint.setStyleSheet("color: #a6adc8; background-color: #11111b; border: 1px dashed #45475a; border-radius: 8px; padding: 10px; font-size: 12px;")
        drop_hint.setWordWrap(True)
        left_layout.addWidget(drop_hint)

        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item { padding: 12px; margin: 4px 0; border-radius: 8px; font-size: 14px; color: #a6adc8; font-weight: bold; }
            QListWidget::item:hover { background-color: #313244; }
            QListWidget::item:selected { background-color: #89b4fa; color: #11111b; }
        """)
        self.folder_list.itemClicked.connect(self.on_folder_selected)
        left_layout.addWidget(self.folder_list)
        
        # 👑 右侧：Reels 分页网格
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: transparent;")
        right_layout = QVBoxLayout(right_panel)
        
        self.lbl_folder_title = QLabel("请在左侧选择一个项目...")
        self.lbl_folder_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #f9e2af; padding-bottom: 10px;")
        right_layout.addWidget(self.lbl_folder_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(25)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_widget)
        right_layout.addWidget(scroll, stretch=1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 1000])
        main_layout.addWidget(splitter, stretch=1)

    def parent_window(self):
        p = self.parent()
        while p is not None and not hasattr(p, "switch_room"): p = p.parent()
        return p

    def open_cloud_join_wizard(self):
        previous_project_dir = self.project_data.get("project_dir", "") if isinstance(self.project_data, dict) else ""
        dialog = CloudJoinWizard(get_workspace_config(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if not getattr(dialog, "completed_cloud_workspace", False):
                QMessageBox.information(
                    self,
                    "云端链接已保存",
                    "已保存 Google Drive 工程链接和使用方式。\n\n仅渲染下载 / 自动复制到我的云盘需要 Google Drive API 授权模块；当前可以先用浏览器打开链接，下载工程包后拖入工程大厅。"
                )
                return
            self.release_active_cloud_lock()
            self.reload_workspace()
            if (
                previous_project_dir
                and os.path.isdir(previous_project_dir)
                and not _is_path_inside(previous_project_dir, self.workspace)
                and self._has_reel_files(previous_project_dir)
            ):
                reply = QMessageBox.question(
                    self,
                    "导入当前工程到云端吗？",
                    "云端团队已经连接。\n\n要顺手把当前本地项目复制进云端工程大厅，并自动上传它引用的素材吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.import_project_folder(previous_project_dir)
            QMessageBox.information(self, "云端团队已连接", "已切换到云端工程大厅。之后打开 Reel 时，软件会用你的 Gmail 写入编辑锁，减少多人覆盖。")

    def refresh_workspace_controls(self):
        self.workspace_cfg = get_workspace_config()
        mode = self.workspace_cfg.get("mode", WORKSPACE_MODE_LOCAL)
        self.btn_local_workspace.setChecked(mode == WORKSPACE_MODE_LOCAL)
        self.btn_cloud_workspace.setChecked(mode == WORKSPACE_MODE_CLOUD)
        cloud_path = self.workspace_cfg.get("cloud_path", "")
        self.btn_pick_cloud_workspace.setVisible(mode == WORKSPACE_MODE_CLOUD)
        self.btn_cloud_share.setVisible(mode == WORKSPACE_MODE_CLOUD)
        if mode == WORKSPACE_MODE_CLOUD:
            label = os.path.basename(cloud_path) if cloud_path else "选择云端文件夹"
            self.btn_pick_cloud_workspace.setText(label)

    def is_cloud_workspace(self):
        return self.workspace_cfg.get("mode") == WORKSPACE_MODE_CLOUD

    def ensure_cloud_identity(self):
        identity = get_cloud_identity()
        if identity.get("email"):
            return identity

        email, ok = QInputDialog.getText(
            self,
            "云端协作身份",
            "请输入你的 Google 邮箱，用于工程编辑锁和协作记录：",
            text=identity.get("email", ""),
        )
        if not ok or not email.strip():
            QMessageBox.information(self, "需要身份", "云端协作需要先填写你的 Google 邮箱。")
            return None

        name = identity.get("name") or email.strip().split("@")[0]
        return save_cloud_identity(email.strip(), name)

    def release_active_cloud_lock(self):
        if not self.active_lock_project_path:
            return
        try:
            release_project_lock(self.workspace, self.active_lock_project_path, get_cloud_identity())
        except Exception:
            pass
        self.active_lock_project_path = ""

    def prepare_cloud_project_lock(self, path):
        if not self.is_cloud_workspace():
            return True

        identity = self.ensure_cloud_identity()
        if not identity:
            return False

        locked, lock = acquire_project_lock(self.workspace, path, identity)
        if not locked:
            owner = lock.get("name") or lock.get("email") or "其他成员"
            expires_at = lock.get("expires_at", "未知时间")
            reply = QMessageBox.warning(
                self,
                "工程正在被编辑",
                f"这个 Reel 当前由 {owner} 锁定编辑。\n锁定到期时间：{expires_at}\n\n仍然打开可能覆盖对方正在同步的修改，要继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.release_active_cloud_lock()
                return True
            return False

        previous_path = self.active_lock_project_path
        if previous_path and os.path.normcase(os.path.abspath(previous_path)) != os.path.normcase(os.path.abspath(path)):
            try:
                release_project_lock(self.workspace, previous_path, identity)
            except Exception:
                pass
        self.active_lock_project_path = path
        return True

    def open_cloud_share_settings(self):
        if not self.is_cloud_workspace():
            return
        ensure_cloud_workspace(self.workspace)
        dialog = CloudShareDialog(self.workspace, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            update_manifest_from_workspace(self.workspace)
            QMessageBox.information(self, "已保存", "云端共享设置已保存到当前云端工作区。")

    def switch_workspace_mode(self, mode):
        if mode != self.workspace_cfg.get("mode"):
            self.release_active_cloud_lock()
        if mode == WORKSPACE_MODE_CLOUD and not self.workspace_cfg.get("cloud_path"):
            if not self.choose_cloud_workspace(switch_to_cloud=True):
                self.refresh_workspace_controls()
                return
        else:
            save_workspace_config(mode=mode)
        self.reload_workspace()

    def choose_cloud_workspace(self, switch_to_cloud=True):
        default_dir = self.workspace_cfg.get("cloud_path") or os.path.expanduser("~")
        previous_project_dir = self.project_data.get("project_dir", "") if isinstance(self.project_data, dict) else ""
        folder = QFileDialog.getExistingDirectory(self, "选择云端协作工作区文件夹", default_dir)
        if not folder:
            return False
        if os.path.abspath(folder) != os.path.abspath(self.workspace):
            self.release_active_cloud_lock()
        os.makedirs(folder, exist_ok=True)
        mode = WORKSPACE_MODE_CLOUD if switch_to_cloud else self.workspace_cfg.get("mode", WORKSPACE_MODE_CLOUD)
        save_workspace_config(mode=mode, cloud_path=folder)
        self.reload_workspace()
        if (
            switch_to_cloud
            and previous_project_dir
            and os.path.isdir(previous_project_dir)
            and not _is_path_inside(previous_project_dir, folder)
            and self._has_reel_files(previous_project_dir)
        ):
            reply = QMessageBox.question(
                self,
                "导入当前工程到云端吗？",
                "检测到当前加载的工程还在本地工作区。\n\n要复制这个项目文件夹到云端工程大厅，并自动把素材放入 assets 等待 Google Drive 同步上传吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.import_project_folder(previous_project_dir)
        return True

    def reload_workspace(self):
        self.workspace_cfg = get_workspace_config()
        self.workspace = get_active_workspace()
        os.makedirs(self.workspace, exist_ok=True)
        self.current_folder = ""
        self.active_lock_project_path = ""
        self.lbl_folder_title.setText("请在左侧选择一个项目...")
        if self.is_cloud_workspace():
            ensure_cloud_workspace(self.workspace)
            update_manifest_from_workspace(self.workspace)
        self.refresh_workspace_controls()
        self.refresh_folders()

    def sync_current_project_label(self):
        p_name = self.project_data.get("project_name", "") if isinstance(self.project_data, dict) else ""
        if p_name: self.lbl_current.setText(f"当前加载 Reel: {p_name}")
        else: self.lbl_current.setText("当前加载 Reel: 无")

    def refresh_folders(self, select_name=None):
        if self.is_cloud_workspace():
            try:
                ensure_cloud_workspace(self.workspace)
                update_manifest_from_workspace(self.workspace)
            except Exception:
                pass
        self.folder_list.clear()
        folders = get_project_folders(self.workspace)
        for f in folders:
            self.folder_list.addItem(f)
            
        if folders:
            # 尝试选中指定的名称
            if select_name:
                items = self.folder_list.findItems(select_name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.folder_list.setCurrentItem(items[0])
                    self.on_folder_selected(items[0])
                    return
            
            # 否则默认选中第一个
            self.folder_list.setCurrentRow(0)
            self.on_folder_selected(self.folder_list.item(0))

    def create_new_folder(self):
        name, ok = QInputDialog.getText(self, "新建项目", "请输入新项目文件夹的名称：")
        if ok and name.strip():
            safe_name = "".join(c for c in name.strip() if c not in r'\/:*?"<>|')
            path = os.path.join(self.workspace, safe_name)
            if not os.path.exists(path):
                os.makedirs(path)
                self.refresh_folders(select_name=safe_name)
            else:
                QMessageBox.warning(self, "提示", "项目文件夹已存在！")

    def _safe_folder_name(self, name):
        safe_name = "".join(c for c in (name or "").strip() if c not in r'\/:*?"<>|')
        return safe_name or "导入项目"

    def _unique_workspace_folder(self, base_name):
        safe_name = self._safe_folder_name(base_name)
        target = os.path.join(self.workspace, safe_name)
        n = 2
        while os.path.exists(target):
            target = os.path.join(self.workspace, f"{safe_name}-{n}")
            n += 1
        return target

    def _has_reel_files(self, folder_path):
        try:
            return any(name.lower().endswith(".scomp") for name in os.listdir(folder_path))
        except Exception:
            return False

    def import_project_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "导入项目文件夹", os.getcwd())
        if folder:
            self.import_project_folder(folder)

    def cloudify_project_folder_assets(self, folder_path):
        copied = 0
        missing = []
        if not self.is_cloud_workspace():
            return copied, missing
        for reel_path in get_reels_in_folder(folder_path):
            try:
                project = load_project(reel_path)
                _, report = sync_project_assets_to_project_dir(project)
                copied += len(report.get("copied", []))
                missing.extend(report.get("missing", []))
            except Exception:
                continue
        return copied, missing

    def import_project_folder(self, folder_path):
        folder_path = os.path.abspath(folder_path)
        if not os.path.isdir(folder_path):
            return
        if not self._has_reel_files(folder_path):
            QMessageBox.warning(self, "无法导入", "这个文件夹里没有找到 .scomp 工程文件。请拖入项目文件夹，或拖入某个 .scomp 所在的文件夹。")
            return

        workspace_abs = os.path.abspath(self.workspace)
        parent_abs = os.path.abspath(os.path.dirname(folder_path))
        if parent_abs == workspace_abs:
            self.refresh_folders(select_name=os.path.basename(folder_path))
            QMessageBox.information(self, "已定位项目", "这个项目已经在工作区里，已为你选中。")
            return

        target = self._unique_workspace_folder(os.path.basename(folder_path))
        try:
            shutil.copytree(folder_path, target)
            copied_assets, missing_assets = self.cloudify_project_folder_assets(target)
            folder_name = os.path.basename(target)
            self.refresh_folders(select_name=folder_name)
            cloud_note = ""
            if copied_assets:
                cloud_note += f"\n\n已自动复制 {copied_assets} 个素材到工程 assets，Google Drive 会继续同步上传。"
            if missing_assets:
                cloud_note += f"\n\n有 {len(missing_assets)} 个素材找不到，其他成员可能无法打开。"
            QMessageBox.information(self, "导入成功", f"项目文件夹已导入工作区：\n{target}{cloud_note}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def package_current_folder(self):
        if not self.current_folder or not os.path.isdir(self.current_folder):
            QMessageBox.warning(self, "提示", "请先选择一个项目文件夹。")
            return

        folder_name = os.path.basename(self.current_folder)
        default_path = os.path.join(self.workspace, f"{folder_name}.scompkg.zip")
        zip_path, _ = QFileDialog.getSaveFileName(self, "打包当前项目文件夹", default_path, "Subtitle Composer 工程包 (*.zip)")
        if not zip_path:
            return
        if not zip_path.lower().endswith(".zip"):
            zip_path += ".zip"

        try:
            self._zip_project_folder(self.current_folder, zip_path)
            QMessageBox.information(self, "打包完成", f"工程包已生成：\n{zip_path}\n\n这个文件可以上传到 Google Drive / 共享云盘，其他人下载解压后可拖回工程大厅。")
        except Exception as e:
            QMessageBox.critical(self, "打包失败", str(e))

    def _zip_project_folder(self, folder_path, zip_path):
        folder_path = os.path.abspath(folder_path)
        zip_path = os.path.abspath(zip_path)
        root_name = os.path.basename(folder_path)
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(folder_path):
                for filename in files:
                    file_path = os.path.abspath(os.path.join(root, filename))
                    if file_path == zip_path:
                        continue
                    rel_path = os.path.relpath(file_path, folder_path)
                    arc_name = os.path.join(root_name, rel_path)
                    zf.write(file_path, arc_name)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for url in urls:
            path = url.toLocalFile()
            if os.path.isdir(path) or path.lower().endswith(".scomp"):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for url in urls:
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.import_project_folder(path)
                event.acceptProposedAction()
                return
            if path.lower().endswith(".scomp"):
                self.import_project_folder(os.path.dirname(path))
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    # 👑 新增：重命名项目
    def rename_current_folder(self):
        if not self.current_folder: return
        old_name = os.path.basename(self.current_folder)
        new_name, ok = QInputDialog.getText(self, "重命名项目", "请输入新的项目名称：", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            safe_name = "".join(c for c in new_name.strip() if c not in r'\/:*?"<>|')
            new_path = os.path.join(self.workspace, safe_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "提示", "该项目名称已存在！")
                return
            try:
                if self.active_lock_project_path and os.path.abspath(self.active_lock_project_path).startswith(os.path.abspath(self.current_folder) + os.sep):
                    self.release_active_cloud_lock()
                os.rename(self.current_folder, new_path)
                
                # 如果正在加载的 Reel 刚好在这个文件夹里，修复它的内部路径映射
                if self.project_data and self.project_data.get("project_dir", "") == self.current_folder:
                    old_scomp = self.project_data.get("project_path")
                    new_scomp = old_scomp.replace(self.current_folder, new_path)
                    if os.path.exists(new_scomp):
                        self.project_data = load_project(new_scomp)
                        self.sync_current_project_to_main()
                        self.sync_current_project_label()

                self.current_folder = new_path
                self.refresh_folders(select_name=safe_name)
            except Exception as e:
                QMessageBox.critical(self, "重命名失败", str(e))

    # 👑 新增：删除项目
    def delete_current_folder(self):
        if not self.current_folder: return
        folder_name = os.path.basename(self.current_folder)
        reply = QMessageBox.warning(self, '⚠️ 警告', f'确认彻底删除项目【{folder_name}】及其所有内容吗？\n此操作不可逆！', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.active_lock_project_path and os.path.abspath(self.active_lock_project_path).startswith(os.path.abspath(self.current_folder) + os.sep):
                    self.release_active_cloud_lock()
                shutil.rmtree(self.current_folder)
                
                # 如果正在加载的 Reel 被删了，清理大盘数据
                if self.project_data and self.project_data.get("project_dir", "") == self.current_folder:
                    self.project_data = {}
                    self.sync_current_project_label()
                    self.sync_current_project_to_main()
                
                self.current_folder = ""
                self.lbl_folder_title.setText("请在左侧选择一个项目...")
                self.refresh_folders()
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def on_folder_selected(self, item):
        if not item: return
        self.current_folder = os.path.join(self.workspace, item.text())
        self.lbl_folder_title.setText(f"📁 {item.text()} 下的 Reels")
        self.refresh_reels_grid()

    def refresh_reels_grid(self):
        for i in reversed(range(self.grid_layout.count())): 
            widget = self.grid_layout.itemAt(i).widget()
            if widget: widget.deleteLater()

        if not self.current_folder or not os.path.exists(self.current_folder): 
            return
        
        reels_paths = get_reels_in_folder(self.current_folder)
        col_count = 5; row, col = 0, 0

        # 新建 Reel 卡片
        new_card = QFrame()
        new_card.setFixedSize(200, 280)
        new_card.setStyleSheet("QFrame { background-color: transparent; border: 2px dashed #45475a; border-radius: 12px; } QFrame:hover { border-color: #a6e3a1; background-color: #1e1e2e; }")
        new_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_layout = QVBoxLayout(new_card)
        new_lbl = QLabel("➕\n新建 Reel")
        new_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_lbl.setStyleSheet("color: #a6e3a1; font-size: 20px; font-weight: bold; border: none;")
        new_layout.addWidget(new_lbl)
        new_card.mousePressEvent = lambda e: self.create_new_reel() if e.button() == Qt.MouseButton.LeftButton else None
        
        self.grid_layout.addWidget(new_card, row, col)
        col += 1

        batch_card = QFrame()
        batch_card.setFixedSize(200, 280)
        batch_card.setStyleSheet("QFrame { background-color: transparent; border: 2px dashed #b4befe; border-radius: 12px; } QFrame:hover { border-color: #f9e2af; background-color: #1e1e2e; }")
        batch_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        batch_layout = QVBoxLayout(batch_card)
        batch_lbl = QLabel("🧩\n批量创建 Reel")
        batch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_lbl.setStyleSheet("color: #b4befe; font-size: 20px; font-weight: bold; border: none;")
        batch_layout.addWidget(batch_lbl)
        batch_card.mousePressEvent = lambda e: self.open_batch_project_builder() if e.button() == Qt.MouseButton.LeftButton else None

        self.grid_layout.addWidget(batch_card, row, col)
        col += 1

        for path in reels_paths:
            try:
                p_data = load_project(path)
                card = ReelCard(p_data)
                card.clicked.connect(self.load_and_enter_project)
                card.delete_clicked.connect(self.delete_reel)
                
                self.grid_layout.addWidget(card, row, col)
                col += 1
                if col >= col_count: col = 0; row += 1
            except Exception: pass

    def create_new_reel(self):
        if not self.current_folder: return
        if self.is_cloud_workspace() and not self.ensure_cloud_identity():
            return
        name, ok = QInputDialog.getText(self, "新建 Reel", "给你的新 Reel 起个名字：")
        if ok and name.strip():
            try:
                self.project_data = create_reel(self.current_folder, name.strip(), "edit_room")
                project_path = self.project_data.get("project_path", "")
                if self.is_cloud_workspace() and project_path and not self.prepare_cloud_project_lock(project_path):
                    return
                self.sync_current_project_to_main()
                self.refresh_reels_grid()
                self.sync_current_project_label()
                parent = self.parent_window()
                if parent: parent.switch_room(1)
            except Exception as e:
                QMessageBox.critical(self, "创建失败", str(e))

    def open_batch_project_builder(self):
        if not self.current_folder or not os.path.isdir(self.current_folder):
            QMessageBox.warning(self, "请选择工程", "请先在左侧选择一个工程文件夹，或先新建一个工程。")
            return
        parent = self.parent_window()
        if not parent or not hasattr(parent, "room_batch"):
            QMessageBox.warning(self, "无法打开", "没有找到批量创建房间。")
            return
        if self.is_cloud_workspace() and not self.ensure_cloud_identity():
            return
        parent.room_batch.prepare_project_builder(self.current_folder, os.path.basename(self.current_folder))
        parent.switch_room(3)

    def load_and_enter_project(self, path):
        if not self.prepare_cloud_project_lock(path):
            return
        try:
            self.project_data = load_project(path)
            if self.is_cloud_workspace():
                self.project_data, report = sync_project_assets_to_project_dir(self.project_data)
                if report.get("copied"):
                    QMessageBox.information(
                        self,
                        "素材已云端化",
                        f"已自动复制 {len(report['copied'])} 个本机素材到当前工程 assets。\nGoogle Drive 会在后台继续同步上传。"
                    )
            self.sync_current_project_to_main()
            self.sync_current_project_label()
            parent = self.parent_window()
            if parent: parent.switch_room(1) 
        except Exception as e:
            QMessageBox.critical(self, "载入失败", str(e))

    def delete_reel(self, path):
        reply = QMessageBox.warning(self, '⚠️ 警告', '确认删除该 Reel 吗？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.active_lock_project_path and os.path.normcase(os.path.abspath(self.active_lock_project_path)) == os.path.normcase(os.path.abspath(path)):
                    self.release_active_cloud_lock()
                os.remove(path)
                cover_path = path.replace(".scomp", "_cover.jpg")
                if os.path.exists(cover_path): os.remove(cover_path)
                self.refresh_reels_grid()
                
                # 如果删除的刚好是当前加载的，则清空引用
                if self.project_data.get("project_path") == path:
                    self.project_data = {}
                    self.sync_current_project_label()
                    self.sync_current_project_to_main()
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def sync_current_project_to_main(self):
        parent = self.parent_window()
        if not parent: return
        parent.project = self.project_data
        if hasattr(parent, "reload_rooms_from_project"):
            parent.reload_rooms_from_project()
