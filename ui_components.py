# ==========================================
# 文件名: ui_components.py (无缝融合 + 宽度拉伸 + 羽化蒙版滚动 + 平滑边缘抗锯齿修复)
# ==========================================
import math
import copy
import subprocess
import os
import re
import html
from difflib import SequenceMatcher
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QObject, pyqtSlot

from core import get_ffmpeg_cmd

FAITH_WORDS = {"god", "jesus", "amen", "lord", "christ", "holy", "bible"}
APOSTROPHES = {"'", "’", "‘", "`"}
ENGLISH_SUFFIX_TOKENS = {
    "'s", "'m", "'re", "'ve", "'ll", "'d", "'t",
    "n't", "n’t", "’s", "’m", "’re", "’ve", "’ll", "’d", "’t",
}


def _normalize_apostrophes(text):
    return str(text or "").replace("’", "'").replace("‘", "'").replace("`", "'")

def _visual_text_units(text):
    units = 0.0
    for ch in str(text or ""):
        if ch.isspace():
            units += 0.32
        elif re.match(r"[\u4e00-\u9fff]", ch):
            units += 1.0
        elif re.match(r"[A-Za-z0-9]", ch):
            units += 0.58
        else:
            units += 0.38
    return max(0.2, units)

def tokenize_display_text(raw_text):
    tokens = []
    buf = ""
    pending_newline = False

    def flush_buf():
        nonlocal buf, pending_newline
        if not buf:
            return
        token = buf
        if pending_newline:
            token = "\n" + token.lstrip()
            pending_newline = False
        tokens.append(token)
        buf = ""

    for ch in _normalize_apostrophes(raw_text).replace("\r\n", "\n").replace("\r", "\n"):
        if ch == "\n":
            flush_buf()
            pending_newline = True
        elif ch.isspace():
            flush_buf()
        elif re.match(r"[\u4e00-\u9fff]", ch):
            flush_buf()
            token = ch
            if pending_newline:
                token = "\n" + token
                pending_newline = False
            tokens.append(token)
        elif re.match(r"[A-Za-z0-9']", ch):
            buf += ch
        else:
            flush_buf()
            if tokens:
                tokens[-1] += ch
            else:
                token = ch
                if pending_newline:
                    token = "\n" + token
                    pending_newline = False
                tokens.append(token)
    flush_buf()
    return [t for t in tokens if t.replace("\n", "").strip()]


def _token_match_key(token):
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff']+", "", _normalize_apostrophes(token).replace("\n", "")).lower()


def _merge_english_suffix_tokens(words):
    merged = []
    for item in words or []:
        word = _normalize_apostrophes(item.get("word", item.get("text", ""))).strip()
        if not word:
            continue
        if not merged:
            fixed = copy.deepcopy(item)
            fixed["word"] = word
            merged.append(fixed)
            continue

        prev = merged[-1]
        prev_word = _normalize_apostrophes(prev.get("word", prev.get("text", ""))).strip()
        suffix_key = word.lower()
        should_merge = (
            suffix_key in ENGLISH_SUFFIX_TOKENS
            or (len(word) <= 3 and word.startswith("'") and re.match(r"^[A-Za-z]+$", word[1:]))
            or (suffix_key in {"s", "m", "re", "ve", "ll", "d", "t"} and prev_word.endswith("'"))
        )
        if should_merge and re.search(r"[A-Za-z]'?$", prev_word):
            fixed_prev = copy.deepcopy(prev)
            if word.startswith("'") or prev_word.endswith("'"):
                suffix_text = word
            else:
                suffix_text = "'" + word
            fixed_prev["word"] = prev_word + suffix_text
            fixed_prev["end"] = max(float(prev.get("end", 0.0)), float(item.get("end", prev.get("end", 0.0))))
            merged[-1] = fixed_prev
            continue

        fixed = copy.deepcopy(item)
        fixed["word"] = word
        merged.append(fixed)
    return merged


def _distribute_tokens_over_span(tokens, start_time, end_time):
    if not tokens:
        return []
    start_time = float(start_time)
    end_time = max(start_time + 0.01, float(end_time))
    weights = [_visual_text_units(token.replace("\n", "")) for token in tokens]
    total = max(0.01, sum(weights))
    span = end_time - start_time
    aligned = []
    cursor_units = 0.0
    for idx, token in enumerate(tokens):
        token_start = start_time + span * cursor_units / total
        cursor_units += weights[idx]
        token_end = end_time if idx == len(tokens) - 1 else start_time + span * cursor_units / total
        if token_end <= token_start:
            token_end = token_start + 0.02
        aligned.append({"word": token, "start": token_start, "end": token_end})
    return aligned


def _normalize_aligned_word_times(aligned, total_start=None, total_end=None):
    if not aligned:
        return []
    total_start = float(total_start if total_start is not None else aligned[0].get("start", 0.0))
    total_end = float(total_end if total_end is not None else aligned[-1].get("end", total_start + 1.0))
    span = max(0.01, total_end - total_start)
    min_dur = min(0.06, max(0.012, span / max(1, len(aligned)) * 0.22))
    cursor = total_start
    normalized = []
    for idx, item in enumerate(aligned):
        remaining = len(aligned) - idx - 1
        latest_start = max(total_start, total_end - max(0.0, remaining + 1) * min_dur)
        raw_start = float(item.get("start", cursor))
        raw_end = float(item.get("end", raw_start + min_dur))
        start = max(cursor, min(raw_start, latest_start))
        end = max(raw_end, start + min_dur)
        if remaining > 0:
            end = min(end, total_end - remaining * min_dur)
            if end <= start:
                end = start + min_dur
        normalized.append({"word": item.get("word", ""), "start": start, "end": end})
        cursor = end
    return normalized


