import csv
import json
import os
import re
import threading
import wave

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from web_asset_loader import load_web_tool_page
from app_theme import web_theme_script

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:
    QWebChannel = None
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False


SETTINGS_FILE = os.path.join(os.getcwd(), "settings.json")
DEFAULT_API_KEY_LINK = "https://elevenlabs.io/app/settings/api-keys"


def _safe_filename(text, fallback="voice"):
    clean = re.sub(r"[\r\n\t]+", " ", text or "").strip()
    clean = re.sub(r'[\\/:*?"<>|]', "_", clean)
    clean = re.sub(r"\s+", " ", clean)[:36].strip()
    return clean or fallback


def _load_app_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_app_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _json(data):
    return json.dumps(data, ensure_ascii=False)


def _float_value(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_config(raw_format):
    if raw_format == "mp3_as_mp4":
        return "mp3_44100_128", "mp4"
    if raw_format == "pcm_44100":
        return raw_format, "wav"
    return raw_format or "mp3_44100_128", "mp3"


def _write_audio_file(path, content, api_format):
    if api_format == "pcm_44100":
        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(content)
        return
    with open(path, "wb") as f:
        f.write(content)


class ElevenLabsBridge(QObject):
    event = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False

    def emit_event(self, event_type, **payload):
        payload["type"] = event_type
        self.event.emit(_json(payload))

    def _tool_settings(self):
        return _load_app_settings().get("elevenlabs_tool", {})

    def _state_from_settings(self):
        data = self._tool_settings()
        accounts = list(data.get("accounts", []) or [])
        legacy_key = data.get("api_key", "")
        if legacy_key and not any(a.get("key") == legacy_key for a in accounts):
            accounts.append({"alias": "账号 1", "key": legacy_key})
        current_key = data.get("current_account_key") or legacy_key
        if not current_key and accounts:
            current_key = accounts[0].get("key", "")
        return {
            "accounts": accounts,
            "currentKey": current_key,
            "voiceId": data.get("voice_id", ""),
            "model": data.get("model", "eleven_multilingual_v2"),
            "format": data.get("format", "mp3_44100_128"),
            "outputDir": data.get("output_dir", ""),
            "stability": float(data.get("stability", 0.5)),
            "similarity": float(data.get("similarity", 0.75)),
            "style": float(data.get("style", 0.0)),
            "speakerBoost": bool(data.get("speaker_boost", True)),
            "clearAfter": bool(data.get("clear_after", False)),
            "splitMode": int(data.get("split_mode", 0)),
            "apiKeyLink": data.get("api_key_link", DEFAULT_API_KEY_LINK),
            "cards": list(data.get("cards", []) or [""]),
        }

    def _save_state_dict(self, state):
        accounts = list(state.get("accounts", []) or [])
        current_key = state.get("currentKey", "") or state.get("api_key", "")
        if current_key and not any(a.get("key") == current_key for a in accounts):
            accounts.append({"alias": f"账号 {len(accounts) + 1}", "key": current_key})
        all_settings = _load_app_settings()
        all_settings["elevenlabs_tool"] = {
            "api_key": current_key,
            "accounts": accounts,
            "current_account_key": current_key,
            "voice_id": state.get("voiceId", ""),
            "model": state.get("model", "eleven_multilingual_v2"),
            "format": state.get("format", "mp3_44100_128"),
            "output_dir": state.get("outputDir", ""),
            "stability": _float_value(state.get("stability"), 0.5),
            "similarity": _float_value(state.get("similarity"), 0.75),
            "style": _float_value(state.get("style"), 0.0),
            "speaker_boost": bool(state.get("speakerBoost", True)),
            "clear_after": bool(state.get("clearAfter", False)),
            "split_mode": int(state.get("splitMode", 0) or 0),
            "api_key_link": state.get("apiKeyLink") or DEFAULT_API_KEY_LINK,
            "cards": list(state.get("cards", []) or [""]),
        }
        _save_app_settings(all_settings)

    def _update_account_quota(self, key, left, limit):
        state = self._state_from_settings()
        changed = False
        for account in state["accounts"]:
            if account.get("key") == key:
                account["quota_left"] = left
                account["quota_limit"] = limit
                changed = True
                break
        if changed:
            self._save_state_dict(state)

    @pyqtSlot(result=str)
    def getState(self):
        return _json(self._state_from_settings())

    @pyqtSlot(str)
    def saveState(self, payload):
        try:
            self._save_state_dict(json.loads(payload or "{}"))
        except Exception as e:
            self.emit_event("error", message=f"保存设置失败: {e}")

    @pyqtSlot(str)
    def refreshVoices(self, key):
        key = (key or "").strip()
        if not key:
            self.emit_event("error", message="请先配置 ElevenLabs API Key。")
            return
        self.emit_event("status", message="正在刷新声音列表...")
        threading.Thread(target=self._refresh_voices_worker, args=(key,), daemon=True).start()

    def _refresh_voices_worker(self, key):
        try:
            import requests
            res = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=30)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:180]}")
            voices = res.json().get("voices", [])
            self.emit_event("voices", voices=voices)
            self.emit_event("status", message="声音列表已更新")
        except Exception as e:
            self.emit_event("error", message=f"声音列表获取失败: {e}")

    @pyqtSlot(str)
    def checkQuota(self, key):
        key = (key or "").strip()
        if not key:
            self.emit_event("error", message="请先配置 ElevenLabs API Key。")
            return
        self.emit_event("status", message="正在检查账号余额...")
        threading.Thread(target=self._quota_worker, args=(key,), daemon=True).start()

    @pyqtSlot(str)
    def checkAllQuotas(self, payload):
        try:
            accounts = json.loads(payload or "[]")
        except Exception:
            accounts = []
        if not accounts:
            self.emit_event("status", message="暂无账号可检查")
            return
        self.emit_event("status", message="正在检查全部账号余额...")
        threading.Thread(target=self._all_quota_worker, args=(accounts,), daemon=True).start()

    def _all_quota_worker(self, accounts):
        for account in accounts:
            key = (account.get("key") or "").strip()
            if key:
                self._quota_worker(key, silent=True)
        self.emit_event("status", message="全部账号余额已刷新")

    def _quota_worker(self, key, silent=False):
        try:
            import requests
            res = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=30)
            if not res.ok:
                raise Exception(f"HTTP {res.status_code}: {res.text[:180]}")
            data = res.json()
            limit = int(data.get("character_limit", 0) or 0)
            used = int(data.get("character_count", 0) or 0)
            left = max(0, limit - used)
            self._update_account_quota(key, left, limit)
            self.emit_event("quota", key=key, left=left, limit=limit)
            if not silent:
                self.emit_event("status", message="账号余额已刷新")
        except Exception as e:
            self.emit_event("quotaError", key=key, message=str(e))
            if not silent:
                self.emit_event("error", message=f"余额检查失败: {e}")

    @pyqtSlot(result=str)
    def selectOutputDir(self):
        default_dir = self._state_from_settings().get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace")
        os.makedirs(default_dir, exist_ok=True)
        path = QFileDialog.getExistingDirectory(None, "选择 ElevenLabs 音频输出目录", default_dir)
        return path or ""

    @pyqtSlot(str, result=str)
    def exportAccountsCsv(self, payload):
        try:
            accounts = json.loads(payload or "[]")
        except Exception:
            accounts = []
        if not accounts:
            return _json({"ok": False, "message": "当前没有可导出的账号。"})
        default_path = os.path.join(os.getcwd(), "ElevenLabs_账号.csv")
        path, _ = QFileDialog.getSaveFileName(None, "导出 ElevenLabs 账号 CSV", default_path, "CSV Files (*.csv)")
        if not path:
            return _json({"ok": False, "message": ""})
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["备注名", "API_Key", "剩余字数", "总额度"])
                for account in accounts:
                    writer.writerow([
                        account.get("alias", ""),
                        account.get("key", ""),
                        account.get("quota_left", ""),
                        account.get("quota_limit", ""),
                    ])
            return _json({"ok": True, "message": f"CSV 已导出: {path}"})
        except Exception as e:
            return _json({"ok": False, "message": f"导出失败: {e}"})

    @pyqtSlot(result=str)
    def importAccountsCsv(self):
        path, _ = QFileDialog.getOpenFileName(None, "导入 ElevenLabs 账号", os.getcwd(), "Key Files (*.csv *.txt);;All Files (*.*)")
        if not path:
            return _json({"ok": False, "accounts": [], "message": ""})
        rows = []
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                sample = f.read()
            if path.lower().endswith(".csv") or "," in sample:
                for row in csv.reader(sample.splitlines()):
                    if not row:
                        continue
                    header = row[0].strip().lower()
                    if header in ("备注名", "alias", "name"):
                        continue
                    if len(row) == 1:
                        rows.append({"alias": "", "key": row[0].strip()})
                    else:
                        rows.append({"alias": row[0].strip(), "key": row[1].strip()})
            else:
                rows = [{"alias": "", "key": line.strip()} for line in sample.splitlines() if line.strip()]
            rows = [row for row in rows if len(row.get("key", "")) >= 10]
            return _json({"ok": True, "accounts": rows, "message": f"读取到 {len(rows)} 个账号"})
        except Exception as e:
            return _json({"ok": False, "accounts": [], "message": f"导入失败: {e}"})

    @pyqtSlot(str, result=str)
    def exportConfig(self, payload):
        default_path = os.path.join(os.getcwd(), "ElevenLabs_Config.json")
        path, _ = QFileDialog.getSaveFileName(None, "备份 ElevenLabs 配置", default_path, "JSON Files (*.json)")
        if not path:
            return _json({"ok": False, "message": ""})
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(json.loads(payload or "{}"), f, indent=2, ensure_ascii=False)
            return _json({"ok": True, "message": f"配置已备份: {path}"})
        except Exception as e:
            return _json({"ok": False, "message": f"备份失败: {e}"})

    @pyqtSlot(result=str)
    def importConfig(self):
        path, _ = QFileDialog.getOpenFileName(None, "恢复 ElevenLabs 配置", os.getcwd(), "JSON Files (*.json);;All Files (*.*)")
        if not path:
            return _json({"ok": False, "state": {}, "message": ""})
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            return _json({"ok": True, "state": state, "message": "配置已读取"})
        except Exception as e:
            return _json({"ok": False, "state": {}, "message": f"恢复失败: {e}"})

    @pyqtSlot(str)
    def openOutputDir(self, path):
        target = path or self._state_from_settings().get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace")
        os.makedirs(target, exist_ok=True)
        try:
            os.startfile(target)
        except Exception as e:
            self.emit_event("error", message=f"打开目录失败: {e}")

    @pyqtSlot(str)
    def openExternalUrl(self, url):
        url = (url or DEFAULT_API_KEY_LINK).strip()
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        ok = QDesktopServices.openUrl(QUrl(url))
        if ok:
            self.emit_event("status", message="已打开获取 API Key 链接")
        else:
            self.emit_event("error", message=f"打开链接失败: {url}")

    @pyqtSlot(str)
    def generate(self, payload):
        if self.is_running:
            return
        try:
            cfg = json.loads(payload or "{}")
        except Exception as e:
            self.emit_event("error", message=f"生成参数错误: {e}")
            return
        key = (cfg.get("currentKey") or "").strip()
        voice_id = (cfg.get("voiceId") or "").strip()
        segments = [s.strip() for s in (cfg.get("segments") or []) if str(s).strip()]
        if not key:
            self.emit_event("error", message="请先配置 ElevenLabs API Key。")
            return
        if not voice_id:
            self.emit_event("error", message="请先选择声音，或手动填写 Voice ID。")
            return
        if not segments:
            self.emit_event("error", message="请先输入要生成的文案。")
            return
        self._save_state_dict(cfg)
        self.is_running = True
        self.emit_event("generationStart", total=len(segments))
        threading.Thread(target=self._generate_worker, args=(segments, cfg), daemon=True).start()

    def _generate_worker(self, segments, cfg):
        try:
            import requests
            output_dir = cfg.get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace", "ElevenLabs_语音")
            os.makedirs(output_dir, exist_ok=True)
            api_format, file_ext = _format_config(cfg.get("format"))
            model = cfg.get("model") or "eleven_multilingual_v2"
            voice_settings = {
                "stability": float(cfg.get("stability", 0.5) or 0.5),
                "similarity_boost": float(cfg.get("similarity", 0.75) or 0.75),
            }
            if model == "eleven_multilingual_v2":
                voice_settings["style"] = float(cfg.get("style", 0.0) or 0.0)
                voice_settings["use_speaker_boost"] = bool(cfg.get("speakerBoost", True))
            total = max(1, len(segments))
            for idx, text in enumerate(segments, start=1):
                self.emit_event("progress", value=int((idx - 1) * 100 / total), message=f"生成 {idx}/{total} ...")
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voiceId']}?output_format={api_format}"
                res = requests.post(
                    url,
                    headers={"xi-api-key": cfg["currentKey"], "Content-Type": "application/json"},
                    json={"text": text, "model_id": model, "voice_settings": voice_settings},
                    timeout=180,
                )
                if not res.ok:
                    detail = res.text[:300]
                    try:
                        data = res.json()
                        detail = data.get("detail", {}).get("message", detail) if isinstance(data.get("detail"), dict) else str(data.get("detail", detail))
                    except Exception:
                        pass
                    raise Exception(f"第 {idx} 段失败: HTTP {res.status_code} {detail}")
                filename = f"{idx:03d}_{_safe_filename(text)}.{file_ext}"
                out_path = os.path.join(output_dir, filename)
                _write_audio_file(out_path, res.content, api_format)
                self.emit_event("log", message=f"已保存: {out_path}")
                self.emit_event("progress", value=int(idx * 100 / total), message=f"完成 {idx}/{total}")
            self.emit_event("generated", outputDir=output_dir)
            self._quota_worker(cfg["currentKey"], silent=True)
        except Exception as e:
            self.emit_event("error", message=f"生成失败: {e}")
        finally:
            self.is_running = False
            self.emit_event("generationFinished")


