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

from core import get_ffmpeg_cmd, get_ffprobe_cmd

FAITH_WORDS = {"god", "jesus", "amen", "lord", "christ", "holy", "bible"}
APOSTROPHES = {"'", "’", "‘", "`"}
ENGLISH_SUFFIX_TOKENS = {
    "'s", "'m", "'re", "'ve", "'ll", "'d", "'t",
    "n't", "n’t", "’s", "’m", "’re", "’ve", "’ll", "’d", "’t",
}


def default_signature_style(base_style=None, scale_from_subtitle=True):
    style = copy.deepcopy(base_style or {})
    try:
        base_size = int(style.get("size", 42) or 42)
    except Exception:
        base_size = 42
    style.update({
        "size": int(base_size * 0.42) if scale_from_subtitle and base_size > 70 else base_size,
        "font": style.get("font", "Noto Sans SC"),
        "font_weight": style.get("font_weight", "700"),
        "font_style": style.get("font_style", "normal"),
        "color_txt": style.get("color_txt", "#FFFFFF"),
        "color_hl": style.get("color_hl", "#FFFFFF"),
        "bg_mode": "cinematic_frame",
        "bg_color": style.get("bg_color", "#0B1020"),
        "bg_alpha": 45,
        "bg_radius": 26,
        "bg_padding": 10,
        "bg_pad_left": 18,
        "bg_pad_right": 18,
        "bg_pad_top": 5,
        "bg_pad_bottom": 6,
        "hl_bg_color": style.get("hl_bg_color", "#FFFFFF"),
        "hl_bg_alpha": 0,
        "stroke_width": min(2, int(style.get("stroke_width", 2) or 2)),
        "stroke_color": style.get("stroke_color", "#000000"),
        "stroke_o_width": 0,
        "shadow_x": 0,
        "shadow_y": 3,
        "shadow_blur": 10,
        "shadow_color": "#000000",
        "shadow_alpha": 55,
        "line_height": 1.0,
        "text_transform": "normal",
        "text_align": "right",
        "letter_spacing": 0,
        "word_spacing": 0,
        "layout_mode": "standard",
        "layout_variant": "auto",
        "box_layout": "auto",
        "box_width": 0,
        "box_height": 0,
        "max_lines": 1,
        "mask_en": False,
        "use_hl": False,
        "hl_glow": False,
        "anim_type": "none",
        "font_motion": "none",
        "hl_motion": "stable",
        "inactive_alpha": 100,
        "text_texture": "none",
    })
    return style


def default_signature_config(base_style=None):
    return {
        "enabled": False,
        "text": "",
        "placement": "top_right",
        "margin_x": 5.0,
        "margin_y": 4.0,
        "pos_x": 0.0,
        "pos_y": -42.0,
        "style": default_signature_style(base_style),
    }


def normalize_signature_config(signature, base_style=None):
    config = default_signature_config(base_style)
    if isinstance(signature, dict):
        sig_style = signature.get("style", {})
        config.update({k: v for k, v in signature.items() if k != "style"})
        style = default_signature_style(base_style)
        if isinstance(sig_style, dict):
            style.update(sig_style)
        config["style"] = style
    return config


def default_design_room_state():
    return {
        "version": 1,
        "width": 1080,
        "height": 1920,
        "pages": [
            {
                "id": "page-1",
                "name": "页面 1",
                "duration": 5.0,
                "layers": [],
            }
        ],
    }


def normalize_design_room_state(state):
    data = copy.deepcopy(state) if isinstance(state, dict) else default_design_room_state()
    data.setdefault("version", 1)
    data["width"] = max(1, int(data.get("width", 1080) or 1080))
    data["height"] = max(1, int(data.get("height", 1920) or 1920))
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        pages = default_design_room_state()["pages"]
    clean_pages = []
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        clean_page = {
            "id": str(page.get("id") or f"page-{i + 1}"),
            "name": str(page.get("name") or f"页面 {i + 1}"),
            "duration": max(0.1, float(page.get("duration", 5.0) or 5.0)),
            "layers": [],
        }
        for j, layer in enumerate(page.get("layers", []) or []):
            if not isinstance(layer, dict):
                continue
            item = copy.deepcopy(layer)
            item["id"] = str(item.get("id") or f"layer-{i + 1}-{j + 1}")
            item["type"] = str(item.get("type") or "text")
            if item["type"] not in {"text", "rect", "image"}:
                item["type"] = "text"
            item["name"] = str(item.get("name") or ("文字" if item["type"] == "text" else "图层"))
            item["x"] = float(item.get("x", 0) or 0)
            item["y"] = float(item.get("y", 0) or 0)
            item["width"] = max(1.0, float(item.get("width", 300) or 300))
            item["height"] = max(1.0, float(item.get("height", 80) or 80))
            item["rotation"] = float(item.get("rotation", 0) or 0)
            item["opacity"] = max(0.0, min(1.0, float(item.get("opacity", 1) or 0)))
            item["start"] = max(0.0, float(item.get("start", 0.0) or 0.0))
            item["end"] = max(0.0, float(item.get("end", 0.0) or 0.0))
            try:
                item["zIndex"] = int(float(item.get("zIndex", j) or 0))
            except Exception:
                item["zIndex"] = j
            if item["type"] == "image":
                item["src"] = str(item.get("src", "") or "")
                item["fit"] = str(item.get("fit", "cover") or "cover")
            clean_page["layers"].append(item)
        clean_pages.append(clean_page)
    if not clean_pages:
        clean_pages = default_design_room_state()["pages"]
    data["pages"] = clean_pages
    return data


def design_frame_times(design_state):
    state = normalize_design_room_state(design_state)
    times = [0.0]
    cursor = 0.0
    for page in state.get("pages", []) or []:
        page_dur = max(0.1, float(page.get("duration", 5.0) or 5.0))
        times.append(cursor)
        for layer in page.get("layers", []) or []:
            if not isinstance(layer, dict):
                continue
            start = max(0.0, float(layer.get("start", 0.0) or 0.0))
            end = float(layer.get("end", 0.0) or 0.0)
            if end <= 0:
                end = page_dur
            times.append(cursor + min(page_dur, start))
            times.append(cursor + min(page_dur, max(start, end)))
        cursor += page_dur
        times.append(cursor)
    return sorted(set(round(t, 3) for t in times if t >= 0.0))


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

