import hashlib
import json
import os
from datetime import datetime, timedelta

from workspace_config import CONFIG_FILE


CLOUD_DIR = ".subtitle_cloud"
MANIFEST_FILE = "manifest.json"
LOCKS_DIR = "locks"
DEFAULT_LOCK_HOURS = 8


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _load_settings():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_cloud_identity():
    data = _load_settings()
    ident = data.get("cloud_identity", {}) if isinstance(data.get("cloud_identity"), dict) else {}
    return {
        "name": ident.get("name") or os.environ.get("USERNAME") or "Cloud User",
        "email": ident.get("email", ""),
    }


def save_cloud_identity(email, name=None):
    data = _load_settings()
    current = get_cloud_identity()
    data["cloud_identity"] = {
        "email": (email or "").strip(),
        "name": (name or current.get("name") or "").strip() or "Cloud User",
    }
    _save_settings(data)
    return data["cloud_identity"]


def cloud_meta_dir(workspace):
    return os.path.join(workspace, CLOUD_DIR)


def ensure_cloud_workspace(workspace):
    meta_dir = cloud_meta_dir(workspace)
    os.makedirs(os.path.join(meta_dir, LOCKS_DIR), exist_ok=True)
    manifest_path = os.path.join(meta_dir, MANIFEST_FILE)
    if not os.path.exists(manifest_path):
        save_manifest(workspace, {
            "schema": 1,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "share": {
                "mode": "private",
                "members": [],
                "link": "",
            },
            "projects": [],
        })
    return meta_dir


def load_manifest(workspace):
    ensure_cloud_workspace(workspace)
    path = os.path.join(cloud_meta_dir(workspace), MANIFEST_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault("schema", 1)
    data.setdefault("share", {"mode": "private", "members": [], "link": ""})
    data.setdefault("projects", [])
    return data


def save_manifest(workspace, data):
    meta_dir = cloud_meta_dir(workspace)
    os.makedirs(meta_dir, exist_ok=True)
    data["updated_at"] = now_iso()
    path = os.path.join(meta_dir, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data


def scan_workspace_projects(workspace):
    projects = []
    if not os.path.isdir(workspace):
        return projects
    for folder_name in sorted(os.listdir(workspace)):
        if folder_name == CLOUD_DIR:
            continue
        folder_path = os.path.join(workspace, folder_name)
        if not os.path.isdir(folder_path):
            continue
        reels = []
        try:
            for name in sorted(os.listdir(folder_path)):
                if name.lower().endswith(".scomp"):
                    path = os.path.join(folder_path, name)
                    reels.append({
                        "name": os.path.splitext(name)[0],
                        "path": os.path.join(folder_name, name).replace("\\", "/"),
                        "mtime": os.path.getmtime(path),
                    })
        except Exception:
            reels = []
        if reels:
            projects.append({
                "name": folder_name,
                "reel_count": len(reels),
                "reels": reels,
                "updated_at": now_iso(),
            })
    return projects


def update_manifest_from_workspace(workspace):
    data = load_manifest(workspace)
    data["projects"] = scan_workspace_projects(workspace)
    return save_manifest(workspace, data)


def get_share_config(workspace):
    return load_manifest(workspace).get("share", {})


def set_share_config(workspace, mode, members=None, link=""):
    data = load_manifest(workspace)
    data["share"] = {
        "mode": mode or "private",
        "members": members or [],
        "link": link or "",
    }
    return save_manifest(workspace, data)["share"]


def _lock_id(workspace, project_path):
    rel = os.path.relpath(project_path, workspace).replace("\\", "/")
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()
    return digest, rel


def lock_path_for_project(workspace, project_path):
    lock_id, _ = _lock_id(workspace, project_path)
    return os.path.join(cloud_meta_dir(workspace), LOCKS_DIR, f"{lock_id}.json")


def read_project_lock(workspace, project_path):
    ensure_cloud_workspace(workspace)
    path = lock_path_for_project(workspace, project_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except Exception:
        return None
    expires_at = lock.get("expires_at", "")
    try:
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
            os.remove(path)
            return None
    except Exception:
        pass
    return lock


def acquire_project_lock(workspace, project_path, identity, ttl_hours=DEFAULT_LOCK_HOURS):
    ensure_cloud_workspace(workspace)
    current = read_project_lock(workspace, project_path)
    email = (identity or {}).get("email", "")
    if current and current.get("email") and current.get("email") != email:
        return False, current

    _, rel = _lock_id(workspace, project_path)
    expires = datetime.now() + timedelta(hours=ttl_hours)
    lock = {
        "path": rel,
        "email": email,
        "name": (identity or {}).get("name", ""),
        "locked_at": now_iso(),
        "expires_at": expires.isoformat(timespec="seconds"),
    }
    with open(lock_path_for_project(workspace, project_path), "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    return True, lock


def release_project_lock(workspace, project_path, identity):
    path = lock_path_for_project(workspace, project_path)
    lock = read_project_lock(workspace, project_path)
    email = (identity or {}).get("email", "")
    if lock and lock.get("email") and lock.get("email") != email:
        return False
    if os.path.exists(path):
        os.remove(path)
    return True
