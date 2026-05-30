import json
import os

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QUrl
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app_theme import apply_tinted_styles
from project_io import update_room_state
from ui_components import default_design_room_state, normalize_design_room_state
from web_asset_loader import load_web_tool_page


def _json(data):
    return json.dumps(data, ensure_ascii=False)


class DesignBridge(QObject):
    event = pyqtSignal(str)

    def __init__(self, room):
        super().__init__(room)
        self.room = room

    def emit_event(self, event_type, **payload):
        payload["type"] = event_type
        self.event.emit(_json(payload))

    @pyqtSlot(result=str)
    def getState(self):
        return _json(self.room.export_state())

    @pyqtSlot(str)
    def saveState(self, payload):
        try:
            self.room.state = normalize_design_room_state(json.loads(payload or "{}"))
            self.room.save_to_project(silent=True)
        except Exception as e:
            self.emit_event("error", message=f"设计数据保存失败: {e}")


class DesignView(QWidget):
    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.state = default_design_room_state()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.fallback_label = QLabel("设计房间正在加载...")
        self.fallback_label.setStyleSheet("color:#a6adc8; background:#11111b; padding:12px;")
        self.fallback_label.hide()

        self.view = QWebEngineView()
        layout.addWidget(self.view, stretch=1)
        layout.addWidget(self.fallback_label)

        self.bridge = DesignBridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("designBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.load_from_project(self.project_data)
        self.load_web_editor()

    def parent_window(self):
        parent = self.parent()
        while parent is not None and not hasattr(parent, "project"):
            parent = parent.parent()
        return parent

    def edit_host(self):
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "update_floating_subtitle"):
                return parent
            parent = parent.parent()
        parent_window = self.parent_window()
        host = getattr(parent_window, "room_edit", None) if parent_window is not None else None
        if host is not None and hasattr(host, "update_floating_subtitle"):
            return host
        return None

    def load_web_editor(self):
        fallback = """
        <!doctype html>
        <html><head><meta charset="utf-8"></head>
        <body style="margin:0;background:#11111b;color:#cdd6f4;font-family:Segoe UI,Arial,sans-serif;">
          <div style="padding:24px;">
            <h2>设计房间未构建</h2>
            <p>请运行 web_tools 构建任务生成 Canva 式设计编辑器。</p>
          </div>
        </body></html>
        """
        ok = load_web_tool_page(self.view, "design_editor", fallback, os.getcwd())
        if not ok:
            self.fallback_label.show()

    def load_from_project(self, project_data):
        self.project_data = project_data or {}
        room_state = self.project_data.get("room_state", {}).get("design_room", {})
        self.state = normalize_design_room_state(room_state)
        self.send_state_to_web()

    def send_state_to_web(self):
        payload = _json(self.export_state()).replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        self.view.page().runJavaScript(
            f"if (window.designEditorSetState) window.designEditorSetState(`{payload}`);"
        )

    def export_state(self):
        return normalize_design_room_state(self.state)

    def save_to_project(self, silent=False):
        parent = self.parent_window()
        project_data = getattr(parent, "project", None) if parent else None
        project_data = project_data or self.project_data or {"project_type": "edit_room"}
        project_data = update_room_state(project_data, "design_room", self.export_state())
        self.project_data = project_data
        if parent is not None and hasattr(parent, "project"):
            parent.project = project_data
        host = self.edit_host()
        if host is not None:
            host.project_data = project_data
            host.last_render_hash = None
            QTimer.singleShot(0, host.update_floating_subtitle)
            if hasattr(host, "status_lbl") and not silent:
                host.status_lbl.setText("🎨 设计插件已同步到精修预览。")
        return project_data

    def apply_theme(self, colors, theme_key=None):
        apply_tinted_styles(self, colors)
