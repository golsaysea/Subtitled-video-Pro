import re

from PyQt6.QtWidgets import QWidget


ROLE_SOURCE_COLORS = {
    "bg": ("#11111b", "#0f1220", "#f5f7f1"),
    "panel": ("#181825", "#171a2b", "#fbfcf7"),
    "panel_2": ("#1e1e2e", "#20243a", "#edf3e7", "#242438", "#1b1d31", "#232634"),
    "card": ("#232742",),
    "card_hover": ("#2b3150", "#eef5e9"),
    "text": ("#cdd6f4", "#eef2ff", "#263226"),
    "muted": ("#a6adc8", "#aeb8d6", "#687866", "#7f849c", "#6c7086"),
    "accent": ("#89b4fa", "#8aa3ff", "#557b5f", "#b4befe", "#cba6f7", "#f5c2e7"),
    "accent_2": ("#a6e3a1", "#7fc7d9", "#6c8a59", "#74c7ec", "#94d38f", "#81c8be"),
    "warn": ("#f9e2af", "#d8b871", "#8f7438", "#f59e0b", "#d97706", "#f5d58b"),
    "danger": ("#f38ba8", "#e98aa2", "#b45d65"),
    "border": ("#313244", "#3a4062", "#d8e0cf"),
    "input": ("#121628", "#fffefa", "#25262b"),
    "selected": ("#cfe3c4",),
    "selected_text": ("#0b1020", "#1e2b1f"),
    "hint": ("#151a2e", "#edf4e8"),
}


def _replacement_map(colors):
    replacements = {}
    for role, source_colors in ROLE_SOURCE_COLORS.items():
        target = colors.get(role)
        if not target:
            continue
        for source in source_colors:
            replacements[source.lower()] = target
    return replacements


def retint_stylesheet(style, colors):
    if not style:
        return style

    tinted = re.sub(
        r"(selection-background-color\s*:\s*)#313244\b",
        rf"\g<1>{colors['selected']}",
        style,
        flags=re.IGNORECASE,
    )
    tinted = re.sub(
        r"(background(?:-color)?\s*:\s*)#313244\b",
        rf"\g<1>{colors['panel_2']}",
        tinted,
        flags=re.IGNORECASE,
    )
    replacements = _replacement_map(colors)

    def replace_hex(match):
        source = match.group(0).lower()
        return replacements.get(source, match.group(0))

    tinted = re.sub(r"#[0-9a-fA-F]{6}\b", replace_hex, tinted)
    if "#000000" not in style.lower():
        tinted = re.sub(r"color\s*:\s*white\b", f"color: {colors['text']}", tinted, flags=re.IGNORECASE)
    tinted = re.sub(r"color\s*:\s*gray\b", f"color: {colors['muted']}", tinted, flags=re.IGNORECASE)
    return tinted


def room_base_stylesheet(colors):
    return f"""
        QWidget {{
            background-color: {colors['bg']};
            color: {colors['text']};
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial;
        }}
        QLabel {{
            color: {colors['text']};
            background: transparent;
            border: none;
        }}
        QFrame {{
            background-color: {colors['panel']};
            border-color: {colors['border']};
        }}
        QScrollArea, QStackedWidget {{
            background: transparent;
            border: none;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {colors['input']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 6px;
            selection-background-color: {colors['selected']};
            selection-color: {colors['selected_text']};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {colors['accent']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors['panel']};
            color: {colors['text']};
            selection-background-color: {colors['selected']};
            selection-color: {colors['selected_text']};
            border: 1px solid {colors['border']};
            outline: none;
        }}
        QPushButton {{
            background-color: {colors['panel_2']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 6px 10px;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background-color: {colors['card_hover']};
            border-color: {colors['accent']};
        }}
        QPushButton:checked {{
            background-color: {colors['selected']};
            color: {colors['selected_text']};
            border-color: {colors['accent']};
        }}
        QPushButton:disabled {{
            background-color: {colors['border']};
            color: {colors['muted']};
        }}
        QCheckBox {{
            color: {colors['text']};
            background: transparent;
        }}
        QTabWidget::pane {{
            background-color: {colors['panel']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
        }}
        QTabBar::tab {{
            background-color: {colors['panel']};
            color: {colors['muted']};
            padding: 8px 14px;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
        }}
        QTabBar::tab:selected {{
            background-color: {colors['panel_2']};
            color: {colors['accent_2']};
            font-weight: 800;
        }}
        QProgressBar {{
            border: 1px solid {colors['border']};
            border-radius: 6px;
            text-align: center;
            color: {colors['text']};
            background-color: {colors['input']};
            font-weight: 700;
        }}
        QProgressBar::chunk {{
            background-color: {colors['accent_2']};
            border-radius: 4px;
        }}
        QSplitter::handle {{
            background-color: {colors['border']};
            margin: 2px;
        }}
        QMenu {{
            background-color: {colors['panel']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            padding: 6px;
        }}
        QMenu::item {{
            padding: 7px 24px 7px 12px;
            border-radius: 5px;
        }}
        QMenu::item:selected {{
            background-color: {colors['selected']};
            color: {colors['selected_text']};
        }}
    """