def get_stream_duration(file_path, stream_selector="v:0"):
    if not file_path or not os.path.exists(file_path):
        return 0.0
    flags = 0x08000000 if os.name == 'nt' else 0
    try:
        cmd = [
            get_ffprobe_cmd(), "-v", "error",
            "-select_streams", stream_selector,
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            creationflags=flags,
        )
        probed_duration = 0.0
        for line in result.stdout.splitlines():
            try:
                value = float(line.strip())
                if value > 0:
                    probed_duration = value
                    break
            except Exception:
                continue
        if stream_selector.startswith("v"):
            packet_duration = _estimate_video_packet_duration(file_path)
            if packet_duration > 0 and (probed_duration <= 0 or packet_duration < probed_duration * 0.985):
                return packet_duration
        if probed_duration > 0:
            return probed_duration
    except Exception:
        pass

    return get_exact_duration(file_path)

def get_video_stream_duration(file_path):
    return get_stream_duration(file_path, "v:0")

def get_audio_stream_duration(file_path):
    return get_stream_duration(file_path, "a:0")

def _parse_rate(value):
    text = str(value or "").strip()
    if not text or text in ("0/0", "N/A"):
        return 0.0
    try:
        if "/" in text:
            num, den = text.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        return float(text)
    except Exception:
        return 0.0