ELEVENLABS_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ElevenLabs 批量工坊</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    :root {
      --bg-body: #f8f9fa; --bg-sidebar: #ffffff; --bg-content: #f3f4f6; --bg-card: #ffffff;
      --bg-modal: #ffffff; --bg-input: #f1f3f5; --text-main: #212529; --text-sub: #868e96;
      --primary: #228be6; --primary-hover: #1c7ed6; --danger: #fa5252; --success: #40c057;
      --border: #e9ecef; --shadow-sm: 0 1px 3px rgba(0,0,0,.05); --shadow-md: 0 4px 12px rgba(0,0,0,.08);
      --shadow-lg: 0 8px 24px rgba(0,0,0,.12); --radius: 8px; --overlay: rgba(0,0,0,.42);
    }
    body.dark-mode {
      --bg-body: #101113; --bg-sidebar: #1a1b1e; --bg-content: #141517; --bg-card: #25262b;
      --bg-modal: #1a1b1e; --bg-input: #2c2e33; --text-main: #e9ecef; --text-sub: #a6a8ad;
      --primary: #339af0; --primary-hover: #4dabf7; --border: #34363b; --overlay: rgba(0,0,0,.72);
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body { margin: 0; overflow: hidden; background: var(--bg-body); color: var(--text-main); font: 13px "Segoe UI", "Microsoft YaHei", sans-serif; }
    button, input, textarea, select { font: inherit; }
    .app-container { display: flex; height: 100vh; width: 100%; min-width: 760px; }
    .sidebar { width: 320px; flex: 0 0 320px; background: var(--bg-sidebar); border-right: 1px solid var(--border); padding: 18px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
    .sidebar-header { display: flex; justify-content: space-between; align-items: center; }
    .brand { display: flex; align-items: center; gap: 9px; min-width: 0; }
    .logo { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; background: #ffeff3; color: #e74b67; font-weight: 900; font-size: 20px; border: 1px solid #ffd0db; }
    .logo-text { font-size: 17px; font-weight: 800; white-space: nowrap; }
    .header-actions { display: flex; gap: 8px; }
    .icon-btn-round, .icon-btn-small, .tool-btn-icon, .btn-icon-primary, .btn-icon-secondary, .btn-icon-link { width: 32px; height: 32px; display: grid; place-items: center; border-radius: var(--radius); cursor: pointer; transition: .16s; }
    .icon-btn-round { border-radius: 50%; border: 1px solid var(--border); background: var(--bg-card); color: var(--text-main); }
    .icon-btn-round:hover, .tool-btn-icon:hover, .icon-btn-small:hover { border-color: var(--primary); color: var(--primary); }
    .account-wrapper { position: relative; }
    .account-status-card { background: var(--bg-input); padding: 10px; border-radius: var(--radius); display: flex; align-items: center; gap: 10px; border: 1px solid var(--border); cursor: pointer; transition: .18s; }
    .account-status-card:hover { background: var(--bg-card); border-color: var(--primary); }
    .status-dot { width: 8px; height: 8px; background: var(--text-sub); border-radius: 50%; flex: 0 0 auto; }
    .status-dot.active { background: var(--success); box-shadow: 0 0 8px var(--success); }
    .account-info { min-width: 0; flex: 1; }
    .account-name { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .account-quota { font-size: 11px; color: var(--text-sub); margin-top: 2px; }
    .dropdown-icon { font-size: 10px; color: var(--text-sub); }
    .account-dropdown { position: absolute; top: calc(100% + 6px); left: 0; right: 0; max-height: 300px; overflow-y: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-lg); z-index: 20; padding: 5px; }
    .dropdown-item { padding: 9px; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .dropdown-item:hover { background: var(--bg-input); }
    .dropdown-item.active { background: rgba(34,139,230,.12); color: var(--primary); }
    .dd-name { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .dd-quota { font: 11px Consolas, monospace; color: var(--text-sub); white-space: nowrap; }
    .input-with-action, .folder-group, .row, .toolbar-btns, .backup-actions, .add-key-form { display: flex; gap: 8px; align-items: center; }
    input, select, textarea { width: 100%; border: 1px solid var(--border); background: var(--bg-input); color: var(--text-main); border-radius: var(--radius); outline: none; transition: .16s; }
    input, select { height: 34px; padding: 0 10px; }
    textarea { padding: 11px 12px; line-height: 1.55; resize: vertical; }
    input:focus, select:focus, textarea:focus { border-color: var(--primary); background: var(--bg-card); }
    .btn-icon-link { text-decoration: none; color: var(--primary); background: var(--bg-card); border: 1px solid var(--border); }
    .btn-icon-primary { border: 0; background: var(--primary); color: #fff; }
    .btn-icon-secondary, .tool-btn-icon, .icon-btn-small { border: 1px solid var(--border); background: var(--bg-card); color: var(--text-sub); }
    .control-group label { display: block; margin-bottom: 6px; color: var(--text-sub); font-size: 11px; text-transform: uppercase; font-weight: 800; letter-spacing: .4px; }
    .divider { height: 1px; background: var(--border); margin: 2px 0; }
    .slider-item { margin-bottom: 12px; }
    .slider-item .lbl { display: flex; justify-content: space-between; margin-bottom: 6px; font-weight: 600; }
    .val-tag { background: var(--bg-input); color: var(--primary); border-radius: 5px; padding: 1px 6px; font: 11px Consolas, monospace; }
    input[type=range] { height: 4px; padding: 0; border: 0; accent-color: var(--primary); }
    .toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
    .toggle-row input { width: auto; height: auto; }
    .status-bar { margin-top: auto; min-height: 18px; color: var(--text-sub); font-size: 11px; text-align: center; }
    .content-area { flex: 1; min-width: 0; display: flex; flex-direction: column; background: var(--bg-content); }
    .content-toolbar { padding: 15px 24px; display: flex; justify-content: space-between; align-items: center; background: var(--bg-sidebar); border-bottom: 1px solid var(--border); gap: 16px; }
    .content-toolbar h2 { margin: 0; font-size: 16px; }
    .btn-ghost { border: 0; background: transparent; color: var(--text-sub); cursor: pointer; padding: 7px 12px; border-radius: var(--radius); }
    .btn-ghost:hover { background: var(--bg-input); color: var(--danger); }
    .btn-outlined { border: 1px solid var(--border); background: transparent; color: var(--primary); border-radius: var(--radius); padding: 7px 12px; cursor: pointer; font-weight: 700; }
    .btn-outlined:hover { background: var(--primary); border-color: var(--primary); color: #fff; }
    .cards-wrapper { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 12px; }
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 14px; display: flex; flex-direction: column; gap: 8px; }
    .card textarea { min-height: 76px; background: transparent; border: 0; padding: 0; resize: vertical; font-size: 14px; }
    .card-footer { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--border); padding-top: 7px; color: var(--text-sub); font-size: 11px; }
    .del-btn { border: 0; background: transparent; color: var(--text-sub); cursor: pointer; }
    .del-btn:hover { color: var(--danger); }
    .content-footer { background: var(--bg-sidebar); border-top: 1px solid var(--border); padding: 14px 24px; display: grid; grid-template-columns: minmax(0,1fr) minmax(180px, 260px); gap: 18px; align-items: center; }
    .stats-info { color: var(--text-sub); font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .btn-primary { border: 0; background: var(--primary); color: #fff; border-radius: var(--radius); height: 42px; cursor: pointer; font-weight: 800; box-shadow: var(--shadow-md); }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-primary:disabled { background: var(--border); color: var(--text-sub); cursor: not-allowed; box-shadow: none; }
    .progress { height: 4px; background: var(--border); }
    .progress span { display: block; height: 100%; width: 0; background: var(--primary); transition: width .2s; }
    .hidden { display: none !important; }
    .modal-overlay { position: fixed; inset: 0; background: var(--overlay); backdrop-filter: blur(3px); z-index: 100; display: grid; place-items: center; padding: 28px; }
    .modal-panel { width: min(540px, 100%); max-height: 86vh; background: var(--bg-modal); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-lg); display: flex; flex-direction: column; overflow: hidden; }
    .modal-header { display: flex; align-items: center; justify-content: space-between; padding: 15px 18px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border); }
    .modal-header h3 { margin: 0; font-size: 16px; }
    .close-icon { border: 0; background: transparent; color: var(--text-sub); font-size: 22px; cursor: pointer; }
    .modal-body { padding: 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 18px; }
    .setting-section { display: flex; flex-direction: column; gap: 10px; }
    .section-header-row { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
    .section-title { font-size: 12px; font-weight: 900; color: var(--text-sub); text-transform: uppercase; }
    .key-list-scrollable { max-height: 245px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding: 6px; border: 1px solid var(--border); background: var(--bg-input); border-radius: var(--radius); }
    .key-item { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-card); cursor: pointer; }
    .key-item.active { border-color: var(--primary); box-shadow: inset 0 0 0 1px var(--primary); }
    .key-main-info { min-width: 0; flex: 1; }
    .key-alias { font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .key-code, .quota-tag { color: var(--text-sub); font: 11px Consolas, monospace; }
    .quota-tag.good { color: #16834f; }
    .quota-tag.low { color: var(--danger); }
    .key-actions { display: flex; align-items: center; gap: 4px; }
    .key-edit, .key-del { width: 28px; height: 28px; border: 0; border-radius: 6px; background: transparent; color: var(--text-sub); cursor: pointer; font-size: 14px; }
    .key-edit:hover { color: var(--primary); background: rgba(34,139,230,.12); }
    .key-del:hover { color: var(--danger); background: rgba(250,82,82,.12); }
    .log-line { color: var(--text-sub); font: 11px Consolas, monospace; max-height: 38px; overflow: hidden; text-overflow: ellipsis; }
    @media (max-width: 980px) {
      .app-container { min-width: 0; }
      .sidebar { width: 300px; flex-basis: 300px; }
      .content-footer { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body class="dark-mode">
  <div class="app-container">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand"><div class="logo">E</div><div class="logo-text">ElevenLabs</div></div>
        <div class="header-actions">
          <button id="themeToggle" class="icon-btn-round" title="切换深色模式">☾</button>
          <button id="openSettingsBtn" class="icon-btn-round" title="打开设置">⚙</button>
        </div>
      </div>

      <div class="account-wrapper">
        <div class="account-status-card" id="accountCard" title="点击切换账号">
          <div class="status-dot" id="statusDot"></div>
          <div class="account-info">
            <div class="account-name" id="currentAliasDisplay">未配置 Key</div>
            <div class="account-quota" id="userQuota">请在设置中添加</div>
          </div>
          <div class="dropdown-icon">▼</div>
        </div>
        <div class="account-dropdown hidden" id="quickSwitchDropdown"></div>
      </div>

      <div class="quick-key-section">
        <div class="input-with-action">
          <button id="apiKeyLinkBtn" class="btn-icon-link" title="获取 API Key">🔑</button>
          <input type="password" id="quickKeyInput" placeholder="粘贴 Key 回车即用">
          <button id="quickKeySubmitBtn" class="btn-icon-primary" title="立即使用">➜</button>
        </div>
      </div>

      <div class="quick-tools">
        <div class="folder-group">
          <input type="text" id="outputDirInput" placeholder="输出目录">
          <button id="chooseOutputDirBtn" class="tool-btn-icon" title="选择目录">…</button>
          <button id="quickOpenFolderBtn" class="tool-btn-icon" title="打开目录">📂</button>
        </div>
      </div>

      <div class="divider"></div>

      <div class="control-group">
        <label>Voice</label>
        <div class="row">
          <select id="voiceSelect"><option value="">请先刷新声音</option></select>
          <button id="refreshVoices" class="icon-btn-small" title="刷新列表">↻</button>
        </div>
        <div class="input-with-action" style="margin-top:6px">
          <input type="text" id="customVoiceId" placeholder="粘贴 Voice ID">
          <button id="checkVoiceIdBtn" class="btn-icon-secondary" title="使用 Voice ID">✓</button>
        </div>
      </div>

      <div class="control-group">
        <label>Model</label>
        <select id="modelSelect">
          <option value="eleven_multilingual_v2">Multilingual v2</option>
          <option value="eleven_turbo_v2_5">Turbo v2.5</option>
          <option value="eleven_flash_v2_5">Flash v2.5</option>
          <option value="eleven_v3">Eleven v3</option>
        </select>
      </div>

      <div class="control-group">
        <label>Output Format</label>
        <select id="formatSelect">
          <option value="mp3_44100_128">MP3 标准 128k</option>
          <option value="mp3_44100_192">MP3 高质 192k</option>
          <option value="pcm_44100">WAV 无损 PCM</option>
          <option value="mp3_as_mp4">MP4 伪装格式 / Canva</option>
        </select>
      </div>

      <div class="divider"></div>

      <div class="sliders-area">
        <div class="slider-item">
          <div class="lbl"><span>Stability</span><span class="val-tag" id="valStab">0.50</span></div>
          <input type="range" id="stability" min="0" max="1" step="0.01" value="0.5">
        </div>
        <div class="slider-item">
          <div class="lbl"><span>Similarity</span><span class="val-tag" id="valSim">0.75</span></div>
          <input type="range" id="similarity" min="0" max="1" step="0.01" value="0.75">
        </div>
        <div class="slider-item">
          <div class="lbl"><span>Style</span><span class="val-tag" id="valStyle">0.00</span></div>
          <input type="range" id="style" min="0" max="1" step="0.01" value="0">
        </div>
        <div class="toggle-row"><label for="speakerBoost">Speaker Boost</label><input type="checkbox" id="speakerBoost" checked></div>
        <div class="toggle-row"><label for="autoDelete">生成后清空文案</label><input type="checkbox" id="autoDelete"></div>
      </div>

      <div class="status-bar" id="status">就绪</div>
    </aside>

    <main class="content-area">
      <div class="content-toolbar">
        <h2>文案列表</h2>
        <div class="toolbar-btns">
          <button id="clearAllBtn" class="btn-ghost">清空</button>
          <button id="addCardBtn" class="btn-outlined">+ 新段落</button>
        </div>
      </div>
      <div id="listContainer" class="cards-wrapper"></div>
      <div class="progress"><span id="progressBar"></span></div>
      <div class="content-footer">
        <div>
          <div class="stats-info"><span id="totalCharsDisplay">总字数: 0</span> <span> | </span> <span id="remainingDisplay">剩余额度: --</span></div>
          <div class="log-line" id="logLine"></div>
        </div>
        <button id="generateBtn" class="btn-primary">批量生成</button>
      </div>
    </main>
  </div>

  <div id="settingsModal" class="modal-overlay hidden">
    <div class="modal-panel">
      <div class="modal-header"><h3>全局设置</h3><button id="closeSettingsBtn" class="close-icon">×</button></div>
      <div class="modal-body">
        <section class="setting-section">
          <div class="section-header-row">
            <div class="section-title">API 密钥管理</div>
            <button id="importKeysBtn" class="btn-outlined">导入 CSV</button>
          </div>
          <div class="input-with-action">
            <input type="text" id="apiKeyLinkInput" placeholder="获取 API Key 的链接">
            <button id="openApiKeyLinkBtn" class="btn-outlined">打开链接</button>
          </div>
          <div class="key-list-scrollable" id="keyListContainer"></div>
          <div class="add-key-form">
            <input type="text" id="newKeyAlias" placeholder="备注" style="width:34%">
            <input type="password" id="newKeyVal" placeholder="API Key">
            <button id="saveNewKeyBtn" class="btn-outlined">添加</button>
          </div>
        </section>

        <section class="setting-section">
          <div class="section-header-row"><div class="section-title">备份与导出</div></div>
          <div class="backup-actions">
            <button id="refreshAllQuotaBtn" class="btn-outlined">查全部余额</button>
            <button id="exportCsvBtn" class="btn-outlined">导出 CSV</button>
            <button id="exportDataBtn" class="btn-outlined">备份</button>
            <button id="importDataBtn" class="btn-outlined">恢复</button>
          </div>
        </section>
      </div>
    </div>
  </div>

  <script>
    const $ = id => document.getElementById(id);
    let bridge = null;
    let saveTimer = null;
    const state = {
      accounts: [], currentKey: "", currentQuota: null, currentLimit: null, voiceId: "",
      model: "eleven_multilingual_v2", format: "mp3_44100_128", outputDir: "",
      stability: 0.5, similarity: 0.75, style: 0, speakerBoost: true, clearAfter: false,
      apiKeyLink: "https://elevenlabs.io/app/settings/api-keys", cards: [""], voices: []
    };

    function mask(key) { return key ? "•••• " + key.slice(-4) : "----"; }
    function currentAccount() { return state.accounts.find(a => a.key === state.currentKey) || null; }
    function quotaText(account) {
      if (!account || typeof account.quota_left !== "number") return "未查余额";
      return "剩 " + account.quota_left.toLocaleString() + " 字";
    }
    function setStatus(msg, error=false) {
      $("status").textContent = msg || "就绪";
      $("status").style.color = error ? "var(--danger)" : "var(--text-sub)";
    }
    function setLog(msg) { $("logLine").textContent = msg || ""; }
    function setProgress(value) { $("progressBar").style.width = Math.max(0, Math.min(100, value || 0)) + "%"; }

    function collectControls() {
      state.outputDir = $("outputDirInput").value.trim();
      state.voiceId = $("customVoiceId").value.trim() || $("voiceSelect").value || state.voiceId || "";
      state.model = $("modelSelect").value;
      state.format = $("formatSelect").value;
      state.stability = Number($("stability").value);
      state.similarity = Number($("similarity").value);
      state.style = Number($("style").value);
      state.speakerBoost = $("speakerBoost").checked;
      state.clearAfter = $("autoDelete").checked;
      state.apiKeyLink = $("apiKeyLinkInput").value.trim() || state.apiKeyLink || "https://elevenlabs.io/app/settings/api-keys";
    }
    function persist() {
      if (!bridge) return;
      collectControls();
      bridge.saveState(JSON.stringify(state));
    }
    function persistDebounced() {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(persist, 300);
    }

    function renderAccounts() {
      const account = currentAccount();
      $("statusDot").classList.toggle("active", !!state.currentKey);
      $("currentAliasDisplay").textContent = account ? (account.alias || "未命名账号") : "未配置 Key";
      $("userQuota").textContent = account ? quotaText(account) : "请在设置中添加";
      if (account && typeof account.quota_left === "number") {
        state.currentQuota = account.quota_left;
        state.currentLimit = account.quota_limit || 0;
      }
      const dd = $("quickSwitchDropdown");
      dd.innerHTML = state.accounts.length ? "" : "<div class='dropdown-item'>暂无账号</div>";
      state.accounts.forEach((item) => {
        const div = document.createElement("div");
        div.className = "dropdown-item" + (item.key === state.currentKey ? " active" : "");
        div.innerHTML = `<span class="dd-name">${escapeHtml(item.alias || "未命名账号")}</span><span class="dd-quota">${quotaText(item)}</span>`;
        div.onclick = () => switchKey(item.key);
        dd.appendChild(div);
      });
      renderKeyList();
      updateStats();
    }

    function renameAccount(index) {
      const item = state.accounts[index];
      if (!item) return;
      const next = prompt("新的账号备注", item.alias || `账号 ${index + 1}`);
      if (next === null) return;
      const alias = next.trim();
      if (!alias) return setStatus("账号名字不能为空", true);
      item.alias = alias;
      renderAccounts();
      persist();
      setStatus("账号名称已更新");
    }

    function renderKeyList() {
      const box = $("keyListContainer");
      if (!box) return;
      box.innerHTML = "";
      if (!state.accounts.length) {
        box.innerHTML = "<div style='padding:12px;color:var(--text-sub)'>暂无 Key</div>";
        return;
      }
      state.accounts.forEach((item, idx) => {
        const div = document.createElement("div");
        div.className = "key-item" + (item.key === state.currentKey ? " active" : "");
        div.innerHTML = `
          <div class="key-main-info">
            <div class="key-alias">${escapeHtml(item.alias || ("账号 " + (idx + 1)))}</div>
            <div class="key-code">${mask(item.key)}</div>
          </div>
          <span class="quota-tag ${typeof item.quota_left === "number" && item.quota_left < 1000 ? "low" : "good"}">${quotaText(item)}</span>
          <div class="key-actions">
            <button class="key-edit" title="改名字">✎</button>
            <button class="key-del" title="删除">×</button>
          </div>`;
        div.onclick = (event) => {
          if (event.target.closest(".key-actions")) return;
          switchKey(item.key);
        };
        div.querySelector(".key-edit").onclick = (event) => {
          event.stopPropagation();
          renameAccount(idx);
        };
        div.querySelector(".key-del").onclick = (event) => {
          event.stopPropagation();
          state.accounts.splice(idx, 1);
          if (state.currentKey === item.key) state.currentKey = state.accounts[0]?.key || "";
          renderAccounts();
          persist();
        };
        box.appendChild(div);
      });
    }

    function renderVoiceSelect() {
      const select = $("voiceSelect");
      select.innerHTML = "";
      if (!state.voices.length) {
        select.innerHTML = "<option value=''>请先刷新声音</option>";
        if (state.voiceId) $("customVoiceId").value = state.voiceId;
        return;
      }
      [...state.voices].sort((a,b) => (a.name || "").localeCompare(b.name || "")).forEach(voice => {
        const opt = document.createElement("option");
        opt.value = voice.voice_id || "";
        opt.textContent = voice.category ? `${voice.name} · ${voice.category}` : (voice.name || "Unnamed");
        select.appendChild(opt);
      });
      if (state.voiceId && [...select.options].some(o => o.value === state.voiceId)) {
        select.value = state.voiceId;
        $("customVoiceId").value = "";
      } else if (state.voiceId) {
        $("customVoiceId").value = state.voiceId;
      }
    }

    function renderCards() {
      const box = $("listContainer");
      box.innerHTML = "";
      const cards = state.cards.length ? state.cards : [""];
      state.cards = cards;
      cards.forEach((text, idx) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          <textarea data-index="${idx}" placeholder="输入要生成的文案">${escapeHtml(text)}</textarea>
          <div class="card-footer"><span>段落 ${idx + 1} · <b class="char-count">${text.length}</b> 字</span><button class="del-btn">删除</button></div>`;
        const textarea = card.querySelector("textarea");
        textarea.oninput = () => {
          state.cards[idx] = textarea.value;
          card.querySelector(".char-count").textContent = textarea.value.length;
          updateStats();
          persistDebounced();
        };
        card.querySelector(".del-btn").onclick = () => {
          state.cards.splice(idx, 1);
          if (!state.cards.length) state.cards = [""];
          renderCards();
          updateStats();
          persist();
        };
        box.appendChild(card);
      });
      updateStats();
    }

    function renderControls() {
      $("outputDirInput").value = state.outputDir || "";
      $("modelSelect").value = state.model || "eleven_multilingual_v2";
      $("formatSelect").value = state.format || "mp3_44100_128";
      $("stability").value = state.stability ?? 0.5;
      $("similarity").value = state.similarity ?? 0.75;
      $("style").value = state.style ?? 0;
      $("speakerBoost").checked = state.speakerBoost !== false;
      $("autoDelete").checked = !!state.clearAfter;
      $("apiKeyLinkInput").value = state.apiKeyLink || "https://elevenlabs.io/app/settings/api-keys";
      syncSliderLabels();
    }

    function renderAll() {
      renderControls();
      renderAccounts();
      renderVoiceSelect();
      renderCards();
    }

    function updateStats() {
      const total = state.cards.reduce((sum, text) => sum + (text || "").length, 0);
      $("totalCharsDisplay").textContent = `总字数: ${total.toLocaleString()} · ${state.cards.filter(t => (t || "").trim()).length} 段`;
      if (state.currentQuota === null || state.currentQuota === undefined) {
        $("remainingDisplay").textContent = "剩余额度: --";
      } else {
        $("remainingDisplay").textContent = `生成后剩余: ${(state.currentQuota - total).toLocaleString()} 字`;
      }
    }

    function syncSliderLabels() {
      $("valStab").textContent = Number($("stability").value).toFixed(2);
      $("valSim").textContent = Number($("similarity").value).toFixed(2);
      $("valStyle").textContent = Number($("style").value).toFixed(2);
    }

    function addOrSwitchAccount(alias, key) {
      key = (key || "").trim();
      if (!key) return setStatus("请输入 API Key", true);
      let item = state.accounts.find(a => a.key === key);
      if (item) {
        if (alias) item.alias = alias;
      } else {
        item = { alias: alias || `账号 ${state.accounts.length + 1}`, key };
        state.accounts.push(item);
      }
      switchKey(key, false);
      renderAccounts();
      persist();
      if (bridge) {
        bridge.checkQuota(key);
        bridge.refreshVoices(key);
      }
    }

    function switchKey(key, shouldPersist=true) {
      state.currentKey = key || "";
      renderAccounts();
      if (shouldPersist) persist();
      if (bridge && key) {
        setStatus("正在切换账号...");
        bridge.checkQuota(key);
        bridge.refreshVoices(key);
      }
      $("quickSwitchDropdown").classList.add("hidden");
    }

    function startGenerate() {
      collectControls();
      const manualVoice = $("customVoiceId").value.trim();
      state.voiceId = manualVoice || $("voiceSelect").value || state.voiceId || "";
      const segments = state.cards.map(t => (t || "").trim()).filter(Boolean);
      bridge.generate(JSON.stringify({...state, segments}));
    }

    function openApiKeyLink() {
      collectControls();
      persist();
      if (bridge) bridge.openExternalUrl(state.apiKeyLink);
    }

    function normalizeImportedState(src) {
      if (!src || typeof src !== "object") return {};
      if (src.elevenlabs_tool) return normalizeImportedState(src.elevenlabs_tool);
      if (src.saved_key_list || src.xi_key || src.saved_cards) {
        const accounts = Array.isArray(src.saved_key_list) ? src.saved_key_list : [];
        return {
          accounts,
          currentKey: src.xi_key || accounts[0]?.key || "",
          voiceId: src.xi_voice || "",
          model: src.xi_model || "eleven_multilingual_v2",
          format: src.output_format || "mp3_44100_128",
          outputDir: src.output_dir || "",
          stability: Number(src.xi_stab ?? 0.5),
          similarity: Number(src.xi_sim ?? 0.75),
          style: Number(src.xi_style ?? 0),
          speakerBoost: src.xi_boost !== false,
          clearAfter: !!src.auto_del,
          apiKeyLink: src.api_key_link || src.apiKeyLink || "https://elevenlabs.io/app/settings/api-keys",
          cards: Array.isArray(src.saved_cards) && src.saved_cards.length ? src.saved_cards : [""]
        };
      }
      if (src.current_account_key || src.api_key || src.api_key_link || src.voice_id) {
        const accounts = Array.isArray(src.accounts) ? src.accounts : [];
        return {
          accounts,
          currentKey: src.current_account_key || src.api_key || accounts[0]?.key || "",
          voiceId: src.voice_id || "",
          model: src.model || "eleven_multilingual_v2",
          format: src.format || "mp3_44100_128",
          outputDir: src.output_dir || "",
          stability: Number(src.stability ?? 0.5),
          similarity: Number(src.similarity ?? 0.75),
          style: Number(src.style ?? 0),
          speakerBoost: src.speaker_boost !== false,
          clearAfter: !!src.clear_after,
          apiKeyLink: src.api_key_link || "https://elevenlabs.io/app/settings/api-keys",
          cards: Array.isArray(src.cards) && src.cards.length ? src.cards : [""]
        };
      }
      return {...src, apiKeyLink: src.apiKeyLink || src.api_key_link || "https://elevenlabs.io/app/settings/api-keys"};
    }

    function onBridgeEvent(raw) {
      let data = {};
      try { data = JSON.parse(raw); } catch { return; }
      if (data.type === "status") setStatus(data.message);
      if (data.type === "error") { setStatus(data.message, true); setLog(data.message); $("generateBtn").disabled = false; }
      if (data.type === "voices") { state.voices = data.voices || []; renderVoiceSelect(); }
      if (data.type === "quota") {
        const account = state.accounts.find(a => a.key === data.key);
        if (account) { account.quota_left = data.left; account.quota_limit = data.limit; }
        if (data.key === state.currentKey) { state.currentQuota = data.left; state.currentLimit = data.limit; }
        renderAccounts();
        persist();
      }
      if (data.type === "quotaError") setLog(`余额刷新失败: ${data.message}`);
      if (data.type === "generationStart") { $("generateBtn").disabled = true; setProgress(0); setLog(""); setStatus(`开始生成 ${data.total} 段...`); }
      if (data.type === "progress") { setProgress(data.value); setStatus(data.message); }
      if (data.type === "log") setLog(data.message);
      if (data.type === "generated") {
        setProgress(100);
        state.outputDir = data.outputDir || state.outputDir;
        $("outputDirInput").value = state.outputDir;
        setStatus("全部生成完成");
        if (state.clearAfter) { state.cards = [""]; renderCards(); }
        persist();
      }
      if (data.type === "generationFinished") $("generateBtn").disabled = false;
    }

    function escapeHtml(text) {
      return String(text ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[ch]));
    }

    function wireUi() {
      $("themeToggle").onclick = () => {
        document.body.classList.toggle("dark-mode");
        $("themeToggle").textContent = document.body.classList.contains("dark-mode") ? "☾" : "☀";
      };
      $("accountCard").onclick = (event) => {
        event.stopPropagation();
        $("quickSwitchDropdown").classList.toggle("hidden");
      };
      document.addEventListener("click", () => $("quickSwitchDropdown").classList.add("hidden"));
      $("apiKeyLinkBtn").onclick = openApiKeyLink;
      $("openApiKeyLinkBtn").onclick = openApiKeyLink;
      $("quickKeySubmitBtn").onclick = () => {
        addOrSwitchAccount("", $("quickKeyInput").value);
        $("quickKeyInput").value = "";
      };
      $("quickKeyInput").onkeydown = e => { if (e.key === "Enter") $("quickKeySubmitBtn").click(); };
      $("openSettingsBtn").onclick = () => { renderKeyList(); $("settingsModal").classList.remove("hidden"); };
      $("closeSettingsBtn").onclick = () => $("settingsModal").classList.add("hidden");
      $("addCardBtn").onclick = () => { state.cards.push(""); renderCards(); persist(); };
      $("clearAllBtn").onclick = () => { state.cards = [""]; renderCards(); persist(); };
      $("generateBtn").onclick = startGenerate;
      $("refreshVoices").onclick = () => bridge && bridge.refreshVoices(state.currentKey);
      $("checkVoiceIdBtn").onclick = () => { state.voiceId = $("customVoiceId").value.trim(); persist(); setStatus("Voice ID 已设为优先使用"); };
      $("chooseOutputDirBtn").onclick = () => bridge && bridge.selectOutputDir(path => { if (path) { state.outputDir = path; $("outputDirInput").value = path; persist(); }});
      $("quickOpenFolderBtn").onclick = () => { collectControls(); bridge && bridge.openOutputDir(state.outputDir); };
      $("saveNewKeyBtn").onclick = () => {
        addOrSwitchAccount($("newKeyAlias").value.trim(), $("newKeyVal").value.trim());
        $("newKeyAlias").value = ""; $("newKeyVal").value = "";
      };
      $("importKeysBtn").onclick = () => bridge && bridge.importAccountsCsv(raw => {
        const res = JSON.parse(raw || "{}");
        let added = 0;
        (res.accounts || []).forEach((item) => {
          if (!state.accounts.some(a => a.key === item.key)) {
            state.accounts.push({ alias: item.alias || `账号 ${state.accounts.length + 1}`, key: item.key });
            added++;
          }
        });
        if (!state.currentKey && state.accounts.length) state.currentKey = state.accounts[0].key;
        renderAccounts(); persist(); setStatus(added ? `已导入 ${added} 个账号` : (res.message || "没有新账号"));
      });
      $("exportCsvBtn").onclick = () => { persist(); bridge && bridge.exportAccountsCsv(JSON.stringify(state.accounts), raw => setStatus((JSON.parse(raw || "{}")).message)); };
      $("refreshAllQuotaBtn").onclick = () => bridge && bridge.checkAllQuotas(JSON.stringify(state.accounts));
      $("exportDataBtn").onclick = () => { persist(); bridge && bridge.exportConfig(JSON.stringify(state), raw => setStatus((JSON.parse(raw || "{}")).message)); };
      $("importDataBtn").onclick = () => bridge && bridge.importConfig(raw => {
        const res = JSON.parse(raw || "{}");
        if (res.ok && res.state) { Object.assign(state, normalizeImportedState(res.state)); renderAll(); persist(); }
        setStatus(res.message || "");
      });
      ["modelSelect","formatSelect","speakerBoost","autoDelete","outputDirInput","voiceSelect","customVoiceId","apiKeyLinkInput"].forEach(id => $(id).addEventListener("change", persistDebounced));
      ["outputDirInput","customVoiceId","apiKeyLinkInput"].forEach(id => $(id).addEventListener("input", persistDebounced));
      ["stability","similarity","style"].forEach(id => $(id).addEventListener("input", () => { syncSliderLabels(); persistDebounced(); }));
    }

    wireUi();
    if (window.qt && QWebChannel) {
      new QWebChannel(qt.webChannelTransport, channel => {
        bridge = channel.objects.elevenlabsBridge;
        bridge.event.connect(onBridgeEvent);
        bridge.getState(raw => {
          Object.assign(state, JSON.parse(raw || "{}"));
          renderAll();
          if (state.currentKey) {
            bridge.checkQuota(state.currentKey);
            bridge.refreshVoices(state.currentKey);
            bridge.checkAllQuotas(JSON.stringify(state.accounts));
          }
        });
      });
    } else {
      setStatus("浏览器桥接未启动", true);
      renderAll();
    }
  </script>
</body>
</html>
"""


class ElevenLabsWebTool(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_colors = None
        self._theme_key = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.view.loadFinished.connect(self._on_load_finished)
        self.bridge = ElevenLabsBridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("elevenlabsBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        load_web_tool_page(self.view, "elevenlabs", ELEVENLABS_HTML, os.getcwd())
        layout.addWidget(self.view)

    def _on_load_finished(self, ok):
        if ok and self._theme_colors:
            self.view.page().runJavaScript(web_theme_script(self._theme_colors, self._theme_key))

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        self.view.page().runJavaScript(web_theme_script(colors, self._theme_key))


def create_elevenlabs_tool(parent=None, fallback_cls=None):
    if WEBENGINE_AVAILABLE:
        return ElevenLabsWebTool(parent)
    if fallback_cls is not None:
        return fallback_cls(parent)
    return QWidget(parent)