def apply_tinted_styles(widget, colors):
    if not isinstance(widget, QWidget):
        return
    widget.setStyleSheet(room_base_stylesheet(colors))
    for child in widget.findChildren(QWidget):
        style = child.styleSheet()
        if style:
            child.setStyleSheet(retint_stylesheet(style, colors))


def web_theme_script(colors, theme_key=""):
    css_vars = {
        "--bg": colors["bg"],
        "--panel": colors["panel"],
        "--panel-2": colors["panel_2"],
        "--surface": colors["card"],
        "--field": colors["input"],
        "--line": colors["border"],
        "--line-strong": colors["accent"],
        "--text": colors["text"],
        "--muted": colors["muted"],
        "--soft": colors["muted"],
        "--accent": colors["accent"],
        "--accent-2": colors["accent_2"],
        "--danger": colors["danger"],
        "--warn": colors["warn"],
        "--overlay": "rgba(15, 18, 32, 0.18)" if theme_key == "light_care" else "rgba(3, 6, 10, 0.68)",
        "--shadow": "0 18px 48px rgba(85, 123, 95, 0.12)" if theme_key == "light_care" else "0 20px 60px rgba(0, 0, 0, 0.32)",
        "--bg-body": colors["bg"],
        "--bg-sidebar": colors["panel"],
        "--bg-content": colors["bg"],
        "--bg-card": colors["panel_2"],
        "--bg-modal": colors["panel"],
        "--bg-input": colors["input"],
        "--text-main": colors["text"],
        "--text-sub": colors["muted"],
        "--primary": colors["accent"],
        "--primary-hover": colors["accent_2"],
        "--success": colors["accent_2"],
        "--border": colors["border"],
        "--bg-main": colors["bg"],
    }
    assignments = "\n".join(
        f"root.style.setProperty({name!r}, {value!r});"
        for name, value in css_vars.items()
    )
    mode = "light" if theme_key == "light_care" else "dark"
    overrides = f"""
        html, body, #app {{ background: {colors['bg']} !important; color: {colors['text']} !important; }}
        .sc-tool {{ background: {colors['bg']} !important; }}
        .sc-sidebar, .sc-topbar, .sc-footer, .content-toolbar, .content-footer {{
            background: {colors['panel']} !important;
            border-color: {colors['border']} !important;
        }}
        .sc-main, .content-area, .sc-list {{ background: {colors['bg']} !important; }}
        .sc-card, .sc-editor-card, .sc-modal-panel, .modal-panel, .card, .account-status-card, .settings-panel {{
            background: {colors['panel_2']} !important;
            border-color: {colors['border']} !important;
        }}
        input, select, textarea, .sc-field, .sc-select, .sc-textarea {{
            background: {colors['input']} !important;
            color: {colors['text']} !important;
            border-color: {colors['border']} !important;
        }}
        button, .sc-button, .sc-icon-button, .icon-btn-round, .tool-btn-icon, .icon-btn-small {{
            border-color: {colors['border']} !important;
        }}
        .sc-account-quota, .sc-note, .sc-label, .sc-status, .sc-title span {{
            color: {colors['muted']} !important;
        }}
        .sc-button.success, .btn-primary, .primary {{
            background: {colors['accent_2']} !important;
            color: {colors['selected_text']} !important;
        }}
        .sc-button.primary {{
            background: {colors['accent']} !important;
            color: {colors['selected_text']} !important;
        }}
    """
    return f"""
        (() => {{
            const root = document.documentElement;
            root.dataset.scTheme = {mode!r};
            root.style.colorScheme = {mode!r};
            document.body && document.body.classList.toggle('dark-mode', {mode == 'dark'});
            {assignments}
            let style = document.getElementById('subtitle-composer-theme-overrides');
            if (!style) {{
                style = document.createElement('style');
                style.id = 'subtitle-composer-theme-overrides';
                document.head.appendChild(style);
            }}
            style.textContent = {overrides!r};
        }})();
    """