def _estimate_video_packet_duration(file_path):
    if not file_path or not os.path.exists(file_path):
        return 0.0
    flags = 0x08000000 if os.name == 'nt' else 0
    try:
        cmd = [
            get_ffprobe_cmd(), "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets,avg_frame_rate,r_frame_rate",
            "-of", "default=noprint_wrappers=1",
            file_path,
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=20,
            creationflags=flags,
        )
        data = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
        packets = int(float(data.get("nb_read_packets", "0") or 0))
        rate = _parse_rate(data.get("avg_frame_rate")) or _parse_rate(data.get("r_frame_rate"))
        if packets > 0 and rate > 0:
            return packets / rate
    except Exception:
        return 0.0
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
    f_weight = str(style.get("font_weight", "700") or "700")
    f_style = str(style.get("font_style", "normal") or "normal")

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
    stroke_softness = max(0, min(100, int(style.get("stroke_softness", 0))))
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
    text_texture = style.get("text_texture", "none")

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
    stable_word_boxes = bg_mode in ("tape", "block", "full_frame", "sweep", "cinematic_frame") and hl_motion == "stable"

    words = sub.get("words", [])
    if not words:
        words = [{"text": sub.get("text", ""), "start": sub.get("start", 0), "end": sub.get("end", 1)}]

    clip_start = float(sub.get("start", 0))
    clip_end = float(sub.get("end", 1))
    clip_dur = max(0.1, clip_end - clip_start)
    clip_progress = max(0.0, min(1.0, (current_time - clip_start) / clip_dur))
    whole_sub_progress = clip_progress * 100 if bg_mode == "sweep" else 0

    content_indices = [i for i, ww in enumerate(words) if _clean_word_text(ww)]
    content_center = (content_indices[0] + content_indices[-1]) / 2.0 if content_indices else (len(words) - 1) / 2.0
    head_letter_large_variant = layout_mode == "reel_stack" and layout_variant in ("head-letter-large", "initial-large")
    head_large_variant = layout_mode == "reel_stack" and layout_variant in ("head-large", "head-emphasis", "head-only", "head-uppercase")
    tail_large_variant = layout_mode == "reel_stack" and layout_variant in ("tail-large", "tail-emphasis", "tail-only", "tail-uppercase")
    if align in ("free_mix", "left_mix"):
        align_seed_text = "".join(_clean_word_text(words[i]) for i in content_indices) if content_indices else str(sub.get("text", ""))
        align_seed = int(clip_start * 1000) + sum(ord(ch) for ch in align_seed_text)
        if align == "left_mix":
            align = "center" if align_seed % 5 == 0 else "left"
        else:
            align = "left" if align_seed % 2 == 0 else "center"
    if layout_mode in ("mixed_reel", "smart_caption") and content_indices:
        mix_seed_text = "".join(_clean_word_text(words[i]) for i in content_indices)
        mix_seed = int(clip_start * 1000) + sum(ord(ch) for ch in mix_seed_text)
        count = len(content_indices)
        if count >= 5:
            layout_mode = "quote_stack"
        elif count <= 2:
            layout_mode = "side_steps" if mix_seed % 2 else "axis_stack"
        elif count == 3:
            layout_mode = ("axis_stack", "reel_stack", "random_focus")[mix_seed % 3]
        elif count == 4:
            layout_mode = ("side_steps", "random_focus", "reel_stack")[mix_seed % 3]
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

    if layout_mode in ("contrast", "triple", "reel_stack", "random_focus", "axis_stack", "quote_stack") and content_indices:
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
        elif layout_mode == "triple":
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
        elif layout_mode == "reel_stack":
            if head_large_variant:
                emphasis_idx.add(content_indices[0])
            elif tail_large_variant:
                emphasis_idx.add(content_indices[-1])
            elif not head_letter_large_variant:
                emphasis_idx.add(content_indices[0])
                if len(content_indices) > 1:
                    emphasis_idx.add(content_indices[-1])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])
        elif layout_mode == "random_focus":
            focus_count = 2 if len(content_indices) <= 5 else 3
            emphasis_idx.update(sorted(ranked[:focus_count]))
            small_idx.update([i for i in content_indices if i not in emphasis_idx])
        elif layout_mode == "axis_stack":
            if content_indices:
                emphasis_idx.add(content_indices[0])
                if len(content_indices) >= 3:
                    emphasis_idx.add(content_indices[-1])
            small_idx.update([i for i in content_indices if i not in emphasis_idx and len(content_indices) > 2])
        elif layout_mode == "quote_stack":
            emphasis_idx.add(content_indices[0])
            if len(content_indices) > 1:
                emphasis_idx.add(content_indices[-1])
            small_idx.update([i for i in content_indices if i not in emphasis_idx])

    content_order = {word_idx: order for order, word_idx in enumerate(content_indices)}

    def _build_layout_rows():
        items = content_indices
        n = len(items)
        if not items or layout_mode not in ("reel_stack", "random_focus", "side_steps", "axis_stack", "quote_stack"):
            return []
        if layout_mode == "quote_stack":
            if n <= 2:
                return [[item] for item in items]
            if n <= 4:
                return [[items[0]], items[1:-1], [items[-1]]]
            if n <= 7:
                mid = 1 + max(2, min(3, n - 2))
                return [[items[0]], items[1:mid], items[mid:-1], [items[-1]]]
            left_mid = 1 + max(3, min(4, (n - 2) // 2 + 1))
            return [[items[0]], items[1:left_mid], items[left_mid:-1], [items[-1]]]
        if layout_mode == "side_steps":
            return [[item] for item in items]
        if layout_mode == "axis_stack":
            if layout_variant == "axis-123" or n <= 3:
                return [[item] for item in items]
            if n == 4:
                return [[items[0]], [items[1]], [items[2], items[3]]]
            return [[item] for item in items[:-2]] + [items[-2:]]
        if layout_mode == "reel_stack":
            if head_letter_large_variant or head_large_variant:
                if n <= 2:
                    return [[item] for item in items]
                if n <= 4:
                    return [[items[0]], items[1:]]
                mid = max(2, min(n - 1, n // 2 + 1))
                return [[items[0]], items[1:mid], items[mid:]]
            if tail_large_variant:
                if n <= 2:
                    return [[item] for item in items]
                if n <= 4:
                    return [items[:-1], [items[-1]]]
                mid = max(2, min(n - 1, n // 2))
                return [items[:mid], items[mid:-1], [items[-1]]]
            if n <= 3:
                return [[item] for item in items]
            if n == 4:
                return [[items[0]], [items[1], items[2]], [items[3]]]
            mid = max(2, min(n - 2, n // 2))
            return [[items[0]], items[1:mid], items[mid:-1], [items[-1]]]
        if layout_mode == "random_focus":
            if n <= 3:
                return [[item] for item in items]
            if n == 4:
                return [items[:2], [items[2]], [items[3]]]
            return [items[:3], [items[3]], items[4:]]
        return []

    layout_rows = _build_layout_rows()
    layout_break_before = {row[0] for row in layout_rows[1:] if row}
    layout_row_lookup = {
        word_idx: (row_i, pos_i, len(row))
        for row_i, row in enumerate(layout_rows)
        for pos_i, word_idx in enumerate(row)
    }

    def _layout_breaks_before(word_idx):
        return word_idx in layout_break_before

    first_content_idx = content_indices[0] if content_indices else None
    final_content_idx = content_indices[-1] if content_indices else None
    word_line_indices = {}
    line_i = 0
    for word_idx, word in enumerate(words):
        raw_line_txt = str(word.get("text") or word.get("word") or "")
        if word_idx > 0 and ("\n" in raw_line_txt or _layout_breaks_before(word_idx)):
            line_i += 1
        word_line_indices[word_idx] = line_i
    holy_line_count = line_i + 1

    html_words_fg = []
    html_words_bg = []

    for idx, w in enumerate(words):
        raw_txt = str(w.get("text") or w.get("word") or "")
        has_newline = "\n" in raw_txt
        clean_txt = raw_txt.replace("\n", "").strip()

        if not clean_txt:
            if has_newline:
                html_words_fg.append("<br>")
                if bg_mode in ("tape", "block", "sweep"):
                    html_words_bg.append("<br>")
            continue

        inserted_break = False
        if has_newline and idx > 0:
            html_words_fg.append("<br>")
            inserted_break = True
            if bg_mode in ("tape", "block", "sweep"):
                html_words_bg.append("<br>")

        if not inserted_break and _layout_breaks_before(idx):
            html_words_fg.append("<br>")
            if bg_mode in ("tape", "block", "sweep"):
                html_words_bg.append("<br>")

        clean_txt = _style_display_text(clean_txt, style)

        w_start = float(w.get("start", 0))
        w_end = float(w.get("end", w_start + 0.5))

        holy_line_idx = word_line_indices.get(idx, 0)
        is_holy_final_word = anim_type == "holy_breath" and idx == final_content_idx
        holy_speed = max(1.15, pop_speed * 4.8)
        if is_holy_final_word:
            holy_speed *= 1.35
            holy_speed = min(holy_speed, max(0.65, clip_dur * 0.72))
        else:
            holy_speed = min(holy_speed, max(0.55, clip_dur * 0.62))

        if anim_type == "holy_breath":
            line_delay = min(0.70, 0.38 + max(0.0, pop_speed - 0.18) * 0.18)
            if holy_line_count > 1:
                line_delay = min(line_delay, max(0.12, clip_dur * 0.32 / max(1, holy_line_count - 1)))
            holy_reveal_start = max(clip_start, min(w_start, clip_end - 0.05))
            holy_reveal_start = max(holy_reveal_start, clip_start + holy_line_idx * line_delay)
            if is_holy_final_word:
                holy_reveal_start += min(0.55, max(0.22, clip_dur * 0.12))
            min_visible = min(0.80 if is_holy_final_word else 0.42, max(0.34 if is_holy_final_word else 0.20, clip_dur * (0.26 if is_holy_final_word else 0.14)))
            latest_reveal_start = max(clip_start, clip_end - 0.12 - min_visible)
            holy_reveal_start = min(holy_reveal_start, latest_reveal_start)
            word_started = current_time >= holy_reveal_start
            t = current_time - holy_reveal_start
        else:
            word_started = current_time >= w_start
            t = current_time - w_start
        is_active = word_started
        is_current = use_hl and (w_start <= current_time <= w_end)

        current_scale = 1.0
        current_opacity = inactive_alpha
        current_translate_em = 0.0
        current_translate_x_em = 0.0
        current_rotate_x_deg = 0.0
        current_rotate_y_deg = 0.0
        current_filter_css = "filter: none;"
        current_clip_css = ""
        word_reveal_pct = 100.0
        current_letter_extra = 0.0

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
            elif anim_type == "grow_in" and t >= 0:
                p = ease_out_cubic(t / pop_speed)
                current_opacity = p
                current_translate_em += (1.0 - p) * 0.08
                current_scale *= 0.28 + 0.72 * p
                current_filter_css = f"filter: blur({vw(3 * (1.0 - p))});"
            elif anim_type == "scatter_in" and t >= 0:
                p = ease_out_cubic(t / pop_speed)
                spread = idx - content_center
                current_opacity = p
                current_translate_x_em += spread * 0.34 * (1.0 - p)
                current_translate_em += math.sin(idx * 1.71) * 0.20 * (1.0 - p)
                current_scale *= 0.82 + 0.18 * p
                current_filter_css = f"filter: blur({vw(5 * (1.0 - p))});"
            elif anim_type == "letter_scatter_in" and t >= 0:
                p = ease_out_cubic(t / max(0.05, pop_speed * 1.35))
                spread = idx - content_center
                current_opacity = p
                current_letter_extra = 14.0 * (1.0 - p)
                current_translate_x_em += spread * 0.18 * (1.0 - p)
                current_scale *= 0.90 + 0.10 * p
                current_filter_css = f"filter: blur({vw(4 * (1.0 - p))});"
            elif anim_type == "holy_breath" and t >= 0:
                p = ease_out_cubic(t / holy_speed)
                breath = math.sin(max(0.0, current_time - clip_start) * 1.35 + holy_line_idx * 0.45)
                final_weight = 1.0 if is_holy_final_word else 0.0
                current_opacity = p
                current_translate_em += (1.0 - p) * 0.22 - breath * (0.010 + final_weight * 0.004)
                current_scale *= (0.965 + 0.035 * p) * (1.0 + breath * (0.010 + final_weight * 0.008))
                current_filter_css = f"filter: blur({vw((10.0 + final_weight * 3.0) * (1.0 - p))});"
            elif anim_type == "word_wipe" and t >= 0:
                word_reveal_pct = ease_out_cubic(t / pop_speed) * 100.0
        elif anim_type == "blur_fade":
            current_opacity = 0.0
            current_translate_em += 0.16
            current_scale *= 0.96
            current_filter_css = f"filter: blur({vw(8)});"
        elif anim_type == "grow_in":
            current_opacity = 0.0
            current_translate_em += 0.08
            current_scale *= 0.28
            current_filter_css = f"filter: blur({vw(3)});"
        elif anim_type == "scatter_in":
            spread = idx - content_center
            current_opacity = 0.0
            current_translate_x_em += spread * 0.34
            current_translate_em += math.sin(idx * 1.71) * 0.20
            current_scale *= 0.82
            current_filter_css = f"filter: blur({vw(5)});"
        elif anim_type == "letter_scatter_in":
            spread = idx - content_center
            current_opacity = 0.0
            current_letter_extra = 14.0
            current_translate_x_em += spread * 0.18
            current_scale *= 0.90
            current_filter_css = f"filter: blur({vw(4)});"
        elif anim_type == "holy_breath":
            current_opacity = 0.0
            current_translate_em += 0.22
            current_scale *= 0.965
            current_filter_css = f"filter: blur({vw(13 if is_holy_final_word else 10)});"
        elif anim_type == "word_wipe":
            current_opacity = 1.0
            word_reveal_pct = 0.0

        if anim_type in ("wipe_right", "word_wipe"):
            current_opacity = 1.0
        if anim_type == "word_wipe":
            hidden_pct = max(0.0, 100.0 - word_reveal_pct)
            current_clip_css = f"-webkit-clip-path: inset(0 {hidden_pct:.3f}% 0 0); clip-path: inset(0 {hidden_pct:.3f}% 0 0);"

        shadows = []
        stroke_r, stroke_g, stroke_b = hex_to_rgb(stroke_c)
        if stroke_o_w > 0:
            total_w = stroke_w + stroke_o_w
            outer_blur = total_w * (stroke_softness / 100.0) * 0.28
            for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
                sx = total_w * math.cos(math.radians(angle))
                sy = total_w * math.sin(math.radians(angle))
                shadows.append(f"{vw(sx)} {vw(sy)} {vw(outer_blur)} {stroke_o_c}")
        if stroke_w > 0 and stroke_softness > 0:
            soft_p = stroke_softness / 100.0
            soft_blur = stroke_w * (0.22 + 0.78 * soft_p)
            soft_spread = stroke_w * (0.18 + 0.20 * soft_p)
            soft_alpha = 0.24 + 0.30 * soft_p
            for angle in [0, 60, 120, 180, 240, 300]:
                sx = soft_spread * math.cos(math.radians(angle))
                sy = soft_spread * math.sin(math.radians(angle))
                shadows.append(f"{vw(sx)} {vw(sy)} {vw(soft_blur)} rgba({stroke_r}, {stroke_g}, {stroke_b}, {soft_alpha:.2f})")
            shadows.append(f"0 0 {vw(soft_blur * 1.35)} rgba({stroke_r}, {stroke_g}, {stroke_b}, {max(0.18, soft_alpha - 0.12):.2f})")
        if sh_x != 0 or sh_y != 0 or sh_blur != 0:
            sr, sg, sb = hex_to_rgb(sh_c)
            shadows.append(f"{vw(sh_x)} {vw(sh_y)} {vw(sh_blur)} rgba({sr}, {sg}, {sb}, {sh_a})")
        if is_current and hl_glow:
            shadows.extend([f"0 0 {vw(glow_size)} {c_hl}", f"0 0 {vw(glow_size*1.5)} {c_hl}", f"0 0 {vw(glow_size*2)} {c_hl}"])
        if anim_type == "holy_breath" and is_holy_final_word and current_opacity > 0.02:
            glow_hex = c_hl if use_hl else c_txt
            gr, gg, gb = hex_to_rgb(glow_hex)
            aura = min(1.0, max(0.0, current_opacity))
            shadows.extend([
                f"0 0 {vw(10)} rgba({gr}, {gg}, {gb}, {0.16 * aura:.2f})",
                f"0 0 {vw(22)} rgba({gr}, {gg}, {gb}, {0.10 * aura:.2f})",
            ])

        text_shadow_css = f"text-shadow: {', '.join(shadows)};" if shadows else "text-shadow: none;"
        
        # Keep a crisp inner outline and feather the outside through text-shadow.
        hard_stroke_w = stroke_w * (1.0 - 0.42 * (stroke_softness / 100.0))
        stroke_css = f"-webkit-text-stroke: {vw(max(0.0, hard_stroke_w))} {stroke_c}; paint-order: stroke fill; stroke-linejoin: round; stroke-linecap: round;" if stroke_w > 0 else ""

        layout_font_scale = 1.0
        per_word_translate = 0.0
        word_margin_right = ws_vw
        layout_row_i, layout_pos_i, layout_row_len = layout_row_lookup.get(idx, (0, 0, 0))
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
        elif layout_mode == "reel_stack":
            if head_letter_large_variant and idx == first_content_idx:
                layout_font_scale = 1.0
                per_word_translate = -0.02
                word_margin_right = vw(max(0, word_spacing * 0.28 + 0.7))
            elif idx in emphasis_idx:
                layout_font_scale = max(emphasis_scale / 100.0, 1.42 if layout_row_i == 0 else 1.62)
                per_word_translate = -0.035 if layout_row_i == 0 else -0.055
                word_margin_right = vw(max(0, word_spacing * 0.35 + 0.8))
            else:
                layout_font_scale = 0.72 if len(content_indices) > 4 else 0.82
                per_word_translate = 0.035
                word_margin_right = vw(max(0, word_spacing * 0.22 + 0.6))
        elif layout_mode == "random_focus":
            if idx in emphasis_idx:
                rank_boost = 0.18 if layout_row_i % 2 == 1 else 0.0
                layout_font_scale = max(emphasis_scale / 100.0, 1.32 + rank_boost)
                per_word_translate = -0.045
                word_margin_right = vw(max(0, word_spacing * 0.30 + 1.0))
            else:
                layout_font_scale = 0.70 + ((idx * 7) % 4) * 0.08
                per_word_translate = 0.025
                word_margin_right = vw(max(0, word_spacing * 0.18 + 0.55))
        elif layout_mode == "side_steps":
            side = -1 if layout_row_i % 2 == 0 else 1
            layout_font_scale = max(emphasis_scale / 100.0, 1.32)
            current_translate_x_em += side * (1.10 + (0.10 if layout_row_i % 3 == 0 else 0.0))
            per_word_translate = -0.02
            word_margin_right = vw(max(0, word_spacing * 0.20 + 0.4))
        elif layout_mode == "axis_stack":
            if layout_row_len == 2:
                current_translate_x_em += (-0.72 if layout_pos_i == 0 else 0.72)
                layout_font_scale = max(emphasis_scale / 100.0, 1.18)
                word_margin_right = vw(max(0, word_spacing * 0.35 + 1.2))
            elif idx in emphasis_idx:
                layout_font_scale = max(emphasis_scale / 100.0, 1.34)
                per_word_translate = -0.035
                word_margin_right = vw(max(0, word_spacing * 0.25 + 0.8))
            else:
                layout_font_scale = 0.88
                word_margin_right = vw(max(0, word_spacing * 0.18 + 0.55))
        elif layout_mode == "quote_stack":
            if idx in emphasis_idx:
                layout_font_scale = max(emphasis_scale / 100.0, 1.38 if layout_row_i == 0 else 1.48)
                per_word_translate = -0.045 if layout_row_i == 0 else -0.055
                word_margin_right = vw(max(0, word_spacing * 0.32 + 0.85))
            else:
                layout_font_scale = 0.72 if layout_row_len >= 3 else 0.82
                per_word_translate = 0.025
                word_margin_right = vw(max(0, word_spacing * 0.18 + 0.52))

        current_translate_em += per_word_translate
        if font_motion == "wave" and word_started:
            wave = math.sin(current_time * 5.2 + idx * 0.72)
            current_translate_em += wave * 0.055
            current_scale *= 1.0 + max(0.0, wave) * 0.018
        elif font_motion == "breathe" and word_started:
            breath = (math.sin(current_time * 1.8 + idx * 0.12) + 1.0) / 2.0
            current_scale *= 1.0 + breath * 0.055
        elif font_motion == "ripple3d" and word_started:
            ripple = math.sin(current_time * 3.45 + idx * 0.88)
            cross = math.cos(current_time * 2.75 + idx * 0.52)
            current_translate_em += ripple * 0.052
            current_translate_x_em += cross * 0.025
            current_scale *= 1.0 + ripple * 0.020
            current_rotate_y_deg += ripple * 6.0
            current_rotate_x_deg += cross * 2.4
            depth_shadow = f"{vw(3 + ripple * 2)} {vw(4 + cross * 1.5)} {vw(2.5)} rgba(0, 0, 0, 0.38)"
            if text_shadow_css == "text-shadow: none;":
                text_shadow_css = f"text-shadow: {depth_shadow};"
            else:
                text_shadow_css = text_shadow_css.rstrip(";") + f", {depth_shadow};"
            if current_filter_css == "filter: none;":
                current_filter_css = f"filter: drop-shadow({vw(cross * 2)} {vw(2 + ripple)} {vw(1.2)} rgba(255,255,255,0.16));"
        elif font_motion == "drift" and word_started:
            spread = idx - content_center
            drift_p = ease_in_out(clip_progress)
            current_translate_x_em += spread * 0.12 * drift_p
            current_translate_em += math.sin(idx * 1.37) * 0.035 * drift_p
        elif font_motion == "pulse" and word_started:
            pulse = max(0.0, math.sin(current_time * 8.0 + idx * 0.55))
            current_scale *= 1.0 + pulse * 0.11
            current_translate_em -= pulse * 0.025
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
            if font_motion in ("wave", "drift"):
                current_translate_em = per_word_translate
            if anim_type == "pop":
                current_scale = min(current_scale, 1.025)

        word_base = (
            f"font-size: {layout_font_scale:.3f}em; "
            f"transform: perspective(720px) translate({current_translate_x_em:.3f}em, {current_translate_em:.3f}em) scale({current_scale:.3f}) rotateY({current_rotate_y_deg:.3f}deg) rotateX({current_rotate_x_deg:.3f}deg); "
            f"transform-origin: center center; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); "
            f"letter-spacing: calc({ls_vw} + {vw(current_letter_extra)}); "
            f"margin-right: {word_margin_right}; white-space: nowrap; overflow-wrap: normal; word-break: keep-all; "
            f"break-inside: avoid; page-break-inside: avoid; box-sizing: border-box; line-height: inherit; "
            f"vertical-align: baseline; will-change: transform, opacity; backface-visibility: hidden; "
            f"{current_filter_css} {current_clip_css}"
        )

        fill_color = c_hl if is_current else c_txt
        if anim_type == "holy_breath" and is_holy_final_word and use_hl:
            fill_color = c_hl
        texture_css = ""
        texture_profiles = {
            "grain": (0.28, 0.18, "0.014em", "0.010em", "0.24em 0.22em", "0.32em 0.27em", 0.12),
            "noise": (0.42, 0.32, "0.010em", "0.007em", "0.16em 0.15em", "0.23em 0.21em", 0.08),
            "roughen": (0.66, 0.48, "0.040em", "0.025em", "0.38em 0.30em", "0.52em 0.42em", 0.26),
            "distressed": (0.86, 0.72, "0.052em", "0.032em", "0.46em 0.34em", "0.62em 0.48em", 0.38),
            "stacked_distress": (0.92, 0.78, "0.060em", "0.038em", "0.42em 0.31em", "0.58em 0.44em", 0.44),
        }
        if text_texture in texture_profiles:
            alpha_a, alpha_b, dot_a, dot_b, size_a, size_b, scratch_alpha = texture_profiles[text_texture]
            pos_a = f"{(idx * 17) % 31}% {(idx * 23) % 37}%"
            pos_b = f"{(idx * 29 + 11) % 43}% {(idx * 13 + 7) % 41}%"
            pos_c = f"{(idx * 19 + 5) % 47}% {(idx * 31 + 9) % 53}%"
            layers = [
                (f"radial-gradient(circle at 35% 45%, rgba(0,0,0,{alpha_a:.2f}) 0 {dot_a}, transparent calc({dot_a} + 0.006em))", size_a, pos_a),
                (f"radial-gradient(circle at 66% 28%, rgba(0,0,0,{alpha_b:.2f}) 0 {dot_b}, transparent calc({dot_b} + 0.005em))", size_b, pos_b),
                (f"repeating-linear-gradient(103deg, transparent 0 0.19em, rgba(0,0,0,{scratch_alpha:.2f}) 0.205em 0.222em, transparent 0.238em 0.42em)", "0.72em 0.58em", pos_b),
            ]
            if text_texture in ("noise", "stacked_distress"):
                layers.append((f"repeating-radial-gradient(circle at 30% 35%, rgba(0,0,0,{max(alpha_a - 0.08, 0.18):.2f}) 0 0.004em, transparent 0.006em 0.085em)", "0.19em 0.17em", pos_c))
            if text_texture in ("roughen", "distressed", "stacked_distress"):
                edge_alpha = 0.26 if text_texture == "roughen" else 0.34 if text_texture == "distressed" else 0.42
                layers.append((f"repeating-linear-gradient(8deg, rgba(0,0,0,{edge_alpha:.2f}) 0 0.018em, transparent 0.030em 0.155em)", "0.55em 0.36em", pos_c))
                layers.append((f"radial-gradient(ellipse at 52% 112%, rgba(0,0,0,{edge_alpha:.2f}) 0 0.055em, transparent 0.082em)", "0.34em 0.24em", pos_a))
            layers.append((f"linear-gradient({fill_color}, {fill_color})", "auto", "0 0"))
            texture_css = (
                f"-webkit-text-fill-color: transparent; "
                f"background-color: {fill_color}; "
                f"background-image: {', '.join(layer[0] for layer in layers)}; "
                f"background-size: {', '.join(layer[1] for layer in layers)}; "
                f"background-position: {', '.join(layer[2] for layer in layers)}; "
                f"background-repeat: repeat; "
                f"-webkit-background-clip: text; background-clip: text; "
            )

        word_css_fg = f"display: inline-block; color: {fill_color}; opacity: {current_opacity:.3f}; {text_shadow_css} {stroke_css} {texture_css} {word_base}"
        word_css_bg = f"display: inline-block; color: transparent; -webkit-text-fill-color: transparent; text-shadow: none; -webkit-text-stroke: transparent; opacity: {current_opacity:.3f}; {word_base}"

        if bg_mode == "tape":
            if is_current and hl_bg_a > 0:
                hl_css = f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; box-shadow: 0 0 0 {hl_spread_vw} rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}), 0 {vw(3)} {vw(10)} rgba({hl_r}, {hl_g}, {hl_b}, 0.25);"
                word_css_fg += hl_css
                word_css_bg += f" background-color: transparent; border-radius: {hl_rad_vw};"
        elif bg_mode == "block" and is_current and hl_bg_a > 0:
            word_css_fg += f" background-color: rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a}); border-radius: {hl_rad_vw}; box-shadow: 0 0 0 {hl_spread_vw} rgba({hl_r}, {hl_g}, {hl_b}, {hl_bg_a});"

        safe_txt = html.escape(clean_txt, quote=False)
        if head_letter_large_variant and idx == first_content_idx:
            initial_match = re.search(r"[A-Za-z0-9\u4e00-\u9fff]", clean_txt)
            if initial_match:
                initial_pos = initial_match.start()
                initial_scale = max(emphasis_scale / 100.0, 1.58)
                safe_txt = (
                    f"{html.escape(clean_txt[:initial_pos], quote=False)}"
                    f"<span style=\"display:inline-block; font-size:{initial_scale:.3f}em; "
                    f"line-height:0.78; vertical-align:-0.04em; margin-right:0.018em;\">"
                    f"{html.escape(clean_txt[initial_pos], quote=False)}</span>"
                    f"{html.escape(clean_txt[initial_pos + 1:], quote=False)}"
                )
        html_words_fg.append(f"<span style='{word_css_fg}'>{safe_txt}</span>")
        html_words_bg.append(f"<span style='{word_css_bg}'>{safe_txt}</span>")

        if idx < len(words) - 1:
            next_raw = str(words[idx + 1].get("text") or words[idx + 1].get("word") or "")
            if "\n" not in next_raw and not _layout_breaks_before(idx + 1):
                spacer = "<span style='display:inline-block; width:0.14em;'></span>" if layout_mode in ("contrast", "triple", "reel_stack", "random_focus", "side_steps", "axis_stack", "quote_stack") else " "
                html_words_fg.append(spacer)
                if bg_mode in ("tape", "block", "sweep"):
                    html_words_bg.append(spacer if layout_mode in ("contrast", "triple", "reel_stack", "random_focus", "side_steps", "axis_stack", "quote_stack") else " ")

    inner_html_fg = "".join(html_words_fg)
    inner_html_bg = "".join(html_words_bg)

    inner_transform_parts = []
    inner_extra_css = ""
    if anim_type == "roll_up":
        y_offset = (1.0 - clip_progress * 2) * 50
        inner_transform_parts.append(f"translateY({y_offset}vh)")
    elif anim_type == "slam_in":
        p = ease_out_cubic((current_time - clip_start) / max(0.05, pop_speed * 1.8))
        if p < 1.0:
            overshoot = math.sin(p * math.pi) * (0.10 + max(0, pop_bounce - 100) / 100.0 * 0.12)
            slam_scale = max(1.0, 4.2 - 3.2 * p + overshoot)
            slam_y = -18.0 * (1.0 - p)
            slam_rot = -7.0 * (1.0 - p)
            blur = 7.0 * (1.0 - p)
            inner_transform_parts.extend([
                f"translateY({slam_y:.3f}vh)",
                f"scale({slam_scale:.3f})",
                f"rotate({slam_rot:.3f}deg)",
            ])
            inner_extra_css = f"opacity: {p:.3f}; filter: blur({vw(blur)});"
        else:
            inner_transform_parts.append("scale(1)")
    elif anim_type == "camera_push":
        intro_p = ease_out_cubic((current_time - clip_start) / max(0.05, pop_speed * 1.4))
        push_p = ease_in_out(clip_progress)
        push_scale = (0.72 + 0.62 * push_p) * (0.86 + 0.14 * intro_p)
        push_y = 5.5 * (1.0 - intro_p)
        blur = 4.5 * (1.0 - intro_p)
        opacity = 0.35 + 0.65 * intro_p
        inner_transform_parts.extend([
            f"translateY({push_y:.3f}vh)",
            f"scale({push_scale:.3f})",
        ])
        inner_extra_css = f"opacity: {opacity:.3f}; filter: blur({vw(blur)});"
    elif anim_type == "depth_push":
        intro_p = ease_out_cubic((current_time - clip_start) / max(0.05, pop_speed * 1.8))
        breathe = math.sin(current_time * 2.35)
        sway = math.sin(current_time * 1.85 + 0.7)
        depth_scale = (0.42 + 0.72 * intro_p) * (1.0 + breathe * 0.022)
        depth_z = -220.0 * (1.0 - intro_p)
        depth_y = 6.5 * (1.0 - intro_p)
        rot_y = 12.0 * (1.0 - intro_p) + sway * 5.2
        rot_x = -3.5 * (1.0 - intro_p) + breathe * 1.4
        blur = 6.0 * (1.0 - intro_p)
        opacity = 0.18 + 0.82 * intro_p
        inner_transform_parts.extend([
            "perspective(900px)",
            f"translateY({depth_y:.3f}vh)",
            f"translateZ({depth_z:.1f}px)",
            f"scale({depth_scale:.3f})",
            f"rotateY({rot_y:.3f}deg)",
            f"rotateX({rot_x:.3f}deg)",
        ])
        inner_extra_css = f"opacity: {opacity:.3f}; filter: blur({vw(blur)}) drop-shadow({vw(8)} {vw(5)} {vw(1)} rgba(0,0,0,0.48)); transform-style: preserve-3d;"
    inner_transform = ""
    if inner_transform_parts:
        inner_transform = f"transform: {' '.join(inner_transform_parts)}; transform-origin: center center; {inner_extra_css}"

    # 👑 新增平滑边缘及抗锯齿
    base_wrapper_css = f"""
        font-family: '{f_fam}', sans-serif;
        font-size: {size_vw};
        font-weight: {f_weight};
        font-style: {f_style};
        letter-spacing: {ls_vw};
        word-spacing: {('0vw' if layout_mode in ('contrast', 'triple', 'reel_stack', 'random_focus', 'side_steps', 'axis_stack', 'quote_stack') else ws_vw)};
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
    elif bg_mode == "cinematic_frame":
        cinema_float_y = math.sin(current_time * 0.82 + clip_start * 0.37) * 0.055
        cinema_glow_p = 0.72 + 0.28 * math.sin(current_time * 1.05 + clip_start * 0.21)
        glass_a = max(0.10, min(0.34, bg_a * 0.34))
        veil_a = max(0.035, min(0.15, bg_a * 0.12))
        edge_a = max(0.13, min(0.36, 0.17 + hl_bg_a * 0.13))
        aura_a = max(0.09, min(0.26, 0.12 + bg_a * 0.10)) * cinema_glow_p
        warm_a = max(0.08, min(0.22, 0.11 + bg_a * 0.08)) * cinema_glow_p
        glass_radius_vw = vw(max(22, rad))
        glass_inner_radius_vw = vw(max(18, max(22, rad) * 0.86))
        glass_pad_top = vw(max(pad_top, pad / 2.0 + 8))
        glass_pad_right = vw(max(pad_right, pad + 18))
        glass_pad_bottom = vw(max(pad_bottom, pad / 2.0 + 9))
        glass_pad_left = vw(max(pad_left, pad + 18))
        frame_wrap_css = base_wrapper_css + f"""
            display: inline-block;
            position: relative;
            isolation: isolate;
            line-height: {max(0.8, float(lh))};
            white-space: normal;
            overflow-wrap: normal;
            word-break: normal;
            background:
                radial-gradient(ellipse at 18% 0%, rgba(255, 244, 218, {warm_a:.3f}) 0%, transparent 58%),
                radial-gradient(ellipse at 82% 100%, rgba(255, 205, 155, {veil_a:.3f}) 0%, transparent 62%),
                linear-gradient(135deg, rgba(255, 255, 255, {glass_a + 0.055:.3f}) 0%, rgba({r}, {g}, {b}, {glass_a:.3f}) 48%, rgba(255, 230, 195, {veil_a:.3f}) 100%);
            border: {vw(1.2)} solid rgba(255, 246, 224, {edge_a:.3f});
            border-radius: {glass_radius_vw};
            padding: {glass_pad_top} {glass_pad_right} {glass_pad_bottom} {glass_pad_left};
            text-align: {align};
            max-width: 100%;
            box-sizing: border-box;
            transform: translateY({cinema_float_y:.3f}em);
            box-shadow:
                0 0 {vw(16)} rgba(255, 229, 178, {edge_a * 0.42:.3f}),
                0 {vw(12)} {vw(38)} rgba(24, 18, 10, {0.18 + bg_a * 0.10:.3f}),
                0 0 {vw(48)} rgba(255, 214, 158, {aura_a:.3f}),
                inset 0 0 {vw(22)} rgba(255, 255, 255, 0.115),
                inset 0 {vw(1.2)} {vw(0.6)} rgba(255, 255, 255, 0.30);
            -webkit-backdrop-filter: blur({vw(14)}) saturate(1.16);
            backdrop-filter: blur({vw(14)}) saturate(1.16);
        """
        final_html = f"""
        <div class='sub-box' style='{outer_box_style}'>
            <div style="{inner_transform} width: 100%; display:flex; justify-content:{align_item}; text-align:{align};">
                <div style="{frame_wrap_css}">
                    <div style="position:absolute; inset:{vw(-5)}; z-index:-1; border-radius:inherit; pointer-events:none; background:radial-gradient(ellipse at 50% 50%, rgba(255, 230, 186, {aura_a:.3f}) 0%, rgba(255, 230, 186, {aura_a * 0.30:.3f}) 42%, transparent 72%); filter: blur({vw(18)}); opacity:{0.72 + cinema_glow_p * 0.18:.3f};"></div>
                    <div style="position:absolute; inset:{vw(1.5)}; z-index:0; border-radius:{glass_inner_radius_vw}; pointer-events:none; background:linear-gradient(115deg, rgba(255,255,255,0.16), transparent 28%, transparent 68%, rgba(255,226,188,0.10));"></div>
                    <div style="position:relative; z-index:1;">{inner_html_fg}</div>
                </div>
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


def render_signature_html(signature, current_time, proj_w=1080):
    config = normalize_signature_config(signature)
    text = str(config.get("text", "") or "").strip()
    if not config.get("enabled") or not text:
        return ""

    style = default_signature_style(None, scale_from_subtitle=False)
    if isinstance(config.get("style"), dict):
        style.update(config.get("style", {}))
    placement = str(config.get("placement", "top_right") or "top_right")
    margin_x = max(0.0, min(45.0, float(config.get("margin_x", 5.0) or 0.0)))
    margin_y = max(0.0, min(45.0, float(config.get("margin_y", 4.0) or 0.0)))
    pos_x = max(-100.0, min(100.0, float(config.get("pos_x", 0.0) or 0.0)))
    pos_y = max(-100.0, min(100.0, float(config.get("pos_y", -42.0) or 0.0)))

    align = str(style.get("text_align", "center") or "center") if placement == "custom" else "right" if "right" in placement else "left" if "left" in placement else "center"
    style["text_align"] = align
    style["anim_type"] = "none"
    style["font_motion"] = "none"
    style["use_hl"] = False

    end_time = max(float(current_time or 0.0) + 1.0, 1.0)
    sig_sub = {
        "text": text,
        "start": 0.0,
        "end": end_time,
        "words": [{"text": text, "start": 0.0, "end": end_time}],
        "style": style,
    }
    inner_html = render_subtitle_html(sig_sub, current_time, proj_w)

    if placement == "top_left":
        pos_css = f"left:{margin_x:.3f}%; top:{margin_y:.3f}%; text-align:left;"
    elif placement == "bottom_right":
        pos_css = f"right:{margin_x:.3f}%; bottom:{margin_y:.3f}%; text-align:right;"
    elif placement == "bottom_left":
        pos_css = f"left:{margin_x:.3f}%; bottom:{margin_y:.3f}%; text-align:left;"
    elif placement == "top_center":
        pos_css = f"left:50%; top:{margin_y:.3f}%; transform:translateX(-50%); text-align:center;"
    elif placement == "bottom_center":
        pos_css = f"left:50%; bottom:{margin_y:.3f}%; transform:translateX(-50%); text-align:center;"
    elif placement == "custom":
        pos_css = f"left:calc(50% + {pos_x:.3f}%); top:calc(50% + {pos_y:.3f}%); transform:translate(-50%, -50%); text-align:{align};"
    else:
        pos_css = f"right:{margin_x:.3f}%; top:{margin_y:.3f}%; text-align:right;"

    return f"""
    <div class="signature-overlay" style="position:absolute; {pos_css} z-index:90; max-width:72%; pointer-events:none; box-sizing:border-box;">
        {inner_html}
    </div>
    """


def render_design_html(design_state, current_time, proj_w=1080, proj_h=1920):
    state = normalize_design_room_state(design_state)
    pages = state.get("pages", [])
    if not pages:
        return ""

    t = max(0.0, float(current_time or 0.0))
    cursor = 0.0
    active_page = None
    page_local_time = 0.0
    for page in pages:
        dur = max(0.1, float(page.get("duration", 5.0) or 5.0))
        if cursor <= t < cursor + dur:
            active_page = page
            page_local_time = t - cursor
            break
        cursor += dur
    if active_page is None:
        return ""

    design_w = max(1.0, float(state.get("width", proj_w) or proj_w))
    design_h = max(1.0, float(state.get("height", proj_h) or proj_h))

    layer_html = []
    layers = sorted(
        active_page.get("layers", []) or [],
        key=lambda item: int(item.get("zIndex", 0) or 0)
    )
    page_dur = max(0.1, float(active_page.get("duration", 5.0) or 5.0))
    for layer in layers:
        start = max(0.0, float(layer.get("start", 0.0) or 0.0))
        end = float(layer.get("end", 0.0) or 0.0)
        if end <= 0:
            end = page_dur
        if not (start <= page_local_time < end):
            continue

        x_pct = float(layer.get("x", 0) or 0) * 100.0 / design_w
        y_pct = float(layer.get("y", 0) or 0) * 100.0 / design_h
        w_pct = max(0.01, float(layer.get("width", 1) or 1) * 100.0 / design_w)
        h_pct = max(0.01, float(layer.get("height", 1) or 1) * 100.0 / design_h)
        opacity = max(0.0, min(1.0, float(layer.get("opacity", 1) or 0)))
        rot = float(layer.get("rotation", 0) or 0)
        common = (
            f"position:absolute; left:{x_pct:.5f}%; top:{y_pct:.5f}%; "
            f"width:{w_pct:.5f}%; min-height:{h_pct:.5f}%; opacity:{opacity:.3f}; "
            f"transform:rotate({rot:.3f}deg); transform-origin:center center; "
            f"box-sizing:border-box; pointer-events:none;"
        )
        if layer.get("type") == "rect":
            fill = html.escape(str(layer.get("fill", "#000000") or "#000000"), quote=True)
            radius = float(layer.get("cornerRadius", 0) or 0) * 100.0 / design_w
            layer_html.append(
                f"<div style='{common} height:{h_pct:.5f}%; background:{fill}; border-radius:{radius:.5f}vw;'></div>"
            )
            continue
        if layer.get("type") == "image":
            src = html.escape(str(layer.get("src", "") or "").strip(), quote=True)
            if not src:
                continue
            fit = str(layer.get("fit", "cover") or "cover").strip().lower()
            object_fit = "fill" if fit == "stretch" else ("contain" if fit == "contain" else "cover")
            layer_html.append(
                f"<img src='{src}' style='{common} height:{h_pct:.5f}%; object-fit:{object_fit}; display:block;' />"
            )
            continue

        text = html.escape(str(layer.get("text", "") or ""), quote=False).replace("\n", "<br>")
        if not text:
            continue
        font_size = float(layer.get("fontSize", 48) or 48) * 100.0 / design_w
        family = html.escape(str(layer.get("fontFamily", "Noto Sans SC") or "Noto Sans SC"), quote=True)
        weight = html.escape(str(layer.get("fontWeight", "700") or "700"), quote=True)
        fill = html.escape(str(layer.get("fill", "#FFFFFF") or "#FFFFFF"), quote=True)
        align = html.escape(str(layer.get("align", "center") or "center"), quote=True)
        line_height = max(0.8, min(2.4, float(layer.get("lineHeight", 1.18) or 1.18)))
        bg = str(layer.get("background", "") or "").strip()
        bg_css = ""
        if bg:
            bg_css = f"background:{html.escape(bg, quote=True)}; border-radius:0.55vw; padding:0.5vw 0.85vw;"
        shadow_css = "text-shadow:0 0 0.45vw rgba(0,0,0,0.62), 0 0.28vw 0.85vw rgba(0,0,0,0.38);" if layer.get("shadow", True) else "text-shadow:none;"
        layer_html.append(
            f"<div style='{common} color:{fill}; font-family:\"{family}\", sans-serif; "
            f"font-size:{font_size:.5f}vw; font-weight:{weight}; line-height:{line_height}; "
            f"text-align:{align}; white-space:pre-wrap; overflow:hidden; {shadow_css} {bg_css}'>{text}</div>"
        )

    if not layer_html:
        return ""
    return (
        "<div class='design-overlay' style='position:absolute; inset:0; z-index:2; "
        "pointer-events:none; overflow:hidden; box-sizing:border-box;'>"
        + "\n".join(layer_html)
        + "</div>"
    )