def normalize_word_timestamps(words, text_key="word"):
    normalized = []
    for word in words or []:
        raw_text = _normalize_apostrophes(word.get(text_key) or word.get("word") or word.get("text") or "").strip()
        if not raw_text:
            continue
        pieces = tokenize_display_text(raw_text)
        if not pieces:
            continue
        start = float(word.get("start", 0.0))
        end = float(word.get("end", start + 0.05))
        if end <= start:
            end = start + 0.05
        if len(pieces) == 1:
            normalized.append({"word": pieces[0], "start": start, "end": end})
            continue
        weights = [_visual_text_units(piece.replace("\n", "")) for piece in pieces]
        total = max(0.01, sum(weights))
        cursor = start
        dur = end - start
        for idx, piece in enumerate(pieces):
            part_dur = dur * weights[idx] / total
            part_end = end if idx == len(pieces) - 1 else min(end, cursor + max(0.01, part_dur))
            normalized.append({"word": piece, "start": cursor, "end": max(cursor + 0.01, part_end)})
            cursor = part_end
    return _merge_english_suffix_tokens(normalized)

def align_reference_text_to_timestamps(ai_words, raw_text):
    user_tokens = tokenize_display_text(raw_text)
    ai_words = normalize_word_timestamps(ai_words or [])
    if not ai_words or not user_tokens:
        return ai_words

    total_start = float(ai_words[0].get("start", 0.0))
    total_end = float(ai_words[-1].get("end", total_start + 1.0))
    if total_end <= total_start:
        total_end = total_start + max(1.0, len(user_tokens) * 0.18)

    user_keys = [_token_match_key(token) for token in user_tokens]
    ai_keys = [_token_match_key(w.get("word", "")) for w in ai_words]
    matcher = SequenceMatcher(None, user_keys, ai_keys, autojunk=False)
    pairs = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            u_idx = block.a + offset
            a_idx = block.b + offset
            if u_idx < len(user_keys) and a_idx < len(ai_keys) and user_keys[u_idx] and user_keys[u_idx] == ai_keys[a_idx]:
                pairs.append((u_idx, a_idx))

    # If Whisper and the pasted script barely overlap, keep every pasted word and
    # distribute it over the detected audio duration instead of trusting bad anchors.
    if len(pairs) < max(3, int(len(user_tokens) * 0.18)):
        return _normalize_aligned_word_times(
            _distribute_tokens_over_span(user_tokens, total_start, total_end),
            total_start,
            total_end,
        )

    aligned = [None] * len(user_tokens)
    cursor_user = 0
    cursor_time = total_start

    for u_idx, a_idx in pairs:
        anchor_start = float(ai_words[a_idx].get("start", cursor_time))
        anchor_end = float(ai_words[a_idx].get("end", anchor_start + 0.05))
        if anchor_end <= anchor_start:
            anchor_end = anchor_start + 0.05

        if u_idx > cursor_user:
            gap_tokens = user_tokens[cursor_user:u_idx]
            gap_start = cursor_time
            gap_end = max(gap_start + 0.01, anchor_start)
            gap_aligned = _distribute_tokens_over_span(gap_tokens, gap_start, gap_end)
            for offset, item in enumerate(gap_aligned):
                aligned[cursor_user + offset] = item

        aligned[u_idx] = {"word": user_tokens[u_idx], "start": anchor_start, "end": anchor_end}
        cursor_user = u_idx + 1
        cursor_time = max(cursor_time, anchor_end)

    if cursor_user < len(user_tokens):
        gap_aligned = _distribute_tokens_over_span(user_tokens[cursor_user:], cursor_time, max(cursor_time + 0.01, total_end))
        for offset, item in enumerate(gap_aligned):
            aligned[cursor_user + offset] = item

    # Fill any holes caused by repeated words or skipped anchors.
    for idx, item in enumerate(aligned):
        if item is None:
            prev_time = aligned[idx - 1]["end"] if idx > 0 and aligned[idx - 1] else total_start
            next_time = total_end
            for later in aligned[idx + 1:]:
                if later is not None:
                    next_time = later["start"]
                    break
            aligned[idx] = _distribute_tokens_over_span([user_tokens[idx]], prev_time, max(prev_time + 0.01, next_time))[0]

    return _normalize_aligned_word_times(aligned, total_start, total_end)

def _clean_word_text(word):
    return str(word.get("text", word.get("word", ""))).replace("\n", "").strip()

def _subtitle_plain_text(words):
    parts = []
    for word in words:
        raw = str(word.get("text", word.get("word", ""))).strip()
        if raw:
            parts.append(raw)
    return " ".join(parts).replace(" \n", "\n").replace("\n ", "\n")

def _style_display_text(text, style):
    clean = str(text or "")
    trans = (style or {}).get("text_transform", "capitalize")
    if trans == "uppercase":
        return clean.upper()
    if trans == "lowercase":
        return clean.lower()
    if trans == "capitalize":
        return " ".join(word[0].upper() + word[1:] if word else "" for word in clean.split(" "))

    sub_words = clean.split(" ")
    for s_idx, sub_w in enumerate(sub_words):
        letters = re.sub(r"[^a-zA-Z]", "", sub_w)
        pure_w = letters.lower()
        if letters and pure_w in FAITH_WORDS:
            sub_words[s_idx] = sub_w.replace(letters, pure_w.capitalize(), 1)
    return " ".join(sub_words)

