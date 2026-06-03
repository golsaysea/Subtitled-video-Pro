# ==========================================
# 文件名: timeline_engine.py (无损升级版：6轨道平铺引擎)
# ==========================================
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsItem, QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QObject, pyqtSignal, pyqtSlot, QPointF
from PyQt6.QtGui import QBrush, QColor, QPen, QPainter, QFont
import os

TRACK_H = 26
HEADER_H = 22
TRACK_COUNT = 8
SNAP_STEP_SECONDS = 0.05


def _format_time(seconds):
    seconds = max(0.0, float(seconds or 0.0))
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    if seconds < 60:
        return f"{secs:04.1f}s"
    return f"{minutes:02d}:{secs:04.1f}"

def _timeline_colors(controller=None):
    c = getattr(controller, "_theme_colors", None) or {}
    return {
        "bg": c.get("bg", "#11111b"),
        "panel": c.get("panel", "#181825"),
        "panel_2": c.get("panel_2", "#1e1e2e"),
        "text": c.get("text", "#cdd6f4"),
        "muted": c.get("muted", "#a6adc8"),
        "accent": c.get("accent", "#89b4fa"),
        "accent_2": c.get("accent_2", "#a6e3a1"),
        "warn": c.get("warn", "#f9e2af"),
        "danger": c.get("danger", "#f38ba8"),
        "border": c.get("border", "#313244"),
        "input": c.get("input", "#121628"),
        "selected_text": c.get("selected_text", "#11111b"),
        "hint": c.get("hint", "#151a2e"),
    }


