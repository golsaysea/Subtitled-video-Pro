import json
import os

from font_registry import (
    STATUS_APPROVED,
    STATUS_LABELS,
    STATUS_NONCOMMERCIAL,
    STATUS_OPEN,
    STATUS_REVIEW,
    STATUS_SYSTEM,
    audit_project_fonts,
)
from project_io import get_project_folders, get_reels_in_folder, load_project


def _is_inside(path, folder):
    if not path or not folder:
        return False
    try:
        path_abs = os.path.abspath(path)
        folder_abs = os.path.abspath(folder)
        return os.path.commonpath([path_abs, folder_abs]) == folder_abs
    except Exception:
        return False


def _media_entries(project_data):
    entries = []
    edit_state = project_data.get("room_state", {}).get("edit_room", {}) if isinstance(project_data, dict) else {}
    if not isinstance(edit_state, dict):
        return entries

    for idx, clip in enumerate(edit_state.get("video_clips", []) or [], start=1):
        if not isinstance(clip, dict):
            continue
        path = clip.get("path", "")
        if path:
            entries.append({"kind": "video", "label": f"V{idx}", "path": path})

    audio_path = edit_state.get("audio_path", "")
    if audio_path:
        entries.append({"kind": "audio", "label": "A1", "path": audio_path})
    return entries


def audit_project(project_data, workspace=""):
    project_data = project_data or {}
    project_path = project_data.get("project_path", "")
    project_dir = project_data.get("project_dir") or os.path.dirname(project_path)
    media_rows = []
    missing_media = []
    external_media = []

    for entry in _media_entries(project_data):
        path = entry.get("path", "")
        exists = bool(path and os.path.exists(path))
        inside_project = exists and _is_inside(path, project_dir)
        inside_workspace = exists and _is_inside(path, workspace) if workspace else inside_project
        row = {
            **entry,
            "exists": exists,
            "inside_project": inside_project,
            "inside_workspace": inside_workspace,
        }
        media_rows.append(row)
        if not exists:
            missing_media.append(row)
        elif not inside_project:
            external_media.append(row)

    font_audit = audit_project_fonts(project_data)
    warnings = []
    if missing_media:
        warnings.append(f"{len(missing_media)} missing media file(s)")
    if external_media:
        warnings.append(f"{len(external_media)} media file(s) outside project assets")
    if font_audit["summary"].get(STATUS_REVIEW, 0):
        warnings.append(f"{font_audit['summary'][STATUS_REVIEW]} unregistered font(s)")
    if font_audit["summary"].get(STATUS_SYSTEM, 0):
        warnings.append(f"{font_audit['summary'][STATUS_SYSTEM]} system font(s) need license/embedding review")
    if font_audit["summary"].get(STATUS_NONCOMMERCIAL, 0):
        warnings.append(f"{font_audit['summary'][STATUS_NONCOMMERCIAL]} non-commercial/restricted font(s)")

    return {
        "project_name": project_data.get("project_name", os.path.splitext(os.path.basename(project_path))[0]),
        "project_path": project_path,
        "project_dir": project_dir,
        "media": media_rows,
        "missing_media": missing_media,
        "external_media": external_media,
        "fonts": font_audit,
        "warnings": warnings,
        "ok": not warnings,
    }


def scan_folder(folder_path, workspace=""):
    folder_path = os.path.abspath(folder_path)
    project_reports = []
    for reel_path in get_reels_in_folder(folder_path, recursive=True):
        try:
            project_reports.append(audit_project(load_project(reel_path), workspace=workspace))
        except Exception as exc:
            project_reports.append({
                "project_name": os.path.splitext(os.path.basename(reel_path))[0],
                "project_path": reel_path,
                "project_dir": folder_path,
                "media": [],
                "missing_media": [],
                "external_media": [],
                "fonts": {"fonts": [], "summary": {}, "needs_review": []},
                "warnings": [f"load failed: {exc}"],
                "ok": False,
            })
    return _summarize_scan({
        "scope": "folder",
        "folder_path": folder_path,
        "workspace": workspace,
        "projects": project_reports,
    })


def scan_workspace(workspace):
    workspace = os.path.abspath(workspace)
    all_reports = []
    for folder_name in get_project_folders(workspace):
        folder_path = os.path.join(workspace, folder_name)
        folder_report = scan_folder(folder_path, workspace=workspace)
        all_reports.extend(folder_report.get("projects", []))
    return _summarize_scan({
        "scope": "workspace",
        "folder_path": "",
        "workspace": workspace,
        "projects": all_reports,
    })