def _apply_balanced_breaks(words, line_capacity, max_lines, style=None):
    cleaned = []
    for word in words:
        item = copy.deepcopy(word)
        item["text"] = _clean_word_text(item)
        cleaned.append(item)
    if max_lines <= 1 or len(cleaned) <= 1:
        return cleaned

    def measure_units(word):
        return _visual_text_units(_style_display_text(_clean_word_text(word), style))

    total_units = sum(measure_units(w) + 0.32 for w in cleaned)
    if total_units <= line_capacity * 1.05:
        return cleaned

    lines = [[]]
    line_units = 0.0
    for word in cleaned:
        word_units = measure_units(word) + (0.32 if lines[-1] else 0.0)
        if lines[-1] and line_units + word_units > line_capacity and len(lines) < max_lines:
            lines.append([])
            line_units = 0.0
            word_units = measure_units(word)
        lines[-1].append(word)
        line_units += word_units

    rebuilt = []
    for line_idx, line in enumerate(lines):
        for word_idx, word in enumerate(line):
            item = copy.deepcopy(word)
            if line_idx > 0 and word_idx == 0:
                item["text"] = "\n" + _clean_word_text(item).lstrip()
            rebuilt.append(item)
    return rebuilt

def subtitle_layout_capacity(style, proj_w=1080):
    style = style or {}
    size = max(12.0, float(style.get("size", 100)))
    width_pct = float(style.get("box_width", 0) or 0)
    if width_pct <= 0:
        width_pct = 74.0
    width_pct = max(28.0, min(92.0, width_pct))
    max_lines = max(1, min(4, int(style.get("max_lines", 2) or 2)))
    line_capacity = max(3.5, (float(proj_w) * width_pct / 100.0) / size * 0.92)
    return line_capacity, max_lines, max(4.0, line_capacity * max_lines)

def rebalance_subtitle_layout(subs, fallback_style=None, default_pos=(0.0, 25.0), proj_w=1080, min_gap=0.01, force_standard_box=False, allow_split=True):
    balanced = []
    stats = {"before": len(subs or []), "after": 0, "split": 0, "overlaps_fixed": 0}
    fallback_style = fallback_style or {}

    for sub in subs or []:
        base = copy.deepcopy(sub)
        style = copy.deepcopy(fallback_style)
        style.update(copy.deepcopy(base.get("style", {})))
        is_standard = style.get("layout_mode", "standard") == "standard"
        if force_standard_box and is_standard:
            style["box_layout"] = "fixed"
            if float(style.get("box_width", 0) or 0) <= 0:
                style["box_width"] = 74.0
            style["max_lines"] = max(1, min(4, int(style.get("max_lines", 2) or 2)))

        words = base.get("words", [])
        if not words:
            words = [{"text": base.get("text", ""), "start": base.get("start", 0.0), "end": base.get("end", 1.0)}]
        words = normalize_word_timestamps(words, text_key="text")
        words = [copy.deepcopy(w) for w in words if _clean_word_text(w)]
        if not words:
            balanced.append(base)
            continue

        if not is_standard:
            base["style"] = style
            base["text"] = _subtitle_plain_text(words)
            base["words"] = words
            balanced.append(base)
            continue

        line_capacity, max_lines, capacity = subtitle_layout_capacity(style, proj_w)
        chunks = []
        current = []
        current_units = 0.0
        for word in words:
            clean = _clean_word_text(word)
            display_clean = _style_display_text(clean, style)
            word_units = _visual_text_units(display_clean) + (0.32 if current else 0.0)
            if allow_split and current and current_units + word_units > capacity:
                chunks.append(current)
                current = []
                current_units = 0.0
                word_units = _visual_text_units(display_clean)
            item = copy.deepcopy(word)
            item["text"] = clean
            current.append(item)
            current_units += word_units
        if current:
            chunks.append(current)

        if len(chunks) > 1:
            stats["split"] += len(chunks) - 1

        for chunk in chunks:
            chunk_words = _apply_balanced_breaks(chunk, line_capacity, max_lines, style)
            new_sub = copy.deepcopy(base)
            new_sub["style"] = copy.deepcopy(style)
            new_sub["words"] = chunk_words
            new_sub["text"] = _subtitle_plain_text(chunk_words)
            new_sub["start"] = float(chunk_words[0].get("start", base.get("start", 0.0)))
            new_sub["end"] = float(chunk_words[-1].get("end", max(new_sub["start"] + 0.05, base.get("end", 1.0))))
            if new_sub["end"] <= new_sub["start"]:
                new_sub["end"] = new_sub["start"] + 0.05
            new_sub["pos_x"] = float(new_sub.get("pos_x", default_pos[0]))
            new_sub["pos_y"] = float(new_sub.get("pos_y", default_pos[1]))
            new_sub["track"] = new_sub.get("track", 1)
            balanced.append(new_sub)

    balanced.sort(key=lambda s: (int(s.get("track", 1)), float(s.get("start", 0.0)), float(s.get("end", 1.0))))
    last_by_track = {}
    for sub in balanced:
        track = int(sub.get("track", 1))
        start = float(sub.get("start", 0.0))
        end = float(sub.get("end", start + 0.05))
        prev = last_by_track.get(track)
        if prev is not None and float(prev.get("end", 0.0)) > start - min_gap:
            prev["end"] = max(float(prev.get("start", 0.0)) + 0.05, start - min_gap)
            stats["overlaps_fixed"] += 1
        if end <= start:
            sub["end"] = start + 0.05
        last_by_track[track] = sub

    balanced.sort(key=lambda s: (float(s.get("start", 0.0)), int(s.get("track", 1)), float(s.get("end", 1.0))))
    stats["after"] = len(balanced)
    return balanced, stats

