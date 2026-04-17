# ==========================================
# 文件名: project_io.py (支持二级目录与封面抓取)
# ==========================================
import os
import copy
import json
from datetime import datetime
import shutil

PROJECT_VERSION = 4

def _base_project_data(path, project_type, project_name):
    return {
        "project_name": project_name,
        "project_path": path,  
        "project_dir": os.path.dirname(path), 
        "project_type": project_type,
        "project_version": PROJECT_VERSION,
        "cover_img": f"{project_name}_cover.jpg", # 每个 Reel 独立的封面图
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "media_files": {},
        "room_state": {
            "edit_room": {
                "video_clips": [], "audio_path": "", "subs_data": [], 
                "duration": 10.0, "resolution": "原画检测 (自动跟随)",
                "v_scale": 100, "v_volume": 100, "a_volume": 100,
                "chunk_mode": "双行大段 (约10字，智能折行)",
                "default_pos_x": 0.0, "default_pos_y": 25.0, "default_style": {}
            }
        },
        "subs_data": [],
        "timeline": []
    }

def ensure_project_schema(data, path=None):
    data = copy.deepcopy(data) if data else {}
    project_type = data.get("project_type", "edit_room")
    project_path = path or data.get("project_path", "")
    project_name = data.get("project_name", os.path.basename(project_path).replace(".scomp", "") if project_path else "未命名Reel")
    
    base = _base_project_data(project_path, project_type, project_name)
    merged = copy.deepcopy(base)
    merged.update(data)
    
    merged["project_path"] = project_path or merged.get("project_path", "")
    merged["project_dir"] = os.path.dirname(merged["project_path"]) if merged["project_path"] else ""
    merged["project_type"] = project_type
    merged["project_version"] = PROJECT_VERSION
    merged["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    room_state = copy.deepcopy(base["room_state"])
    room_state.update(data.get("room_state", {}))
    merged["room_state"] = room_state

    return merged

# 👑 获取所有项目文件夹 (一级目录)
def get_project_folders(workspace):
    folders = []
    if os.path.exists(workspace):
        for item in os.listdir(workspace):
            p = os.path.join(workspace, item)
            if os.path.isdir(p):
                folders.append(item)
    return sorted(folders)

# 👑 获取某个文件夹下的所有 Reels (二级目录)
def get_reels_in_folder(folder_path):
    reels = []
    if os.path.exists(folder_path):
        for item in os.listdir(folder_path):
            if item.lower().endswith(".scomp"):
                p = os.path.join(folder_path, item)
                reels.append({"path": p, "mtime": os.path.getmtime(p)})
    reels.sort(key=lambda x: x["mtime"], reverse=True)
    return [r["path"] for r in reels]

def create_reel(project_dir, reel_name, project_type="edit_room"):
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)
    safe_name = "".join(c for c in reel_name if c not in r'\/:*?"<>|')
    scomp_path = os.path.join(project_dir, f"{safe_name}.scomp")
    data = ensure_project_schema(_base_project_data(scomp_path, project_type, safe_name), scomp_path)
    save_project(scomp_path, data)
    return data

def load_project(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ensure_project_schema(data, path)

def save_project(path, data):
    normalized = ensure_project_schema(data, path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    return normalized

def update_room_state(project_data, room_name, room_payload):
    project_data = ensure_project_schema(project_data, project_data.get("project_path"))
    project_data.setdefault("room_state", {})[room_name] = copy.deepcopy(room_payload)

    if room_name == "edit_room":
        project_data["subs_data"] = copy.deepcopy(room_payload.get("subs_data", []))
        project_data["timeline"] = copy.deepcopy(room_payload.get("video_clips", []))
        media_files = project_data.setdefault("media_files", {})
        media_files["video_clips"] = copy.deepcopy(room_payload.get("video_clips", []))
        media_files["audio_path"] = room_payload.get("audio_path", "")
        if room_payload.get("cover_img"):
            project_data["cover_img"] = room_payload.get("cover_img")

    path = project_data.get("project_path")
    if path:
        project_data = save_project(path, project_data)
    return project_data

def load_or_create_default_project(workspace=None):
    workspace = workspace or os.path.join(os.getcwd(), "MyWorkspace")
    if not os.path.exists(workspace): os.makedirs(workspace)
    folders = get_project_folders(workspace)
    if not folders:
        default_folder = os.path.join(workspace, "默认项目")
        os.makedirs(default_folder)
        return create_reel(default_folder, "第一条Reel", "edit_room")
    
    first_folder = os.path.join(workspace, folders[0])
    reels = get_reels_in_folder(first_folder)
    if reels: return load_project(reels[0])
    return create_reel(first_folder, "第一条Reel", "edit_room")