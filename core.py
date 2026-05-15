# ==========================================
# 文件名: core.py (核心引擎与云端通信 - 智能寻路融合版)
# ==========================================
import os
import sys
import shutil
import json
import threading
import subprocess
import time
import urllib.request

try:
    import requests
except ImportError:
    pass

CONFIG_FILE = "settings.json"
EFFECTS_FILE = "effects.json"
CLOUD_SECRET = "zdCp7M6mQaJFSr4qzUU5yVfsJDxaQzeZZtE2Ps4qbG1cAUU0zYfqNHRsIS1u0bdRBi4Ld1eu8OkXa7ZY3htClFuvwoEVvfh07xZSoy3uWDlpXWQfRBWMz7Q8"
DEFAULT_SYNC_URL = "https://sub.golsaysea.workers.dev/"
FFMPEG_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_ffmpeg_cmd():
    exe_name = "ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
    local_ffmpeg = os.path.join(get_app_dir(), exe_name)
    if os.path.exists(local_ffmpeg): 
        return local_ffmpeg
    if hasattr(sys, '_MEIPASS'):
        meipass_ffmpeg = os.path.join(sys._MEIPASS, exe_name)
        if os.path.exists(meipass_ffmpeg): 
            return meipass_ffmpeg
    if shutil.which(exe_name): 
        return exe_name
    return exe_name

def get_ffprobe_cmd():
    exe_name = "ffprobe.exe" if os.name == 'nt' else "ffprobe"
    local_ffprobe = os.path.join(get_app_dir(), exe_name)
    if os.path.exists(local_ffprobe):
        return local_ffprobe
    if hasattr(sys, '_MEIPASS'):
        meipass_ffprobe = os.path.join(sys._MEIPASS, exe_name)
        if os.path.exists(meipass_ffprobe):
            return meipass_ffprobe
    if shutil.which(exe_name):
        return exe_name
    return exe_name

def download_file_with_progress(url, dest_path, on_progress=None, is_cancelled=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Subtitle-Composer/1.0"})
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    start_time = time.monotonic()
    last_ui_update = 0.0
    downloaded = 0
    chunk_size = 1024 * 256

    with urllib.request.urlopen(req, timeout=30) as response:
        total_raw = response.headers.get("Content-Length") or response.headers.get("content-length")
        total_size = int(total_raw) if total_raw and total_raw.isdigit() else 0

        with open(dest_path, "wb") as f:
            while True:
                if is_cancelled and is_cancelled():
                    raise RuntimeError("用户取消了下载。")

                chunk = response.read(chunk_size)
                if not chunk:
                    break

                f.write(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                if on_progress and (now - last_ui_update >= 0.15):
                    last_ui_update = now
                    elapsed = max(now - start_time, 0.001)
                    speed = downloaded / elapsed
                    if total_size > 0:
                        percent = min(int(downloaded * 100 / total_size), 98)
                    else:
                        percent = 0
                    on_progress(percent, downloaded, total_size, speed)

    if on_progress:
        elapsed = max(time.monotonic() - start_time, 0.001)
        speed = downloaded / elapsed
        on_progress(99, downloaded, total_size, speed)

    return downloaded

def auto_sync_cloud_data(on_complete=None):
    def _sync_task():
        try:
            sync_url = DEFAULT_SYNC_URL
            config_path = os.path.join(os.getcwd(), CONFIG_FILE)
            config_data = {}
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        sync_url = config_data.get("sync_url", DEFAULT_SYNC_URL)
                except: pass

            if not sync_url: return

            headers = {"X-App-Auth": CLOUD_SECRET}
            res = requests.get(sync_url, headers=headers, timeout=10, verify=False)
            if res.status_code != 200: return
                
            data = res.json()
            
            if "cf_accounts" in data:
                config_data["cf_accounts"] = data["cf_accounts"]
                config_data["sync_url"] = sync_url
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)

            has_effects = False
            effects_path = os.path.join(os.getcwd(), EFFECTS_FILE)
            try:
                with open(effects_path, "r", encoding="utf-8") as f: 
                    local_effects = json.load(f)
            except: 
                local_effects = {"basic": {}, "viral": {}}
            
            if "effects_basic" in data:
                local_effects["basic"] = data["effects_basic"]
                has_effects = True
            if "effects_viral" in data:
                local_effects["viral"] = data["effects_viral"]
                has_effects = True
                
            if has_effects:
                with open(effects_path, "w", encoding="utf-8") as f: 
                    json.dump(local_effects, f, indent=4, ensure_ascii=False)
            
            if on_complete:
                on_complete()
                
        except Exception as e:
            pass

    threading.Thread(target=_sync_task, daemon=True).start()
