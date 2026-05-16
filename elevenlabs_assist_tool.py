import json
import os
import random
import re
import threading
import time

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
LOGIN_URL = "https://elevenlabs.io/app/sign-in"
OFFICIAL_TTS_URL = "https://elevenlabs.io/app/speech-synthesis/text-to-speech"


class ElevenLabsUserError(Exception):
    def __init__(self, message, popup=False):
        super().__init__(message)
        self.popup = popup


def _json(data):
    return json.dumps(data, ensure_ascii=False)


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


def _safe_filename(text, fallback="voice"):
    clean = re.sub(r"[\r\n\t]+", " ", text or "").strip()
    clean = re.sub(r'[\\/:*?"<>|]', "_", clean)
    clean = re.sub(r"\s+", " ", clean)[:36].strip()
    return clean or fallback


def _elevenlabs_error_message(res, context="请求"):
    raw = ""
    status = ""
    message = ""
    try:
        data = res.json()
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            status = str(detail.get("status", "") or "")
            message = str(detail.get("message", "") or "")
        else:
            message = str(detail or "")
        raw = json.dumps(data, ensure_ascii=False)
    except Exception:
        raw = (getattr(res, "text", "") or "")[:300]
        message = raw

    if status == "detected_unusual_activity" or "Unusual activity detected" in message:
        return (
            f"{context}被 ElevenLabs 拒绝：账号被判定为异常活动，免费生成被禁用。"
            "这不是按钮没点中，而是官方接口返回 401。可以先关闭 VPN/代理后重新网页登录授权；"
            "如果官网网页仍能生成，说明官网会话可用但桌面自动接口被限制，建议改用 API Key/付费账号或在官网生成。"
        ), True

    if res.status_code in (401, 403):
        return (
            f"{context}授权失败：HTTP {res.status_code}。请重新点“网页登录”捕获授权，"
            "或换一个可用账号/API Key。原始信息：" + (message or raw)[:180]
        ), True

    return f"{context}失败：HTTP {res.status_code} {(message or raw)[:220]}", False


class TokenCaptureBridge(QObject):
    token_captured = pyqtSignal(str)

    @pyqtSlot(str)
    def captureToken(self, token):
        token = (token or "").replace("Bearer ", "").replace("bearer ", "").strip()
        if len(token) > 20:
            self.token_captured.emit(token)