def _summarize_scan(report):
    projects = report.get("projects", [])
    font_summary = {STATUS_APPROVED: 0, STATUS_OPEN: 0, STATUS_SYSTEM: 0, STATUS_NONCOMMERCIAL: 0, STATUS_REVIEW: 0}
    for project in projects:
        for status, count in project.get("fonts", {}).get("summary", {}).items():
            font_summary[status] = font_summary.get(status, 0) + count
    report["summary"] = {
        "project_count": len(projects),
        "warning_projects": sum(1 for item in projects if not item.get("ok")),
        "missing_media": sum(len(item.get("missing_media", [])) for item in projects),
        "external_media": sum(len(item.get("external_media", [])) for item in projects),
        "font_summary": font_summary,
    }
    return report


def _short_path(path, base=""):
    if not path:
        return ""
    try:
        if base:
            return os.path.relpath(path, base)
    except Exception:
        pass
    return path


def format_project_audit_report(project, workspace=""):
    lines = [f"工程: {project.get('project_name') or 'Untitled'}"]
    if project.get("project_path"):
        lines.append(f"文件: {_short_path(project.get('project_path'), workspace)}")

    missing = project.get("missing_media", [])
    external = project.get("external_media", [])
    font_rows = project.get("fonts", {}).get("fonts", [])
    font_summary = project.get("fonts", {}).get("summary", {})

    lines.append("")
    lines.append(f"素材: {len(project.get('media', []))} 个，缺失 {len(missing)} 个，外部引用 {len(external)} 个")
    for row in missing[:12]:
        lines.append(f"  [缺失] {row.get('label')}: {row.get('path')}")
    for row in external[:12]:
        lines.append(f"  [外部] {row.get('label')}: {row.get('path')}")
    if len(missing) > 12 or len(external) > 12:
        lines.append("  ...还有更多素材问题，建议先整理到工程 assets。")

    lines.append("")
    lines.append(
        "字体: "
        f"已确认 {font_summary.get(STATUS_APPROVED, 0)}，"
        f"开源 {font_summary.get(STATUS_OPEN, 0)}，"
        f"系统 {font_summary.get(STATUS_SYSTEM, 0)}，"
        f"待确认 {font_summary.get(STATUS_REVIEW, 0)}"
    )
    if font_summary.get(STATUS_NONCOMMERCIAL, 0):
        lines.append(f"Restricted non-commercial fonts: {font_summary.get(STATUS_NONCOMMERCIAL, 0)}")
    for row in font_rows:
        status = STATUS_LABELS.get(row.get("status"), STATUS_LABELS[STATUS_REVIEW])
        lines.append(f"  [{status}] {row.get('font')} - {row.get('notes', '')}")
    return "\n".join(lines)


def format_scan_report(report):
    summary = report.get("summary", {})
    workspace = report.get("workspace", "")
    lines = []
    title = "工作区体检" if report.get("scope") == "workspace" else "项目文件夹体检"
    lines.append(title)
    if report.get("folder_path"):
        lines.append(f"范围: {report.get('folder_path')}")
    elif workspace:
        lines.append(f"范围: {workspace}")
    lines.append("")
    lines.append(
        f"工程数: {summary.get('project_count', 0)} | "
        f"有风险工程: {summary.get('warning_projects', 0)} | "
        f"缺素材: {summary.get('missing_media', 0)} | "
        f"外部素材: {summary.get('external_media', 0)}"
    )
    fs = summary.get("font_summary", {})
    lines.append(
        f"字体状态: 已确认 {fs.get(STATUS_APPROVED, 0)}，"
        f"开源 {fs.get(STATUS_OPEN, 0)}，"
        f"系统 {fs.get(STATUS_SYSTEM, 0)}，"
        f"待确认 {fs.get(STATUS_REVIEW, 0)}"
    )
    lines.append("")

    if fs.get(STATUS_NONCOMMERCIAL, 0):
        lines.append(f"Restricted non-commercial fonts: {fs.get(STATUS_NONCOMMERCIAL, 0)}")

    warning_projects = [item for item in report.get("projects", []) if not item.get("ok")]
    if not warning_projects:
        lines.append("没有发现缺素材、外部素材或字体登记风险。")
    else:
        lines.append("需要处理的工程:")
        for project in warning_projects[:30]:
            warnings = "；".join(project.get("warnings", []))
            lines.append(f"- {project.get('project_name')}: {warnings}")
        if len(warning_projects) > 30:
            lines.append(f"...还有 {len(warning_projects) - 30} 个工程未展开。")

    lines.append("")
    lines.append("详细工程:")
    for project in report.get("projects", [])[:60]:
        lines.append("")
        lines.append(format_project_audit_report(project, workspace=workspace))
    if len(report.get("projects", [])) > 60:
        lines.append("\n工程数量较多，报告只展开前 60 个。")
    return "\n".join(lines)


def scan_to_json(report):
    return json.dumps(report, indent=2, ensure_ascii=False)
