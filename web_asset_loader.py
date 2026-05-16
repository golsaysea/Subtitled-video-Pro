import os
import sys

from PyQt6.QtCore import QUrl

from core import get_app_dir


def _candidate_roots():
    roots = []
    for base in (get_app_dir(), os.getcwd(), getattr(sys, "_MEIPASS", "")):
        if base and base not in roots:
            roots.append(base)
    return roots


def find_web_tool_index(tool_name):
    for root in _candidate_roots():
        path = os.path.join(root, "web_tools", "dist", tool_name, "index.html")
        if os.path.exists(path):
            return os.path.abspath(path)
    return ""


def load_web_tool_page(view, tool_name, fallback_html, fallback_base=None):
    index_path = find_web_tool_index(tool_name)
    if index_path:
        view.setUrl(QUrl.fromLocalFile(index_path))
        return True

    base = fallback_base or os.getcwd()
    view.setHtml(fallback_html, QUrl.fromLocalFile(base + os.sep))
    return False