class TokenCaptureDialog(QDialog):
    token_captured = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ElevenLabs 网页授权捕获")
        self.resize(1180, 820)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        tip = QLabel("用账号密码登录 ElevenLabs 后，进入会加载声音/额度的页面；捕获到网页授权后会自动保存到小工具。")
        tip.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        btn_external = QPushButton("外部浏览器打开")
        btn_external.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(LOGIN_URL)))
        top.addWidget(tip, stretch=1)
        top.addWidget(btn_external)
        layout.addLayout(top)

        self.view = QWebEngineView(self)
        self.bridge = TokenCaptureBridge(self)
        self.bridge.token_captured.connect(self.token_captured.emit)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("tokenSniffer", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.loadFinished.connect(self.inject_sniffer)
        self.view.setUrl(QUrl(LOGIN_URL))
        layout.addWidget(self.view, stretch=1)

    def inject_sniffer(self):
        script = r"""
        (function() {
          if (window.__elDesktopSnifferInstalled) return;
          window.__elDesktopSnifferInstalled = true;
          let bridge = null;
          let pendingToken = "";
          function clean(token) {
            return String(token || "").replace(/^Bearer\s+/i, "").trim();
          }
          function send(token) {
            token = clean(token);
            if (token.length <= 20) return;
            if (bridge) bridge.captureToken(token);
            else pendingToken = token;
          }
          function setupChannel() {
            if (window.qt && window.QWebChannel) {
              new QWebChannel(qt.webChannelTransport, function(channel) {
                bridge = channel.objects.tokenSniffer;
                if (pendingToken) send(pendingToken);
              });
            }
          }
          if (!window.QWebChannel) {
            const s = document.createElement("script");
            s.src = "qrc:///qtwebchannel/qwebchannel.js";
            s.onload = setupChannel;
            document.documentElement.appendChild(s);
          } else {
            setupChannel();
          }

          const originalFetch = window.fetch;
          window.fetch = async function(url, options) {
            const urlStr = typeof url === "string" ? url : (url && url.url) || "";
            try {
              if (urlStr.includes("elevenlabs.io") && options && options.headers) {
                const headers = options.headers;
                let token = "";
                if (headers instanceof Headers) {
                  token = headers.get("authorization") || headers.get("xi-api-key") || "";
                } else {
                  const key = Object.keys(headers).find(k => /^(authorization|xi-api-key)$/i.test(k));
                  token = key ? headers[key] : "";
                }
                send(token);
              }
            } catch (e) {}
            const response = await originalFetch.apply(this, arguments);
            try {
              if (urlStr.includes("identitytoolkit.googleapis.com") || urlStr.includes("securetoken.googleapis.com")) {
                const data = await response.clone().json();
                send(data.idToken || data.access_token || "");
              }
            } catch (e) {}
            return response;
          };
        })();
        """
        self.view.page().runJavaScript(script)


class ElevenLabsAssistBridge(QObject):
    event = pyqtSignal(str)

    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.is_running = False
        self.stop_requested = False
        self.capture_dialog = None

    def emit_event(self, event_type, **payload):
        payload["type"] = event_type
        self.event.emit(_json(payload))

    def _tool_settings(self):
        return _load_app_settings().get("elevenlabs_assist_tool", {})

    def _state_from_settings(self):
        data = self._tool_settings()
        accounts = list(data.get("accounts", []) or [])
        current_token = data.get("current_token", "")
        if not current_token and accounts:
            current_token = accounts[0].get("token", "")
        return {
            "accounts": accounts,
            "currentToken": current_token,
            "voiceId": data.get("voice_id", ""),
            "model": data.get("model", "eleven_flash_v2_5"),
            "outputDir": data.get("output_dir", ""),
            "subFolder": data.get("sub_folder", "批量导出"),
            "stability": float(data.get("stability", 0.5)),
            "similarity": float(data.get("similarity", 0.75)),
            "style": float(data.get("style", 0.0)),
            "speakerBoost": bool(data.get("speaker_boost", True)),
            "compatMode": bool(data.get("compat_mode", True)),
            "autoDelete": bool(data.get("auto_delete", True)),
            "cards": list(data.get("cards", []) or [""]),
        }

    def _save_state_dict(self, state):
        accounts = list(state.get("accounts", []) or [])
        current_token = state.get("currentToken", "")
        if current_token and not any(a.get("token") == current_token for a in accounts):
            accounts.append({"alias": f"网页账号 {len(accounts) + 1}", "token": current_token})
        all_settings = _load_app_settings()
        all_settings["elevenlabs_assist_tool"] = {
            "accounts": accounts,
            "current_token": current_token,
            "voice_id": state.get("voiceId", ""),
            "model": state.get("model", "eleven_flash_v2_5"),
            "output_dir": state.get("outputDir", ""),
            "sub_folder": state.get("subFolder", "批量导出"),
            "stability": float(state.get("stability", 0.5) or 0.5),
            "similarity": float(state.get("similarity", 0.75) or 0.75),
            "style": float(state.get("style", 0.0) or 0.0),
            "speaker_boost": bool(state.get("speakerBoost", True)),
            "compat_mode": bool(state.get("compatMode", True)),
            "auto_delete": bool(state.get("autoDelete", True)),
            "cards": list(state.get("cards", []) or [""]),
        }
        _save_app_settings(all_settings)

    @pyqtSlot(result=str)
    def getState(self):
        return _json(self._state_from_settings())

    @pyqtSlot(str)
    def saveState(self, payload):
        try:
            self._save_state_dict(json.loads(payload or "{}"))
        except Exception as e:
            self.emit_event("error", message=f"保存设置失败: {e}")

    @pyqtSlot()
    def openTokenCapture(self):
        if not WEBENGINE_AVAILABLE:
            self.emit_event("error", message="当前环境缺少浏览器内核，无法打开网页登录捕获。")
            return
        self.capture_dialog = TokenCaptureDialog(self.parent_widget)
        self.capture_dialog.token_captured.connect(self.on_token_captured)
        self.capture_dialog.show()

    def on_token_captured(self, token):
        self.emit_event("capturedToken", token=token)
        self.emit_event("status", message="已捕获网页授权，已自动保存为账号。")

    @pyqtSlot(str)
    def refreshVoices(self, token):
        token = (token or "").strip()
        if not token:
            self.emit_event("error", message="请先点击“网页登录并自动授权”，用账号密码登录后自动保存账号。")
            return
        self.emit_event("status", message="正在同步声音列表...")
        threading.Thread(target=self._voices_worker, args=(token,), daemon=True).start()

    def _voices_worker(self, token):
        try:
            import requests
            res = requests.get(
                "https://api.us.elevenlabs.io/v2/voices?page_size=100",
                headers={"authorization": "Bearer " + token},
                timeout=30,
            )
            if not res.ok:
                message, _ = _elevenlabs_error_message(res, "声音列表获取")
                raise Exception(message)
            data = res.json()
            voices = data.get("voices", [])
            self.emit_event("voices", voices=voices)
            self.emit_event("status", message="账号与声音库已同步")
        except Exception as e:
            self.emit_event("error", message=f"声音列表获取失败: {e}")

    @pyqtSlot(str)
    def checkQuota(self, token):
        token = (token or "").strip()
        if not token:
            self.emit_event("error", message="请先点击“网页登录并自动授权”，用账号密码登录后自动保存账号。")
            return
        self.emit_event("status", message="正在刷新额度...")
        threading.Thread(target=self._quota_worker, args=(token,), daemon=True).start()

    def _quota_worker(self, token, silent=False):
        try:
            import requests
            res = requests.get(
                "https://api.us.elevenlabs.io/v1/user",
                headers={"authorization": "Bearer " + token, "Cache-Control": "no-cache"},
                timeout=30,
            )
            if not res.ok:
                message, _ = _elevenlabs_error_message(res, "额度获取")
                raise Exception(message)
            subscription = res.json().get("subscription", {})
            used = int(subscription.get("character_count", 0) or 0)
            total = int(subscription.get("character_limit", 0) or 0)
            left = max(0, total - used)
            self.emit_event("quota", token=token, used=used, total=total, left=left)
            if not silent:
                self.emit_event("status", message="额度已刷新")
        except Exception as e:
            self.emit_event("quotaError", token=token, message=str(e))
            if not silent:
                self.emit_event("error", message=f"额度获取失败: {e}")

    @pyqtSlot(result=str)
    def selectOutputDir(self):
        default_dir = self._state_from_settings().get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace", "ElevenLabs_辅助语音")
        os.makedirs(default_dir, exist_ok=True)
        path = QFileDialog.getExistingDirectory(None, "选择 ElevenLabs 辅助语音输出目录", default_dir)
        return path or ""

    @pyqtSlot(str)
    def openOutputDir(self, path):
        target = path or self._state_from_settings().get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace", "ElevenLabs_辅助语音")
        os.makedirs(target, exist_ok=True)
        try:
            os.startfile(target)
        except Exception as e:
            self.emit_event("error", message=f"打开目录失败: {e}")

    @pyqtSlot()
    def openOfficialGenerator(self):
        QDesktopServices.openUrl(QUrl(OFFICIAL_TTS_URL))

    @pyqtSlot()
    def stopGeneration(self):
        self.stop_requested = True
        self.emit_event("status", message="正在停止生成...")

    @pyqtSlot(str)
    def generate(self, payload):
        if self.is_running:
            return
        try:
            cfg = json.loads(payload or "{}")
        except Exception as e:
            self.emit_event("error", message=f"生成参数错误: {e}")
            return
        token = (cfg.get("currentToken") or "").strip()
        voice_id = (cfg.get("voiceId") or "").strip()
        segments = [s.strip() for s in (cfg.get("segments") or []) if str(s).strip()]
        if not token:
            self.emit_event("error", message="请先点击“网页登录并自动授权”，用账号密码登录后自动保存账号。")
            return
        if not voice_id:
            self.emit_event("error", message="请先选择声音。")
            return
        if not segments:
            self.emit_event("error", message="没有需要生成的文案。")
            return
        self._save_state_dict(cfg)
        self.is_running = True
        self.stop_requested = False
        self.emit_event("generationStart", total=len(segments))
        threading.Thread(target=self._generate_worker, args=(segments, cfg), daemon=True).start()

    def _generate_worker(self, segments, cfg):
        try:
            import requests
            output_dir = cfg.get("outputDir") or os.path.join(os.getcwd(), "MyWorkspace", "ElevenLabs_辅助语音")
            sub_folder = _safe_filename(cfg.get("subFolder") or "批量导出", "批量导出")
            output_dir = os.path.join(output_dir, sub_folder)
            os.makedirs(output_dir, exist_ok=True)
            model = cfg.get("model") or "eleven_flash_v2_5"
            compat_mode = bool(cfg.get("compatMode", True))
            voice_settings = {
                "stability": float(cfg.get("stability", 0.5) or 0.5),
                "similarity_boost": float(cfg.get("similarity", 0.75) or 0.75),
            }
            if model == "eleven_multilingual_v2":
                voice_settings["style"] = float(cfg.get("style", 0.0) or 0.0)
                voice_settings["use_speaker_boost"] = bool(cfg.get("speakerBoost", True))
            headers = {
                "authorization": "Bearer " + cfg["currentToken"],
                "content-type": "application/json",
                "accept": "audio/mpeg,audio/*,*/*",
                "origin": "https://elevenlabs.io",
                "referer": "https://elevenlabs.io/",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            }
            total = max(1, len(segments))
            for idx, text in enumerate(segments, start=1):
                if self.stop_requested:
                    self.emit_event("status", message="已停止生成")
                    break
                self.emit_event("progress", value=int((idx - 1) * 100 / total), message=f"生成 {idx}/{total} ...")
                payload = {"text": text, "model_id": model}
                if not compat_mode:
                    payload["voice_settings"] = voice_settings
                res = requests.post(
                    f"https://api.us.elevenlabs.io/v1/text-to-speech/{cfg['voiceId']}/stream",
                    headers=headers,
                    json=payload,
                    timeout=180,
                )
                if not res.ok:
                    message, popup = _elevenlabs_error_message(res, f"第 {idx} 段生成")
                    raise ElevenLabsUserError(message, popup=popup)
                path = os.path.join(output_dir, f"{idx:03d}_{_safe_filename(text)}.mp3")
                with open(path, "wb") as f:
                    f.write(res.content)
                self.emit_event("log", message=f"已保存: {path}")
                self.emit_event("progress", value=int(idx * 100 / total), message=f"完成 {idx}/{total}")
                if compat_mode and idx < len(segments) and not self.stop_requested:
                    time.sleep(random.uniform(2.5, 4.5))
            self.emit_event("generated", outputDir=output_dir)
            self._quota_worker(cfg["currentToken"], silent=True)
        except Exception as e:
            self.emit_event("error", message=f"生成失败: {e}", popup=bool(getattr(e, "popup", False)))
        finally:
            self.is_running = False
            self.stop_requested = False
            self.emit_event("generationFinished")


ASSIST_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ElevenLabs 辅助语音</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    :root { --bg-main:#1e1e24; --bg-sidebar:#25252d; --bg-input:#33333d; --text-main:#f0f0f0; --text-sub:#a0a0a0; --primary:#6366f1; --primary-hover:#4f46e5; --danger:#ef4444; --success:#10b981; --border:#3f3f4a; --shadow:0 4px 12px rgba(0,0,0,.2); }
    :root.light-theme { --bg-main:#f4f5f7; --bg-sidebar:#fff; --bg-input:#f0f1f4; --text-main:#1f2937; --text-sub:#6b7280; --primary:#4f46e5; --primary-hover:#4338ca; --border:#e5e7eb; --shadow:0 4px 12px rgba(0,0,0,.05); }
    * { box-sizing:border-box; }
    html, body { height:100%; }
    body { margin:0; background:var(--bg-main); color:var(--text-main); font:14px system-ui, "Microsoft YaHei", sans-serif; overflow:hidden; }
    button, input, textarea, select { font:inherit; }
    .app { display:flex; height:100vh; min-width:760px; }
    .sidebar { width:350px; flex:0 0 350px; background:var(--bg-sidebar); padding:22px; border-right:1px solid var(--border); display:flex; flex-direction:column; overflow:auto; }
    .content { flex:1; min-width:0; padding:22px 34px; display:flex; flex-direction:column; }
    .header { display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; }
    .brand { display:flex; align-items:center; gap:10px; font-size:19px; font-weight:900; }
    .logo { width:34px; height:34px; border-radius:10px; display:grid; place-items:center; background:linear-gradient(135deg,#8b5cf6,#ec4899); color:white; font-weight:900; }
    .round { width:32px; height:32px; border-radius:50%; border:1px solid var(--border); background:var(--bg-input); color:var(--text-main); cursor:pointer; }
    .account-card { background:var(--bg-input); padding:13px; border-radius:8px; display:flex; align-items:center; gap:12px; border:1px solid var(--border); cursor:pointer; position:relative; }
    .dot { width:11px; height:11px; border-radius:50%; background:var(--danger); box-shadow:0 0 8px rgba(0,0,0,.25); }
    .dot.ok { background:var(--success); }
    .account-name { font-weight:800; margin-bottom:3px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
    .quota { color:var(--text-sub); font-size:12px; }
    .dropdown { position:absolute; left:0; right:0; top:calc(100% + 6px); max-height:270px; overflow:auto; z-index:5; background:var(--bg-sidebar); border:1px solid var(--border); border-radius:8px; padding:6px; box-shadow:var(--shadow); }
    .dropdown-item { padding:8px; border-radius:6px; display:flex; align-items:center; justify-content:space-between; gap:8px; cursor:pointer; }
    .dropdown-item:hover, .dropdown-item.active { background:var(--bg-input); color:var(--primary); }
    .hidden { display:none !important; }
    .row { display:flex; gap:8px; align-items:center; }
    .group { margin-top:16px; }
    label { display:block; font-weight:800; color:var(--text-sub); margin-bottom:7px; font-size:12px; text-transform:uppercase; }
    input, select, textarea { width:100%; border:1px solid var(--border); background:var(--bg-main); color:var(--text-main); border-radius:7px; outline:none; }
    input, select { height:38px; padding:0 11px; }
    textarea { min-height:110px; padding:14px; line-height:1.6; resize:vertical; box-shadow:var(--shadow); }
    input:focus, select:focus, textarea:focus { border-color:var(--primary); }
    .btn { border:0; border-radius:7px; height:38px; padding:0 13px; cursor:pointer; font-weight:800; white-space:nowrap; }
    .primary { background:var(--primary); color:#fff; }
    .primary:hover { background:var(--primary-hover); }
    .soft { background:var(--bg-input); color:var(--text-main); border:1px solid var(--border); }
    .danger { background:var(--danger); color:#fff; }
    .divider { height:1px; background:var(--border); margin:20px 0; }
    .status { margin-top:auto; padding-top:18px; color:var(--primary); font-weight:800; text-align:center; word-break:break-word; font-size:12px; }
    .toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; gap:14px; }
    h2 { margin:0; font-size:20px; }
    .cards { flex:1; overflow:auto; padding-right:10px; }
    .card { position:relative; margin-bottom:14px; }
    .card .del { position:absolute; right:10px; top:10px; height:28px; padding:0 9px; opacity:.75; }
    .footer { border-top:1px solid var(--border); padding-top:18px; display:flex; justify-content:space-between; align-items:center; gap:20px; }
    .stats { color:var(--text-sub); font-weight:800; }
    .actions { display:flex; gap:12px; }
    .progress { height:4px; background:var(--border); margin-bottom:12px; }
    .progress span { display:block; height:100%; width:0; background:var(--primary); transition:width .2s; }
    .token-list { display:flex; flex-direction:column; gap:7px; max-height:190px; overflow:auto; }
    .token-item { display:flex; align-items:center; gap:8px; background:var(--bg-input); border:1px solid var(--border); border-radius:7px; padding:8px; }
    .token-item.active { border-color:var(--primary); }
    .token-main { flex:1; min-width:0; }
    .token-alias { font-weight:800; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .token-code { font:11px Consolas, monospace; color:var(--text-sub); }
    .mini { height:28px; padding:0 8px; }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="header">
        <div class="brand"><div class="logo">U</div><span>网页授权语音</span></div>
        <button id="themeBtn" class="round" title="切换主题">☾</button>
      </div>

      <div id="accountCard" class="account-card">
        <div id="statusDot" class="dot"></div>
        <div style="min-width:0;flex:1">
          <div id="accountName" class="account-name">等待网页授权</div>
          <div id="quotaText" class="quota">请网页登录自动保存授权账号</div>
        </div>
        <span>▼</span>
        <div id="accountDropdown" class="dropdown hidden"></div>
      </div>

      <div class="group">
        <label>网页授权账号</label>
        <div class="row">
          <input id="aliasInput" type="text" placeholder="备注名">
          <button id="captureBtn" class="btn soft">网页登录并自动授权</button>
        </div>
        <div class="row" style="margin-top:8px">
          <input id="tokenInput" type="text" placeholder="可选：粘贴已捕获授权，一般不用填">
          <button id="saveTokenBtn" class="btn primary">手动保存</button>
        </div>
        <div class="quota" style="margin-top:7px">不用 API Key，也不用手动找授权串；点上方按钮，用账号密码登录即可自动保存。</div>
      </div>

      <div class="group token-list" id="tokenList"></div>

      <div class="divider"></div>

      <div class="group">
        <label>导出位置</label>
        <div class="row">
          <input id="outputDir" type="text" placeholder="默认 MyWorkspace/ElevenLabs_辅助语音">
          <button id="chooseDirBtn" class="btn soft">选择</button>
          <button id="openDirBtn" class="btn soft">打开</button>
        </div>
        <input id="subFolder" type="text" placeholder="子文件夹，例如 客户A" style="margin-top:8px">
      </div>

      <div class="group">
        <label>Voice</label>
        <div class="row">
          <select id="voiceSelect"><option value="">等待网页授权...</option></select>
          <button id="refreshBtn" class="btn soft">刷新</button>
        </div>
      </div>

      <div class="group">
        <label>Model</label>
        <select id="modelSelect">
          <option value="eleven_flash_v2_5">Flash v2.5</option>
          <option value="eleven_turbo_v2_5">Turbo v2.5</option>
          <option value="eleven_multilingual_v2">Multilingual v2</option>
          <option value="eleven_v3">Eleven v3</option>
        </select>
      </div>

      <div class="group row" style="justify-content:space-between">
        <label style="margin:0;text-transform:none">生成完成自动删除文案</label>
        <input id="autoDelete" type="checkbox" style="width:auto" checked>
      </div>

      <div id="status" class="status">准备就绪</div>
    </aside>

    <main class="content">
      <div class="toolbar">
        <h2>文案列表</h2>
        <div class="row">
          <button id="clearBtn" class="btn soft">清空草稿</button>
          <button id="addBtn" class="btn soft">+ 新增一段</button>
        </div>
      </div>
      <div id="cards" class="cards"></div>
      <div class="progress"><span id="progressBar"></span></div>
      <div class="footer">
        <div>
          <div id="stats" class="stats">总字数: 0</div>
          <div id="logLine" class="quota"></div>
        </div>
        <div class="actions">
          <button id="stopBtn" class="btn danger hidden">停止生成</button>
          <button id="generateBtn" class="btn primary">开始批量生成</button>
        </div>
      </div>
    </main>
  </div>

  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script>
    const $ = id => document.getElementById(id);
    let bridge = null;
    let saveTimer = null;
    const state = {
      accounts: [], currentToken: "", voiceId: "", model: "eleven_flash_v2_5",
      outputDir: "", subFolder: "批量导出", autoDelete: true, cards: [""], voices: []
    };
    const mask = token => token ? "..." + token.slice(-8) : "----";
    const account = () => state.accounts.find(a => a.token === state.currentToken) || null;
    const setStatus = (msg, error=false) => { $("status").textContent = msg || "准备就绪"; $("status").style.color = error ? "var(--danger)" : "var(--primary)"; };
    const setLog = msg => $("logLine").textContent = msg || "";
    const progress = value => $("progressBar").style.width = Math.max(0, Math.min(100, value || 0)) + "%";

    function collect() {
      state.voiceId = $("voiceSelect").value || state.voiceId;
      state.model = $("modelSelect").value;
      state.outputDir = $("outputDir").value.trim();
      state.subFolder = $("subFolder").value.trim() || "批量导出";
      state.autoDelete = $("autoDelete").checked;
    }
    function persist() {
      if (!bridge) return;
      collect();
      bridge.saveState(JSON.stringify(state));
    }
    function persistSoon() { clearTimeout(saveTimer); saveTimer = setTimeout(persist, 250); }

    function renderAll() {
      $("modelSelect").value = state.model || "eleven_flash_v2_5";
      $("outputDir").value = state.outputDir || "";
      $("subFolder").value = state.subFolder || "批量导出";
      $("autoDelete").checked = state.autoDelete !== false;
      renderAccounts();
      renderVoices();
      renderCards();
    }

    function renderAccounts() {
      const acc = account();
      $("statusDot").classList.toggle("ok", !!state.currentToken);
      $("accountName").textContent = acc ? (acc.alias || "网页账号") : "等待网页授权";
      $("quotaText").textContent = acc && typeof acc.left === "number" ? `额度: ${acc.used} / ${acc.total} (剩余 ${acc.left})` : "请网页登录自动保存授权账号";
      const dd = $("accountDropdown");
      dd.innerHTML = state.accounts.length ? "" : "<div class='dropdown-item'>暂无账号</div>";
      state.accounts.forEach((item) => {
        const div = document.createElement("div");
        div.className = "dropdown-item" + (item.token === state.currentToken ? " active" : "");
        div.innerHTML = `<span>${escapeHtml(item.alias || "网页账号")}</span><span class="quota">${typeof item.left === "number" ? item.left : "未查"}</span>`;
        div.onclick = () => switchAccount(item.token);
        dd.appendChild(div);
      });
      renderTokenList();
      updateStats();
    }

    function renderTokenList() {
      const list = $("tokenList");
      list.innerHTML = "";
      if (!state.accounts.length) {
        list.innerHTML = "<div class='quota'>暂无保存账号。点“网页登录并自动授权”，用账号密码登录后会自动保存。</div>";
        return;
      }
      state.accounts.forEach((item, idx) => {
        const div = document.createElement("div");
        div.className = "token-item" + (item.token === state.currentToken ? " active" : "");
        div.innerHTML = `
          <div class="token-main"><div class="token-alias">${escapeHtml(item.alias || "网页账号")}</div><div class="token-code">${mask(item.token)}</div></div>
          <button class="btn soft mini edit">改名</button>
          <button class="btn soft mini del">删</button>`;
        div.onclick = event => { if (!event.target.closest("button")) switchAccount(item.token); };
        div.querySelector(".edit").onclick = event => {
          event.stopPropagation();
          const name = prompt("新的账号备注", item.alias || `网页账号 ${idx + 1}`);
          if (name && name.trim()) { item.alias = name.trim(); renderAccounts(); persist(); }
        };
        div.querySelector(".del").onclick = event => {
          event.stopPropagation();
          state.accounts.splice(idx, 1);
          if (state.currentToken === item.token) state.currentToken = state.accounts[0]?.token || "";
          renderAccounts(); persist();
        };
        list.appendChild(div);
      });
    }

    function addToken(alias, token) {
      token = (token || "").replace(/^Bearer\\s+/i, "").trim();
      if (token.length <= 20) return setStatus("授权内容无效，建议点网页登录自动获取", true);
      let item = state.accounts.find(a => a.token === token);
      if (!item) {
        item = { alias: alias || `网页账号 ${state.accounts.length + 1}`, token };
        state.accounts.push(item);
      } else if (alias) {
        item.alias = alias;
      }
      state.currentToken = token;
      $("tokenInput").value = "";
      renderAccounts();
      persist();
      refreshCurrent();
    }

    function switchAccount(token) {
      state.currentToken = token || "";
      renderAccounts();
      persist();
      refreshCurrent();
      $("accountDropdown").classList.add("hidden");
    }

    function renderVoices() {
      const select = $("voiceSelect");
      select.innerHTML = "";
      if (!state.voices.length) {
        select.innerHTML = "<option value=''>等待网页授权...</option>";
        return;
      }
      state.voices.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.voice_id || "";
        opt.textContent = v.name || "Unnamed";
        select.appendChild(opt);
      });
      if (state.voiceId && [...select.options].some(o => o.value === state.voiceId)) select.value = state.voiceId;
    }

    function renderCards() {
      const box = $("cards");
      box.innerHTML = "";
      state.cards = state.cards.length ? state.cards : [""];
      state.cards.forEach((text, idx) => {
        const div = document.createElement("div");
        div.className = "card";
        div.innerHTML = `<textarea placeholder="输入文案，支持从表格复制多行">${escapeHtml(text)}</textarea><button class="btn soft del">删除</button>`;
        const ta = div.querySelector("textarea");
        ta.oninput = () => { state.cards[idx] = ta.value; updateStats(); persistSoon(); };
        div.querySelector(".del").onclick = () => { state.cards.splice(idx, 1); if (!state.cards.length) state.cards = [""]; renderCards(); persist(); };
        box.appendChild(div);
      });
      updateStats();
    }

    function updateStats() {
      const total = state.cards.reduce((sum, text) => sum + (text || "").trim().length, 0);
      $("stats").textContent = `总字数: ${total.toLocaleString()} | 预计消耗: ${total.toLocaleString()}`;
      const acc = account();
      $("stats").style.color = acc && typeof acc.left === "number" && total > acc.left ? "var(--danger)" : "var(--text-sub)";
    }

    function refreshCurrent() {
      if (!bridge || !state.currentToken) return;
      bridge.checkQuota(state.currentToken);
      bridge.refreshVoices(state.currentToken);
    }

    function startGenerate() {
      collect();
      const segments = state.cards.map(t => (t || "").trim()).filter(Boolean);
      bridge.generate(JSON.stringify({...state, segments}));
    }

    function onEvent(raw) {
      let data = {};
      try { data = JSON.parse(raw); } catch { return; }
      if (data.type === "status") setStatus(data.message);
      if (data.type === "error") { setStatus(data.message, true); setLog(data.message); $("generateBtn").classList.remove("hidden"); $("stopBtn").classList.add("hidden"); }
      if (data.type === "capturedToken") addToken($("aliasInput").value.trim(), data.token);
      if (data.type === "voices") { state.voices = data.voices || []; renderVoices(); persist(); }
      if (data.type === "quota") {
        const item = state.accounts.find(a => a.token === data.token);
        if (item) { item.used = data.used; item.total = data.total; item.left = data.left; }
        renderAccounts(); persist();
      }
      if (data.type === "quotaError") setLog(`额度刷新失败: ${data.message}`);
      if (data.type === "generationStart") { $("generateBtn").classList.add("hidden"); $("stopBtn").classList.remove("hidden"); progress(0); setLog(""); setStatus(`开始生成 ${data.total} 段...`); }
      if (data.type === "progress") { progress(data.value); setStatus(data.message); }
      if (data.type === "log") setLog(data.message);
      if (data.type === "generated") { progress(100); setStatus("生成完成"); setLog(`输出目录: ${data.outputDir}`); if (state.autoDelete) { state.cards = [""]; renderCards(); } persist(); }
      if (data.type === "generationFinished") { $("generateBtn").classList.remove("hidden"); $("stopBtn").classList.add("hidden"); }
    }

    function escapeHtml(text) {
      return String(text ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[ch]));
    }

    function wire() {
      $("themeBtn").onclick = () => document.documentElement.classList.toggle("light-theme");
      $("accountCard").onclick = event => { event.stopPropagation(); $("accountDropdown").classList.toggle("hidden"); };
      document.addEventListener("click", () => $("accountDropdown").classList.add("hidden"));
      $("captureBtn").onclick = () => bridge && bridge.openTokenCapture();
      $("saveTokenBtn").onclick = () => addToken($("aliasInput").value.trim(), $("tokenInput").value);
      $("refreshBtn").onclick = refreshCurrent;
      $("chooseDirBtn").onclick = () => bridge && bridge.selectOutputDir(path => { if (path) { state.outputDir = path; $("outputDir").value = path; persist(); }});
      $("openDirBtn").onclick = () => { collect(); bridge && bridge.openOutputDir(state.outputDir); };
      $("addBtn").onclick = () => { state.cards.push(""); renderCards(); persist(); };
      $("clearBtn").onclick = () => { state.cards = [""]; renderCards(); persist(); };
      $("generateBtn").onclick = startGenerate;
      $("stopBtn").onclick = () => bridge && bridge.stopGeneration();
      $("cards").addEventListener("paste", event => {
        const text = (event.clipboardData || window.clipboardData).getData("text");
        if (!text || (!text.includes("\t") && !text.includes("\n"))) return;
        event.preventDefault();
        const parts = text.split(/\r?\n|\t/).map(s => s.trim()).filter(Boolean);
        if (parts.length) {
          if (state.cards.length === 1 && !state.cards[0].trim()) state.cards = [];
          state.cards.push(...parts);
          renderCards(); persist();
          setStatus(`已导入 ${parts.length} 条文案`);
        }
      });
      ["modelSelect","voiceSelect","outputDir","subFolder","autoDelete"].forEach(id => $(id).addEventListener("change", persistSoon));
      ["outputDir","subFolder"].forEach(id => $(id).addEventListener("input", persistSoon));
    }

    wire();
    new QWebChannel(qt.webChannelTransport, channel => {
      bridge = channel.objects.elevenAssistBridge;
      bridge.event.connect(onEvent);
      bridge.getState(raw => {
        Object.assign(state, JSON.parse(raw || "{}"));
        renderAll();
        refreshCurrent();
      });
    });
  </script>
</body>
</html>
"""


class ElevenLabsAssistTool(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_colors = None
        self._theme_key = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.view.loadFinished.connect(self._on_load_finished)
        self.bridge = ElevenLabsAssistBridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("elevenAssistBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        load_web_tool_page(self.view, "elevenlabs_assist", ASSIST_HTML, os.getcwd())
        layout.addWidget(self.view)

    def _on_load_finished(self, ok):
        if ok and self._theme_colors:
            self.view.page().runJavaScript(web_theme_script(self._theme_colors, self._theme_key))

    def apply_theme(self, colors, theme_key=None):
        self._theme_colors = colors
        self._theme_key = theme_key or ""
        self.view.page().runJavaScript(web_theme_script(colors, self._theme_key))


def create_elevenlabs_assist_tool(parent=None):
    if WEBENGINE_AVAILABLE:
        return ElevenLabsAssistTool(parent)
    return QWidget(parent)
