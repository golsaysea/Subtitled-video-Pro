# ==========================================
# 文件名: core.py (核心引擎与云端通信 - 智能寻路融合版)
# ==========================================
import os
import sys
import shutil
import json
import threading
import subprocess

try:
    import requests
except ImportError:
    pass

CONFIG_FILE = "settings.json"
EFFECTS_FILE = "effects.json"
CLOUD_SECRET = ""
DEFAULT_SYNC_URL = ""

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