def hex_to_rgb(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 6:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (255, 255, 255)

def get_exact_duration(file_path):
    if not file_path or not os.path.exists(file_path): return 0.0
    try:
        cmd = [get_ffmpeg_cmd(), '-i', file_path]
        flags = 0x08000000 if os.name == 'nt' else 0
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=5, creationflags=flags)
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return 0.0
    except:
        return 0.0

def get_video_dimensions(file_path):
    if not file_path or not os.path.exists(file_path): return 1080, 1920
    try:
        cmd = [get_ffmpeg_cmd(), '-i', file_path]
        flags = 0x08000000 if os.name == 'nt' else 0
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=5, creationflags=flags)
        match = re.search(r"Video:.*?, (\d+)x(\d+)", result.stderr)
        if match: return int(match.group(1)), int(match.group(2))
        return 1080, 1920
    except:
        return 1080, 1920

class AspectRatioContainer(QWidget):
    def __init__(self, child_widget, parent=None):
        super().__init__(parent)
        self.child_widget = child_widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self.ratio = 1080 / 1920

    def set_ratio(self, w, h):
        if h == 0: return
        self.ratio = w / h
        self.updateGeometry()
        if self.parentWidget():
            self.parentWidget().update()

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        if h > 0 and (w / h) > self.ratio:
            new_w = int(h * self.ratio)
            self.child_widget.setFixedSize(new_w, h)
        else:
            new_h = int(w / self.ratio) if self.ratio > 0 else h
            self.child_widget.setFixedSize(w, new_h)
        super().resizeEvent(event)

class WebBridge(QObject):
    def __init__(self, parent_controller):
        super().__init__()
        self.controller = parent_controller
        
    @pyqtSlot(int, float, float)
    def update_coordinates(self, idx, x, y):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]

            for c in target_clips:
                c["pos_x"] = x; c["pos_y"] = y
            
            if self.controller.current_selected_idx == idx:
                self.controller.pos_x_spin.blockSignals(True); self.controller.pos_x_slider.blockSignals(True)
                self.controller.pos_y_spin.blockSignals(True); self.controller.pos_y_slider.blockSignals(True)
                
                self.controller.pos_x_spin.setValue(float(x)); self.controller.pos_x_slider.setValue(int(float(x) * 100))
                self.controller.pos_y_spin.setValue(float(y)); self.controller.pos_y_slider.setValue(int(float(y) * 100))
                
                self.controller.pos_x_spin.blockSignals(False); self.controller.pos_x_slider.blockSignals(False)
                self.controller.pos_y_spin.blockSignals(False); self.controller.pos_y_slider.blockSignals(False)
            
            self.controller.update_floating_subtitle()
            self.controller.auto_save_cache() 
            
    @pyqtSlot(int, float)
    def update_box_width(self, idx, width):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]

            for c in target_clips:
                if "style" not in c: c["style"] = self.controller.default_style.copy()
                c["style"]["box_width"] = width
            
            if self.controller.current_selected_idx == idx:
                self.controller.box_width_spin.blockSignals(True); self.controller.box_width_slider.blockSignals(True)
                self.controller.box_width_spin.setValue(float(width)); self.controller.box_width_slider.setValue(int(float(width) * 100))
                self.controller.box_width_spin.blockSignals(False); self.controller.box_width_slider.blockSignals(False)
            
            self.controller.update_floating_subtitle()
            self.controller.auto_save_cache()

    @pyqtSlot(int)
    def notify_selected(self, idx): 
        self.controller.current_selected_idx = idx
        self.controller.switch_inspector("sub")
        
    @pyqtSlot(int, str)
    def update_text_from_screen(self, idx, new_text):
        pass
            
    @pyqtSlot(int, int)
    def adjust_font_size(self, idx, delta):
        if 0 <= idx < len(self.controller.state["subs_data"]):
            current_clip = self.controller.state["subs_data"][idx]
            st = current_clip.get("style", current_clip)
            new_size = max(10, min(300, st.get("size", 100) + delta))
            
            scope = self.controller.style_scope_combo.currentIndex()
            if scope == 0: target_clips = self.controller.state["subs_data"]
            elif scope == 1: target_clips = [c for c in self.controller.state["subs_data"] if c.get("track") == current_clip.get("track")]
            else: target_clips = [current_clip]
            
            for c in target_clips: 
                if "style" not in c: c["style"] = {}
                c["style"]["size"] = new_size
            if self.controller.current_selected_idx == idx: 
                self.controller.size_slider.blockSignals(True); self.controller.size_spin.blockSignals(True)
                self.controller.size_slider.setValue(new_size); self.controller.size_spin.setValue(new_size)
                self.controller.size_slider.blockSignals(False); self.controller.size_spin.blockSignals(False)
            self.controller.update_floating_subtitle(); self.controller.auto_save_cache()