class TimelineHeader(QWidget):
    def __init__(self, parent=None, controller=None):
        super().__init__(parent); self.controller = controller; self.setFixedWidth(96); self.setMinimumHeight(HEADER_H + TRACK_H * TRACK_COUNT + 12); self.TRACK_H = TRACK_H
        
    def paintEvent(self, event):
        c = _timeline_colors(self.controller)
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.fillRect(self.rect(), QColor(c["bg"]))
        painter.setPen(QColor(c["border"])); painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height()); painter.drawLine(0, HEADER_H, self.width(), HEADER_H)
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold)); painter.setPen(QColor(c["muted"]))
        painter.drawText(QRectF(12, 0, self.width() - 24, HEADER_H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "TRACKS")

        tracks = [
            ("T3", "标题", c["warn"]),
            ("T2", "正文", c["warn"]),
            ("T1", "蒙版", c["warn"]),
            ("V1", "画面", c["accent"]),
            ("A1", "原声/配乐", c["accent_2"]),
            ("A2", "配音", c["accent_2"]),
            ("D1", "设计", "#cba6f7"),
            ("D2", "装饰", "#f5c2e7"),
        ]
        for idx, (code, label, color) in enumerate(tracks):
            y = HEADER_H + idx * self.TRACK_H
            bg = QColor(c["panel_2"] if idx % 2 else c["panel"])
            bg.setAlpha(220)
            painter.fillRect(QRectF(0, y, self.width(), self.TRACK_H), bg)
            painter.setPen(QPen(QColor(c["border"]), 1))
            painter.drawLine(0, y, self.width(), y)
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(8, y + 9, 5, self.TRACK_H - 18), 3, 3)
            painter.setPen(QColor(color))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(QRectF(22, y + 3, 30, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, code)
            painter.setPen(QColor(c["muted"]))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(QRectF(22, y + 15, 66, 10), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

    def mousePressEvent(self, event):
        if not self.controller: return
        y = event.pos().y()
        if HEADER_H <= y < HEADER_H + self.TRACK_H: self.controller.select_entire_track("sub", 0) 
        elif HEADER_H + self.TRACK_H <= y < HEADER_H + self.TRACK_H * 2: self.controller.select_entire_track("sub", 1) 
        elif HEADER_H + self.TRACK_H * 2 <= y < HEADER_H + self.TRACK_H * 3: self.controller.select_entire_track("sub", 2) 
        elif HEADER_H + self.TRACK_H * 6 <= y < HEADER_H + self.TRACK_H * 8: self.controller.select_entire_track("design", 6 if y < HEADER_H + self.TRACK_H * 7 else 7)

class ClipSignals(QObject):
    clicked = pyqtSignal(str, int) 
    moved = pyqtSignal(str, int, float, float, int)
    drag_finished = pyqtSignal(str, int, float)

class ClipItem(QGraphicsRectItem):
    def __init__(self, clip_type, idx, start_t, end_t, track_idx, pps, text="", media_dur=0):
        self.clip_type = clip_type; self.idx = idx; self.pps = pps; self.track_idx = track_idx; self.text = text; self.media_dur = media_dur; self.signals = ClipSignals()
        
        # 👑 动态坐标定位
        if clip_type == "sub": y_pos = HEADER_H + self.track_idx * TRACK_H
        elif clip_type == "video": y_pos = HEADER_H + TRACK_H * 3
        elif clip_type == "music": y_pos = HEADER_H + TRACK_H * 4 + 5
        elif clip_type == "design": y_pos = HEADER_H + max(6, min(7, self.track_idx)) * TRACK_H
        else: y_pos = HEADER_H + TRACK_H * 5 + 5 # 假设独立的配音永远在最底下A2
        
        x = start_t * pps; w = max(5.0, (end_t - start_t) * pps)
        super().__init__(0, 0, w, TRACK_H - 4); self.setPos(x, y_pos + 2)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        if clip_type == "video": self.base_color = QColor("#89b4fa")
        elif clip_type in ("audio", "music"): self.base_color = QColor("#a6e3a1")
        elif clip_type == "design": self.base_color = QColor("#cba6f7")
        else: self.base_color = QColor("#f9e2af")
        self.resize_mode = None; self.start_rect = None; self.start_scene_pos = None

    def _controller(self):
        return self.scene().views()[0].controller if self.scene() and self.scene().views() else None

    def _edit_mode_enabled(self):
        if self.clip_type == "music":
            return False
        controller = self._controller()
        return bool(getattr(controller, "edit_mode", False))

    def _snap_time(self, seconds):
        controller = self._controller()
        if controller and getattr(controller, "timeline_snap_enabled", True):
            return round(float(seconds) / SNAP_STEP_SECONDS) * SNAP_STEP_SECONDS
        return float(seconds)

    def hoverMoveEvent(self, event):
        if not self._edit_mode_enabled():
            self.setCursor(Qt.CursorShape.ArrowCursor)
            super().hoverMoveEvent(event)
            return
        pos_x = event.pos().x(); margin = 20 
        if pos_x <= margin or pos_x >= self.rect().width() - margin: self.setCursor(Qt.CursorShape.SizeHorCursor)
        else: self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and not self._edit_mode_enabled():
            return self.pos()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            # 👑 允许字幕跨跃 3 个文字轨道
            if self.clip_type == "sub":
                if new_pos.y() < HEADER_H + TRACK_H: new_pos.setY(HEADER_H + 2); self.track_idx = 0
                elif new_pos.y() < HEADER_H + TRACK_H * 2: new_pos.setY(HEADER_H + TRACK_H + 2); self.track_idx = 1
                else: new_pos.setY(HEADER_H + TRACK_H * 2 + 2); self.track_idx = 2
            elif self.clip_type == "design":
                if new_pos.y() < HEADER_H + TRACK_H * 7:
                    new_pos.setY(HEADER_H + TRACK_H * 6 + 2); self.track_idx = 6
                else:
                    new_pos.setY(HEADER_H + TRACK_H * 7 + 2); self.track_idx = 7
            else: new_pos.setY(self.y())
            if new_pos.x() < 0: new_pos.setX(0)
            controller = self._controller()
            if controller and getattr(controller, "timeline_snap_enabled", True):
                snapped_x = self._snap_time(new_pos.x() / self.pps) * self.pps
                new_pos.setX(max(0.0, snapped_x))
            return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not self.resize_mode: self.emit_moved()
        return super().itemChange(change, value)

    def emit_moved(self):
        new_start = self._snap_time(self.scenePos().x() / self.pps)
        new_end = self._snap_time(new_start + (self.rect().width() / self.pps))
        if new_end <= new_start:
            new_end = new_start + SNAP_STEP_SECONDS
        self.signals.moved.emit(self.clip_type, self.idx, new_start, new_end, self.track_idx)

    def mousePressEvent(self, event):
        self.setZValue(100); self.setSelected(True); self.signals.clicked.emit(self.clip_type, self.idx)
        if not self._edit_mode_enabled():
            self.resize_mode = None
            event.accept()
            return
        pos_x = event.pos().x(); margin = 20
        if pos_x <= margin: self.resize_mode = "left"
        elif pos_x >= self.rect().width() - margin: self.resize_mode = "right"
        else: self.resize_mode = None
        self.start_rect = self.rect(); self.start_scene_pos = self.scenePos()
        if not self.resize_mode: super().mousePressEvent(event)
        else: event.accept()

    def mouseMoveEvent(self, event):
        if not self._edit_mode_enabled():
            event.accept()
            return
        if self.resize_mode:
            scene_dx = event.scenePos().x() - event.buttonDownScenePos(Qt.MouseButton.LeftButton).x()
            if self.resize_mode == "left":
                new_w = self.start_rect.width() - scene_dx
                if new_w >= 2.0 and self.start_scene_pos.x() + scene_dx >= 0:
                    self.setPos(self.start_scene_pos.x() + scene_dx, self.start_scene_pos.y()); self.setRect(0, 0, new_w, self.start_rect.height()); self.emit_moved()
            elif self.resize_mode == "right":
                new_w = self.start_rect.width() + scene_dx
                if new_w >= 2.0: self.setRect(0, 0, new_w, self.start_rect.height()); self.emit_moved()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.resize_mode = None; self.setZValue(1)
        super().mouseReleaseEvent(event)
        final_start = self.scenePos().x() / self.pps
        self.signals.drag_finished.emit(self.clip_type, self.idx, final_start)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        controller = self.scene().views()[0].controller if self.scene() and self.scene().views() else None
        c = _timeline_colors(controller)
        clip_color = c["accent"] if self.clip_type == "video" else c["warn"] if self.clip_type == "music" else c["accent_2"] if self.clip_type == "audio" else "#cba6f7" if self.clip_type == "design" else c["warn"]
        fill = QColor(clip_color)
        fill.setAlpha(220 if self.isSelected() else 178)
        edge = QColor(c["danger"] if self.isSelected() else c["border"])
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(edge, 2 if self.isSelected() else 1))
        painter.drawRoundedRect(self.rect(), 6, 6)
        shine = QColor("#ffffff")
        shine.setAlpha(34 if self.isSelected() else 18)
        painter.fillRect(self.rect().adjusted(1, 1, -1, -self.rect().height() * 0.58), shine)
        if self.clip_type in ("video", "music") and self.media_dur > 0:
            loop_w = self.media_dur * self.pps; curr_x = loop_w; painter.setPen(QPen(QColor(c["selected_text"]), 2, Qt.PenStyle.DashLine))
            while curr_x < self.rect().width(): painter.drawLine(QPointF(curr_x, 0), QPointF(curr_x, self.rect().height())); curr_x += loop_w
        if self.clip_type == "audio" and hasattr(controller, 'a_wave_pixmap'):
            wave = controller.a_wave_pixmap
            if wave and not wave.isNull(): painter.setClipRect(self.rect()); painter.drawPixmap(self.rect(), wave, QRectF(wave.rect())); painter.setClipping(False)
        elif self.clip_type == "video" and hasattr(controller, 'video_thumbs'):
            thumbs = controller.video_thumbs
            if thumbs:
                thumb_w = (TRACK_H - 4) * (16/9); curr_x = 0; idx = self.idx % len(thumbs)
                painter.setClipRect(self.rect())
                while curr_x < self.rect().width() and idx < len(thumbs):
                    if thumbs[idx] and not thumbs[idx].isNull(): painter.drawPixmap(QRectF(curr_x, 0, thumb_w, TRACK_H - 4), thumbs[idx], QRectF(thumbs[idx].rect()))
                    curr_x += thumb_w; idx += 1
                painter.setClipping(False)
        if self.clip_type == "video" and controller:
            clips = controller.state.get("video_clips", [])
            if 0 <= self.idx < len(clips) and (clips[self.idx].get("transition") or {}).get("type") == "fade":
                painter.setBrush(QBrush(QColor(c["accent_2"])))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(4, 4, 24, 14), 4, 4)
                painter.setPen(QColor(c["selected_text"]))
                painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                painter.drawText(QRectF(4, 3, 24, 14), Qt.AlignmentFlag.AlignCenter, "FX")
        handle_pen = QPen(QColor(c["selected_text"]), 1)
        handle_pen.setColor(QColor(c["selected_text"]))
        painter.setPen(handle_pen)
        for hx in (7, max(7, int(self.rect().width()) - 8)):
            painter.drawLine(QPointF(hx, 7), QPointF(hx, self.rect().height() - 7))

        label_color = QColor(c["selected_text"] if self.clip_type != "sub" else c["bg"])
        label_color.setAlpha(235)
        painter.setPen(QPen(label_color))
        painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        duration = self.rect().width() / max(0.001, self.pps)
        label = self.text.replace("\n", " ").strip()
        if len(label) > 42:
            label = label[:39] + "..."
        painter.drawText(self.rect().adjusted(12, 2, -8, -10), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        painter.setFont(QFont("Consolas", 6))
        painter.drawText(self.rect().adjusted(12, 12, -8, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{_format_time(duration)}")

class PlayheadItem(QGraphicsItem):
    def __init__(self, height, controller=None):
        super().__init__(); self.line_height = height; self.controller = controller; self.setZValue(1000)
    def boundingRect(self): return QRectF(-10, 0, 20, self.line_height)
    def paint(self, painter, option, widget=None):
        c = _timeline_colors(self.controller)
        painter.setPen(QPen(QColor(c["danger"]), 2)); painter.drawLine(0, 0, 0, int(self.line_height)); painter.setBrush(QBrush(QColor(c["danger"]))); painter.drawPolygon([QPointF(-6, 0), QPointF(6, 0), QPointF(0, 10)])

class AdvancedTimeline(QGraphicsView):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #11111b; border: none;")
        self.setMinimumHeight(HEADER_H + TRACK_H * TRACK_COUNT + 12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QGraphicsView { background-color: #11111b; border: none; }
            QScrollBar:horizontal { background: #11131f; height: 10px; border: none; }
            QScrollBar::handle:horizontal { background: #45475a; min-width: 32px; border-radius: 5px; }
            QScrollBar::handle:horizontal:hover { background: #89b4fa; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        """)
        self.playhead = PlayheadItem(HEADER_H + TRACK_H * TRACK_COUNT + 12, controller)
        self.scene.addItem(self.playhead)
        self.is_scrubbing = False

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect); pps = self.controller.zoom_factor; dur = max(10.0, self.controller.state.get("duration", 10.0)); w = max(rect.width(), dur * pps + 240); scene_h = HEADER_H + TRACK_H * TRACK_COUNT + 12; self.scene.setSceneRect(0, 0, w, scene_h)
        c = _timeline_colors(self.controller)
        painter.fillRect(QRectF(0, 0, w, HEADER_H), QColor(c["panel"]))
        painter.setPen(QPen(QColor(c["border"]), 1))
        painter.drawLine(QPointF(0, HEADER_H), QPointF(w, HEADER_H))

        y_offsets = [HEADER_H + TRACK_H * i for i in range(TRACK_COUNT)]
        colors = [c["panel"] if i % 2 == 0 else c["panel_2"] for i in range(TRACK_COUNT)]
        for y, color in zip(y_offsets, colors):
            lane = QColor(color)
            lane.setAlpha(228)
            painter.fillRect(QRectF(0, y, w, TRACK_H), lane)
            painter.setPen(QPen(QColor(c["border"]), 1))
            painter.drawLine(QPointF(0, y), QPointF(w, y))

        if pps >= 180:
            major_step, minor_step = 0.5, 0.1
        elif pps >= 90:
            major_step, minor_step = 1.0, 0.25
        elif pps >= 45:
            major_step, minor_step = 2.0, 0.5
        elif pps >= 22:
            major_step, minor_step = 5.0, 1.0
        else:
            major_step, minor_step = 10.0, 2.0

        t = 0.0
        while t <= dur + 2:
            x = t * pps
            is_major = abs((t / major_step) - round(t / major_step)) < 0.001
            line_color = QColor(c["border"] if is_major else c["hint"])
            line_color.setAlpha(170 if is_major else 92)
            painter.setPen(QPen(line_color, 1))
            painter.drawLine(QPointF(x, HEADER_H), QPointF(x, scene_h))
            if is_major:
                painter.setPen(QColor(c["muted"]))
                painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                painter.drawText(QRectF(x + 5, 1, 78, HEADER_H - 4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, _format_time(t))
                painter.drawLine(QPointF(x, HEADER_H - 12), QPointF(x, HEADER_H))
            else:
                painter.drawLine(QPointF(x, HEADER_H - 6), QPointF(x, HEADER_H))
            t += minor_step

        painter.setPen(QPen(QColor(c["border"]), 2)); painter.drawLine(QPointF(0, HEADER_H+TRACK_H*4), QPointF(w, HEADER_H+TRACK_H*4))
        
        v_wave = getattr(self.controller, 'v_wave_pixmap', None); clips = self.controller.state.get("video_clips", [])
        if v_wave and not v_wave.isNull() and clips:
            min_x = min([clip["start"] for clip in clips]) * pps; max_x = max([clip["end"] for clip in clips]) * pps; t_rect = QRectF(min_x, HEADER_H + TRACK_H*4 + 5, max_x - min_x, TRACK_H - 4); painter.fillRect(t_rect, QColor(c["hint"])); painter.setClipRect(t_rect); painter.drawPixmap(t_rect, v_wave, QRectF(v_wave.rect())); painter.setClipping(False)

    def sync_from_controller(self):
        for item in self.scene.items():
            if isinstance(item, ClipItem): self.scene.removeItem(item)
        pps = self.controller.zoom_factor
        
        # 👑 修复渲染轨道映射
        for i, clip in enumerate(self.controller.state.get("video_clips", [])):
            clip_name = os.path.basename(clip.get("path", "")) or "复合片段"
            item = ClipItem("video", i, clip["start"], clip["end"], 3, pps, f"V1 · {clip_name}", media_dur=clip.get("dur", 0)); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, bool(getattr(self.controller, "edit_mode", False)))
            if self.controller.selected_track == "video" and self.controller.current_v_idx == i: item.setSelected(True)
            self.scene.addItem(item)
            
        if self.controller.state.get("audio_path"):
            audio_name = os.path.basename(self.controller.state.get("audio_path", "")) or "独立配音"
            a_trim = self.controller.state.get("a_trim", [0, 10]); item = ClipItem("audio", 0, a_trim[0], a_trim[1], 5, pps, f"A2 · {audio_name}"); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished); self.scene.addItem(item)

        if self.controller.state.get("music_path"):
            music_name = os.path.basename(self.controller.state.get("music_path", "")) or "配乐"
            state = self.controller.state
            try:
                music_actual_dur = float(state.get("music_dur", 0.0) or 0.0)
            except Exception:
                music_actual_dur = 0.0
            try:
                music_timeline_dur = float(state.get("music_match_duration", 0.0) or 0.0)
            except Exception:
                music_timeline_dur = 0.0
            if music_timeline_dur <= 0:
                music_timeline_dur = float(state.get("duration", 1.0) or 1.0)
            music_timeline_dur = max(0.1, music_timeline_dur)
            item = ClipItem("music", 0, 0.0, music_timeline_dur, 4, pps, f"M1 · {music_name}", media_dur=music_actual_dur)
            item.signals.clicked.connect(self.on_clip_clicked)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            if self.controller.selected_track == "music":
                item.setSelected(True)
            self.scene.addItem(item)
            
        for i, s in enumerate(self.controller.state.get("subs_data", [])):
            trk_idx = s.get('track', 1); item = ClipItem("sub", i, float(s.get('start', 0)), float(s.get('end', 1)), trk_idx, pps, f"T{3 - trk_idx} · {s.get('text', '').replace(chr(10), ' ')}"); item.signals.clicked.connect(self.on_clip_clicked); item.signals.moved.connect(self.on_clip_moved); item.signals.drag_finished.connect(self.on_clip_drag_finished)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, bool(getattr(self.controller, "edit_mode", False)))
            if i == self.controller.current_selected_idx: item.setSelected(True)
            self.scene.addItem(item)

        if hasattr(self.controller, "design_timeline_layers"):
            for i, layer in enumerate(self.controller.design_timeline_layers()):
                start_t = float(layer.get("start", 0.0) or 0.0)
                end_t = float(layer.get("end", 0.0) or 0.0)
                if end_t <= start_t:
                    end_t = max(start_t + 0.2, float(layer.get("_page_duration", 5.0) or 5.0))
                track_idx = int(layer.get("timelineTrack", 6) or 6)
                label = layer.get("name") or ("文字" if layer.get("type") == "text" else "图层")
                item = ClipItem("design", i, start_t, end_t, track_idx, pps, f"D{track_idx - 5} · {label}")
                item.signals.clicked.connect(self.on_clip_clicked)
                item.signals.moved.connect(self.on_clip_moved)
                item.signals.drag_finished.connect(self.on_clip_drag_finished)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, bool(getattr(self.controller, "edit_mode", False)))
                if getattr(self.controller, "selected_track", "") == "design" and layer.get("id") == getattr(self.controller, "selected_design_layer_id", ""):
                    item.setSelected(True)
                self.scene.addItem(item)
        self.update_playhead(self.controller.current_play_time); self.scene.update()

    def update_playhead(self, time_sec):
        pps = self.controller.zoom_factor; self.playhead.setPos(time_sec * pps, 0); view_width = self.viewport().width(); head_x = time_sec * pps; scroll_bar = self.horizontalScrollBar()
        if head_x > scroll_bar.value() + view_width - 50: scroll_bar.setValue(int(head_x - view_width + 100))

    @pyqtSlot(str, int)
    def on_clip_clicked(self, clip_type, idx):
        if clip_type == "sub": self.controller.current_selected_idx = idx
        elif clip_type == "video": self.controller.current_v_idx = idx
        elif clip_type == "music":
            self.controller.selected_track = "music"
            self.controller.show_canvas_context_toolbar("audio")
            self.controller._update_workspace_status()
            return
        elif clip_type == "design" and hasattr(self.controller, "select_design_layer_by_index"):
            self.controller.select_design_layer_by_index(idx)
            return
        self.controller.switch_inspector(clip_type)

    @pyqtSlot(str, int, float, float, int)
    def on_clip_moved(self, clip_type, idx, new_start, new_end, new_track):
        if not getattr(self.controller, "edit_mode", False):
            return
        if clip_type == "sub":
            sub = self.controller.state["subs_data"][idx]
            old_start = float(sub.get("start", 0)); old_end = float(sub.get("end", 1))
            old_dur = max(0.001, old_end - old_start); new_dur = max(0.001, new_end - new_start)

            words = sub.get("words", [])
            for w in words:
                rel_s = (float(w.get("start", 0)) - old_start) / old_dur
                rel_e = (float(w.get("end", 1)) - old_start) / old_dur
                w["start"] = new_start + rel_s * new_dur; w["end"] = new_start + rel_e * new_dur

            sub["start"] = new_start; sub["end"] = new_end; sub["track"] = new_track
            
            if hasattr(self.controller, 'ui_entries') and 0 <= idx < len(self.controller.ui_entries):
                entry_dict = self.controller.ui_entries[idx]
                if "start_spin" in entry_dict and "end_spin" in entry_dict:
                    entry_dict["start_spin"].blockSignals(True); entry_dict["end_spin"].blockSignals(True)
                    entry_dict["start_spin"].setValue(new_start); entry_dict["end_spin"].setValue(new_end)
                    entry_dict["start_spin"].blockSignals(False); entry_dict["end_spin"].blockSignals(False)
            
            if getattr(self.controller, 'current_selected_idx', -1) == idx and getattr(self.controller, 'selected_track', '') == 'sub':
                self.controller.sub_start_spin.blockSignals(True); self.controller.sub_end_spin.blockSignals(True)
                self.controller.sub_start_spin.setValue(new_start); self.controller.sub_end_spin.setValue(new_end)
                self.controller.sub_start_spin.blockSignals(False); self.controller.sub_end_spin.blockSignals(False)
                
        elif clip_type == "video":
            self.controller.state["video_clips"][idx]["start"] = new_start; self.controller.state["video_clips"][idx]["end"] = new_end
            if getattr(self.controller, 'current_v_idx', -1) == idx and getattr(self.controller, 'selected_track', '') == 'video':
                self.controller.v_start_spin.blockSignals(True); self.controller.v_end_spin.blockSignals(True)
                self.controller.v_start_spin.setValue(new_start); self.controller.v_end_spin.setValue(new_end)
                self.controller.v_start_spin.blockSignals(False); self.controller.v_end_spin.blockSignals(False)
        elif clip_type == "audio":
            self.controller.state["a_trim"] = [new_start, new_end]
        elif clip_type == "design" and hasattr(self.controller, "update_design_layer_timing_by_index"):
            self.controller.update_design_layer_timing_by_index(idx, new_start, new_end, new_track)

    @pyqtSlot(str, int, float)
    def on_clip_drag_finished(self, clip_type, idx, final_start):
        if not getattr(self.controller, "edit_mode", False):
            return
        self.controller.update_timeline_size()
        self.controller.auto_save_cache()
        self.controller.sync_player_to_time(final_start)
        
    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if not isinstance(item, ClipItem): self.is_scrubbing = True; self.controller.switch_inspector("empty"); self.scrub_playhead(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_scrubbing: self.scrub_playhead(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_scrubbing = False; super().mouseReleaseEvent(event)

    def scrub_playhead(self, x_pos):
        t = max(0.0, self.mapToScene(int(x_pos), 0).x() / self.controller.zoom_factor); self.controller.sync_player_to_time(t)
        
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            old_pps = max(0.001, self.controller.zoom_factor)
            scene_pos = self.mapToScene(event.position().toPoint())
            cursor_time = max(0.0, scene_pos.x() / old_pps)
            cursor_x = event.position().x()
            delta = event.angleDelta().y()
            self.controller.zoom_factor = min(300.0, self.controller.zoom_factor * 1.2) if delta > 0 else max(10.0, self.controller.zoom_factor * 0.8)
            self.sync_from_controller()
            self.horizontalScrollBar().setValue(max(0, int(cursor_time * self.controller.zoom_factor - cursor_x)))
            self.controller._update_workspace_status()
            self.viewport().update()
            event.accept()
        else: super().wheelEvent(event)