def render_subtitle_html(sub, current_time, proj_w=1080):
    def vw(val):
        return f"{float(val) * 100 / proj_w:.4f}vw"

    def clamp01(value):
        return max(0.0, min(1.0, float(value)))

    def ease_out_cubic(value):
        p = clamp01(value)
        return 1.0 - pow(1.0 - p, 3)

    def ease_in_out(value):
        p = clamp01(value)
        return p * p * (3.0 - 2.0 * p)

    style = sub.get("style", sub)
    c_txt = style.get("color_txt", "#FFFFFF")
    c_hl = style.get("color_hl", "#FFFFFF")
    f_fam = style.get("font", "Arial")

    size = int(style.get("size", 100))
    bg_mode = style.get("bg_mode", "none")
    bg_col = style.get("bg_color", "#000000")
    bg_a = style.get("bg_alpha", 80) / 100.0
    rad = style.get("bg_radius", 15)
    pad = style.get("bg_padding", 20)
    pad_left = style.get("bg_pad_left", pad)
    pad_right = style.get("bg_pad_right", pad)
    pad_top = style.get("bg_pad_top", pad / 2.5)
    pad_bottom = style.get("bg_pad_bottom", pad / 2.5)

    hl_bg_col = style.get("hl_bg_color", "#FF0050")
    hl_bg_a = style.get("hl_bg_alpha", 100) / 100.0
    hl_rad = style.get("hl_bg_radius", 8)
    hl_pad = style.get("hl_bg_padding", 8)
    hl_pad_left = style.get("hl_pad_left", hl_pad)
    hl_pad_right = style.get("hl_pad_right", hl_pad)
    hl_pad_top = style.get("hl_pad_top", max(0, hl_pad / 3))
    hl_pad_bottom = style.get("hl_pad_bottom", max(0, hl_pad / 3))

    lh = style.get("line_height", 1.1)
    rot = style.get("rotation", 0)

    stroke_w = style.get("stroke_width", 4)
    stroke_c = style.get("stroke_color", "#000000")
    stroke_o_w = style.get("stroke_o_width", 0)
    stroke_o_c = style.get("stroke_o_color", "#000000")
    sh_x = style.get("shadow_x", 5)
    sh_y = style.get("shadow_y", 5)
    sh_blur = style.get("shadow_blur", 0)
    sh_c = style.get("shadow_color", "#000000")
    sh_a = style.get("shadow_alpha", 100) / 100.0

    trans = style.get("text_transform", "capitalize")
    align = style.get("text_align", "center")
    letter_spacing = style.get("letter_spacing", 0)
    word_spacing = style.get("word_spacing", 0)
    layout_mode = style.get("layout_mode", "standard")
    layout_variant = style.get("layout_variant", "auto")
    emphasis_scale = max(100, int(style.get("emphasis_scale", 145)))
    box_layout = style.get("box_layout", "auto")
    use_hl = style.get("use_hl", True)
    hl_glow = style.get("hl_glow", False)
    glow_size = int(style.get("glow_size", 20))

    anim_type = style.get("anim_type", "pop")
    font_motion = style.get("font_motion", "none")
    hl_motion = style.get("hl_motion", "stable")
    pop_speed = max(0.05, float(style.get("pop_speed", 0.18)))
    pop_bounce = max(100, int(style.get("pop_bounce", 128)))
    inactive_alpha = int(style.get("inactive_alpha", 100)) / 100.0

    box_width = float(style.get("box_width", 0))
    box_height = float(style.get("box_height", 0) or 0)
    max_lines = max(1, min(4, int(style.get("max_lines", 2) or 2)))
    mask_en = style.get("mask_en", False)
    mask_top = style.get("mask_top", 20)
    mask_bot = style.get("mask_bottom", 20)

    size_vw = vw(size)
    rad_vw = vw(rad)
    pad_y = vw(pad / 2.5)
    pad_x = vw(pad)
    pad_top_vw = vw(pad_top)
    pad_right_vw = vw(pad_right)
    pad_bottom_vw = vw(pad_bottom)
    pad_left_vw = vw(pad_left)
    ls_vw = vw(letter_spacing)
    ws_vw = vw(word_spacing)

    hl_rad_vw = vw(hl_rad)
    hl_pad_y = vw(max(0, hl_pad / 3))
    hl_pad_x = vw(hl_pad)
    hl_pad_top_vw = vw(hl_pad_top)
    hl_pad_right_vw = vw(hl_pad_right)
    hl_pad_bottom_vw = vw(hl_pad_bottom)
    hl_pad_left_vw = vw(hl_pad_left)
    hl_spread_vw = vw(max(0, hl_pad, hl_pad_left, hl_pad_right, hl_pad_top, hl_pad_bottom))

    r, g, b = hex_to_rgb(bg_col)
    hl_r, hl_g, hl_b = hex_to_rgb(hl_bg_col)
    stable_word_boxes = bg_mode in ("tape", "block", "full_frame", "sweep") and hl_motion == "stable"

    words = sub.get("words", [])
    if not words:
        words = [{"text": sub.get("text", ""), "start": sub.get("start", 0), "end": sub.get("end", 1)}]

    clip_start = float(sub.get("start", 0))
    clip_end = float(sub.get("end", 1))
    clip_dur = max(0.1, clip_end - clip_start)
    clip_progress = max(0.0, min(1.0, (current_time - clip_start) / clip_dur))
    whole_sub_progress = clip_progress * 100 if bg_mode == "sweep" else 0

    content_indices = [i for i, ww in enumerate(words) if _clean_word_text(ww)]
    emphasis_idx = set()
    small_idx = set()
    current_word_idx = None
    if use_hl and hl_motion in ("pop", "push"):
        for i in content_indices:
            ww = words[i]
            w_start = float(ww.get("start", clip_start))
            w_end = float(ww.get("end", w_start + 0.5))
            if w_start <= current_time <= w_end:
                current_word_idx = i
                break

    def _token_score(token):
        t = re.sub(r"[^A-Za-z0-9一-鿿]", "", token or "")
        if not t:
            return -999
        stop = {
            "i", "me", "my", "you", "your", "we", "our", "to", "the", "a", "an", "and", "or",
            "but", "if", "of", "in", "on", "for", "is", "am", "are", "be", "with", "that",
            "this", "it", "he", "she", "they", "them", "him", "her", "so"
        }
        lower = t.lower()
        score = len(t) * 1.4
        if lower in stop:
            score -= 3.2
        if len(t) <= 2:
            score -= 1.6
        if t.isupper() and len(t) > 1:
            score += 1.2
        if lower in FAITH_WORDS:
            score += 1.5
        return score

    if layout_mode in ("contrast", "triple") and content_indices:
        variant = layout_variant
        if variant == "auto":
            m = len(content_indices) % 3
            variant = "small-big-small" if m == 1 else "big-small-mix" if m == 2 else "mix-big-small"

        ranked = sorted(
            content_indices,
            key=lambda i: (_token_score(_clean_word_text(words[i])), -abs(i - len(words) / 2)),
            reverse=True,
        )

        if layout_mode == "contrast":
            focus_count = 1 if len(content_indices) <= 4 else 2
            emphasis_idx.update(sorted(ranked[:focus_count]))
            if not emphasis_idx:
                emphasis_idx.add(content_indices[max(0, len(content_indices) // 2)])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])
        else:
            if variant == "small-big-small":
                emphasis_idx.update(ranked[:1] or [content_indices[min(1, len(content_indices) - 1)]])
            elif variant == "big-small-mix":
                emphasis_idx.update(ranked[:2] if len(content_indices) > 4 else ranked[:1])
            else:
                focus = ranked[:1] or [content_indices[min(len(content_indices) // 2, len(content_indices) - 1)]]
                emphasis_idx.update(focus)
                if len(content_indices) > 5:
                    emphasis_idx.add(content_indices[0])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])

    html_words_fg = []
    html_words_bg = []

    for idx, w in enumerate(words):
        raw_txt = str(w.get("text") or w.get("word") or "")
        has_newline = "\n" in raw_txt
        clean_txt = raw_txt.replace("\n", "").strip()

        if not clean_txt:
            if has_newline:
                html_words_fg.append("<br>")
                if bg_mode in ("tape", "block"):
                    html_words_bg.append("<br>")
            continue

        if has_newline and idx > 0:
            html_words_fg.append("<br>")
            if bg_mode in ("tape", "block"):
                html_words_bg.append("<br>")

        clean_txt = _style_display_text(clean_txt, style)

        w_start = float(w.get("start", 0))
        w_end = float(w.get("end", w_start + 0.5))

        word_started = current_time >= w_start
        is_active = word_started
        is_current = use_hl and (w_start <= current_time <= w_end)

        t = current_time - w_start
        current_scale = 1.0
        current_opacity = inactive_alpha
        current_translate_em = 0.0
        current_translate_x_em = 0.0
        current_filter_css = "filter: none;"
        current_clip_css = ""
        word_reveal_pct = 100.0

        if is_active:
            current_opacity = 1.0
            if anim_type == "pop" and t >= 0:
                if t <= pop_speed and pop_speed > 0:
                    p = clamp01(t / pop_speed)
                    overshoot = 0.08 + max(0, pop_bounce - 100) / 100.0 * 0.08
                    damp = math.sin(p * math.pi)
                    current_scale = 1.0 + (0.18 + overshoot) * damp
            elif anim_type == "fade" and t >= 0:
                if t <= pop_speed and pop_speed > 0:
                    current_opacity = inactive_alpha + (1.0 - inactive_alpha) * ease_out_cubic(t / pop_speed)
            elif anim_type == "blur_fade" and t >= 0:
                p = ease_out_cubic(t / pop_speed)
                current_opacity = p
                current_translate_em += (1.0 - p) * 0.16
                current_scale *= 0.96 + 0.04 * p
                current_filter_css = f"filter: blur({vw(8 * (1.0 - p))});"
            elif anim_type == "word_wipe" and t >= 0:
                word_reveal_pct = ease_out_cubic(t / pop_speed) * 100.0
        elif anim_type == "blur_fade":
            current_opacity = 0.0
            current_translate_em += 0.16
            current_scale *= 0.96
            current_filter_css = f"filter: blur({vw(8)});"
        elif anim_type == "word_wipe":
            current_opacity = 1.0
            word_reveal_pct = 0.0

        if anim_type in ("wipe_right", "word_wipe"):
            current_opacity = 1.0
        if anim_type == "word_wipe":
            hidden_pct = max(0.0, 100.0 - word_reveal_pct)
            current_clip_css = f"-webkit-clip-path: inset(0 {hidden_pct:.3f}% 0 0); clip-path: inset(0 {hidden_pct:.3f}% 0 0);"

        shadows = []
        if stroke_o_w > 0:
            total_w = stroke_w + stroke_o_w
            for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
                sx = total_w * math.cos(math.radians(angle))
                sy = total_w * math.sin(math.radians(angle))
                shadows.append(f"{vw(sx)} {vw(sy)} 0 {stroke_o_c}")
        if sh_x != 0 or sh_y != 0 or sh_blur != 0:
            sr, sg, sb = hex_to_rgb(sh_c)
            shadows.append(f"{vw(sh_x)} {vw(sh_y)} {vw(sh_blur)} rgba({sr}, {sg}, {sb}, {sh_a})")
        if is_current and hl_glow:
            shadows.extend([f"0 0 {vw(glow_size)} {c_hl}", f"0 0 {vw(glow_size*1.5)} {c_hl}", f"0 0 {vw(glow_size*2)} {c_hl}"])

        text_shadow_css = f"text-shadow: {', '.join(shadows)};" if shadows else "text-shadow: none;"
        
        # 👑 新增平滑边缘
        stroke_css = f"-webkit-text-stroke: {vw(stroke_w)} {stroke_c}; paint-order: stroke fill; stroke-linejoin: round; stroke-linecap: round;" if stroke_w > 0 else ""

        layout_font_scale = 1.0
        per_word_translate = 0.0
        word_margin_right = ws_vw
        if layout_mode in ("contrast", "triple"):
            if idx in emphasis_idx:
                layout_font_scale = emphasis_scale / 100.0
                per_word_translate = -0.06 if layout_mode == "contrast" else -0.04
                word_margin_right = vw(max(0, word_spacing * 0.55 + 1.4))
            elif idx in small_idx:
                layout_font_scale = 0.74 if layout_mode == "contrast" else 0.80
                per_word_translate = 0.03 if layout_mode == "contrast" else 0.02
                word_margin_right = vw(max(0, word_spacing * 0.35 + 0.6))
            else:
                word_margin_right = vw(max(0, word_spacing * 0.45 + 1.0))

        current_translate_em += per_word_translate
        if font_motion == "wave" and word_started:
            wave = math.sin(current_time * 5.2 + idx * 0.72)
            current_translate_em += wave * 0.055
            current_scale *= 1.0 + max(0.0, wave) * 0.018
        if current_word_idx is not None and hl_motion in ("pop", "push"):
            distance = idx - current_word_idx
            active_word = words[current_word_idx]
            active_start = float(active_word.get("start", clip_start))
            active_end = float(active_word.get("end", active_start + 0.5))
            active_dur = max(0.06, active_end - active_start)
            local_p = ease_in_out((current_time - active_start) / min(max(active_dur, 0.12), 0.35))
            if distance == 0:
                target_scale = 1.055 + (0.055 if hl_motion == "push" else 0.035) * local_p
                current_scale = max(current_scale, target_scale)
                current_translate_em -= 0.006 * local_p
            elif hl_motion == "push" and abs(distance) == 1:
                current_translate_x_em += (0.16 + 0.055 * local_p) * (1 if distance > 0 else -1)
            elif hl_motion == "push" and abs(distance) == 2:
                current_translate_x_em += (0.060 + 0.025 * local_p) * (1 if distance > 0 else -1)
        if stable_word_boxes:
            current_translate_x_em = 0.0
            if font_motion == "wave":
                current_translate_em = per_word_translate
            if anim_type == "pop":
                current_scale = min(current_scale, 1.025)

        word_base = (
            f"font-size: {layout_font_scale:.3f}em; "
            f"transform: translate({current_translate_x_em:.3f}em, {current_translate_em:.3f}em) scale({current_scale:.3f}); "
            f"transform-origin: center center; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); "
            f"margin-right: {word_margin_right}; white-space: nowrap; overflow-wrap: normal; word-break: keep-all; "
            f"break-inside: avoid; page-break-inside: avoid; box-sizing: border-box; line-height: inherit; "
            f"vertical-align: baseline; will-change: transform, opacity; backface-visibility: hidden; "
            f"{current_filter_css} {current_clip_css}"
        )

        word_css_fg = f"display: inline-block; color: {c_hl if is_current else c_txt}; opacity: {current_opacity:.3f}; {text_shadow_css} {stroke_css} {word_base}"
        word_css_bg = f"display: inline-block; color: transparent; -webkit-text-fill-color: transparent; text-shadow: none; -webkit-text-stroke: transparent; opacity: {current_opacity:.3f}; {word_base}"

        if bg_mode == "tape":
            if is_current and hl_bg_a > 0:
                hl_css = f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; box-shadow: 0 0 0 {hl_spread_vw} rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}), 0 {vw(3)} {vw(10)} rgba({hl_r}, {hl_g}, {hl_b}, 0.25);"
                word_css_fg += hl_css
                word_css_bg += f" background-color: transparent; border-radius: {hl_rad_vw};"
        elif bg_mode == "block" and is_current and hl_bg_a > 0:
            word_css_fg += f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; box-shadow: 0 0 0 {hl_spread_vw} rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a});"

        safe_txt = html.escape(clean_txt, quote=False)
        html_words_fg.append(f"<span style='{word_css_fg}'>{safe_txt}</span>")
        html_words_bg.append(f"<span style='{word_css_bg}'>{safe_txt}</span>")

        if idx < len(words) - 1:
            next_raw = str(words[idx + 1].get("text") or words[idx + 1].get("word") or "")
            if "\n" not in next_raw:
                spacer = "<span style='display:inline-block; width:0.14em;'></span>" if layout_mode in ("contrast", "triple") else " "
                html_words_fg.append(spacer)
                if bg_mode in ("tape", "block"):
                    html_words_bg.append(spacer if layout_mode in ("contrast", "triple") else " ")

    inner_html_fg = "".join(html_words_fg)
    inner_html_bg = "".join(html_words_bg)

    inner_transform = ""
    if anim_type == "roll_up":
        y_offset = (1.0 - clip_progress * 2) * 50
        inner_transform = f"transform: translateY({y_offset}vh);"

    # 👑 新增平滑边缘及抗锯齿
    base_wrapper_css = f"""
        font-family: '{f_fam}', sans-serif;
        font-size: {size_vw};
        font-weight: bold;
        letter-spacing: {ls_vw};
        word-spacing: {('0vw' if layout_mode in ('contrast', 'triple') else ws_vw)};
        text-transform: none;
        box-sizing: border-box;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
        text-wrap: normal;
        overflow-wrap: normal;
        word-break: normal;
        white-space: normal;
    """

    j_map = {"center": "center", "left": "start", "right": "end", "justify": "center"}
    align_item = j_map.get(align, "center")
    if box_width > 0:
        width_value = f"{box_width:.4f}vw"
        if box_layout == "fixed":
            width_css = f"width: {width_value}; max-width: 92vw;"
        else:
            width_css = f"max-width: {width_value}; width: fit-content;"
    else:
        width_css = "width: max-content; max-width: 92vw;"

    mask_css = ""
    if mask_en:
        mask_css = f"-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black {mask_top}%, black {100-mask_bot}%, transparent 100%); mask-image: linear-gradient(to bottom, transparent 0%, black {mask_top}%, black {100-mask_bot}%, transparent 100%);"

    height_css = f"max-height: {box_height:.4f}vh;" if box_height > 0 else ""
    line_guard_css = ""
    if layout_mode == "standard" and max_lines > 0:
        line_guard_css = f"--sub-max-lines: {max_lines};"
    overflow_css = "hidden" if box_height > 0 else "visible"
    outer_box_style = f"{width_css} {height_css} {line_guard_css} margin: 0 auto; outline: none; text-align: {align}; position: relative; {mask_css} transform: rotate({rot}deg); overflow: {overflow_css}; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);"

    if bg_mode == "tape":
        fg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: rgba({r}, {g}, {b}, {bg_a});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.6, float(lh))};
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display: flex; justify-content: {align_item}; text-align: {align};">
                <span style="{fg_layer_css}">{inner_html_fg}</span>
            </div>
        </div>
        """
    elif bg_mode == "block":
        wrapper_css = base_wrapper_css + f"""
            display: inline-block;
            background-color: rgba({r}, {g}, {b}, {bg_a});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            text-align: {align};
            line-height: {max(0.8, float(lh))};
            width: 100%;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%;"><div style="{wrapper_css}">{inner_html_fg}</div></div>
        </div>
        """
    elif bg_mode == "full_frame":
        frame_wrap_css = base_wrapper_css + f"""
            display: inline-block;
            line-height: {max(0.8, float(lh))};
            white-space: normal;
            overflow-wrap: normal;
            word-break: normal;
            background-color: rgba({r}, {g}, {b}, {bg_a});
            border-radius: {rad_vw};
            padding: {pad_top_vw} {pad_right_vw} {pad_bottom_vw} {pad_left_vw};
            text-align: {align};
            max-width: 100%;
            box-sizing: border-box;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display:flex; justify-content:{align_item}; text-align:{align};">
                <div style="{frame_wrap_css}">{inner_html_fg}</div>
            </div>
        </div>
        """
    elif bg_mode == "sweep":
        bg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: rgb({r}, {g}, {b});
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.8, float(lh))};
        """
        fg_layer_css = base_wrapper_css + f"""
            display: inline;
            background-color: transparent;
            border-radius: {rad_vw};
            padding: {pad_y} {pad_x};
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
            line-height: {max(0.8, float(lh))};
            background: linear-gradient(to right, {hl_bg_col} {whole_sub_progress}%, {c_txt} {whole_sub_progress}%);
            -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; text-fill-color: transparent;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display: grid; grid-template-columns: 1fr; grid-template-rows: 1fr; justify-items: {align_item}; align-items: center; text-align: {align};">
                <div style="grid-area: 1/1; opacity: {bg_a}; z-index: 1; width: 100%;"><span style="{bg_layer_css}">{inner_html_bg if inner_html_bg else inner_html_fg}</span></div>
                <div style="grid-area: 1/1; z-index: 2; width: 100%;"><span style="{fg_layer_css}">{inner_html_fg}</span></div>
            </div>
        </div>
        """
    else:
        wrapper_css = base_wrapper_css + f"""
            display: inline-block;
            text-align: {align};
            line-height: {max(0.8, float(lh))};
            width: 100%;
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%;"><div style="{wrapper_css}">{inner_html_fg}</div></div>
        </div>
        """

    if anim_type == "wipe_right":
        reveal_pct = ease_out_cubic(clip_progress) * 100.0
        hidden_pct = max(0.0, 100.0 - reveal_pct)
        final_html = f"""
        <div class='sub-wipe-wrap' style='position: relative; display: inline-block; max-width: 100%;'>
            <div style='-webkit-clip-path: inset(0 {hidden_pct:.3f}% 0 0); clip-path: inset(0 {hidden_pct:.3f}% 0 0);'>
                {final_html}
            </div>
        </div>
        """

    return final_html
