(function () {
  const defaultState = {
    accounts: [],
    currentToken: "",
    voiceId: "",
    model: "eleven_flash_v2_5",
    outputDir: "",
    subFolder: "批量导出",
    stability: 0.5,
    similarity: 0.75,
    style: 0,
    speakerBoost: true,
    compatMode: true,
    autoDelete: true,
    cards: [""],
    voices: []
  };

  let bridge = null;
  let saveTimer = 0;
  const state = { ...defaultState };
  const app = document.getElementById("app");

  app.innerHTML = `
    <div class="sc-tool">
      <aside class="sc-sidebar">
        <div class="sc-brand">
          <div class="sc-title"><strong>网页登录授权语音</strong><span>Token 捕获与批量生成</span></div>
          <span class="sc-pill" id="ready-pill">Bridge</span>
        </div>

        <section class="sc-card sc-account">
          <span class="sc-dot" id="account-dot"></span>
          <div>
            <div class="sc-account-name" id="account-name">未授权</div>
            <div class="sc-account-quota" id="account-quota">请网页登录授权</div>
          </div>
          <button class="sc-icon-button" id="open-settings">设置</button>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">账号切换</label>
          <div class="sc-row">
            <select class="sc-select" id="account-select"></select>
            <button class="sc-button primary" id="capture-token">网页登录</button>
            <button class="sc-button" id="official-generator">官网生成</button>
          </div>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">输出</label>
          <div class="sc-row">
            <input class="sc-field" id="output-dir" placeholder="选择输出目录" />
            <button class="sc-icon-button" id="pick-output">...</button>
            <button class="sc-icon-button" id="open-output">开</button>
          </div>
          <input class="sc-field" id="sub-folder" placeholder="子文件夹名称" />
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">声音</label>
          <div class="sc-row">
            <select class="sc-select" id="voice-select"></select>
            <button class="sc-icon-button" id="refresh-voices">刷</button>
          </div>
          <input class="sc-field" id="voice-id" placeholder="或手动填写 Voice ID" />
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">模型</label>
          <select class="sc-select" id="model">
            <option value="eleven_flash_v2_5">Flash v2.5</option>
            <option value="eleven_turbo_v2_5">Turbo v2.5</option>
            <option value="eleven_multilingual_v2">Multilingual v2</option>
            <option value="eleven_v3">Eleven v3</option>
          </select>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">Voice Settings</label>
          <div class="sc-note">Stability <b id="stability-value">0.50</b></div>
          <input id="stability" type="range" min="0" max="1" step="0.01" />
          <div class="sc-note">Similarity <b id="similarity-value">0.75</b></div>
          <input id="similarity" type="range" min="0" max="1" step="0.01" />
          <div class="sc-note">Style <b id="style-value">0.00</b></div>
          <input id="style" type="range" min="0" max="1" step="0.01" />
          <label class="sc-note"><input id="speaker-boost" type="checkbox" /> Speaker Boost</label>
          <label class="sc-note"><input id="compat-mode" type="checkbox" /> 插件兼容请求</label>
          <label class="sc-note"><input id="auto-delete" type="checkbox" /> 生成后清空文案</label>
        </section>

        <div class="sc-status" id="status">就绪</div>
      </aside>

      <main class="sc-main">
        <header class="sc-topbar">
          <div><strong>文案段落</strong><div class="sc-note" id="stats">0 字</div></div>
          <div class="sc-row">
            <button class="sc-button" id="clear-cards">清空</button>
            <button class="sc-button" id="add-card">新增段落</button>
          </div>
        </header>
        <div class="sc-list" id="card-list"></div>
        <div>
          <div class="sc-progress"><span id="progress"></span></div>
          <footer class="sc-footer">
            <div class="sc-status" id="log-line"></div>
            <div class="sc-row">
              <button class="sc-button danger" id="stop">停止</button>
              <button class="sc-button success" id="generate">批量生成</button>
            </div>
          </footer>
        </div>
      </main>
    </div>

    <div class="sc-modal" id="settings-modal">
      <div class="sc-modal-panel sc-stack">
        <div class="sc-brand">
          <div class="sc-title"><strong>授权账号</strong><span>网页登录后会自动捕获并保存 Token</span></div>
          <button class="sc-icon-button" id="close-settings">关</button>
        </div>
        <button class="sc-button primary" id="capture-token-modal">网页登录并自动授权</button>
        <div class="sc-key-list" id="token-list"></div>
      </div>
    </div>
  `;

  function byId(id) {
    const node = document.getElementById(id);
    if (!node) throw new Error("Missing element: " + id);
    return node;
  }

  function parseJson(raw, fallback) {
    try {
      return JSON.parse(raw || "");
    } catch {
      return fallback;
    }
  }

  function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    })[ch] ?? ch);
  }

  function splitPastedSegments(text) {
    const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    if (!normalized.includes("\t") && !normalized.includes("\n")) return [];
    return normalized.split(/\t|\n/).map((item) => item.trim()).filter(Boolean);
  }

  function applySpreadsheetPaste(event, index) {
    const text = event.clipboardData?.getData("text/plain") || "";
    const segments = splitPastedSegments(text);
    if (segments.length <= 1) return;
    event.preventDefault();
    const before = state.cards.slice(0, index);
    const after = state.cards.slice(index + 1);
    state.cards = after.every((item) => !item.trim()) ? [...before, ...segments] : [...before, ...segments, ...after];
    renderCards();
    persist();
    setStatus("已按表格内容拆成 " + segments.length + " 段");
  }

  function currentAccount() {
    return state.accounts.find((item) => item.token === state.currentToken) || null;
  }

  function quotaText(account) {
    if (!account || typeof account.left !== "number") return "未查询额度";
    return "剩余 " + account.left.toLocaleString() + " / " + (account.total || 0).toLocaleString() + " 字";
  }

  function setStatus(message, isError) {
    const status = byId("status");
    status.textContent = message || "就绪";
    status.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  function collectControls() {
    state.outputDir = byId("output-dir").value.trim();
    state.subFolder = byId("sub-folder").value.trim() || "批量导出";
    state.voiceId = byId("voice-id").value.trim() || byId("voice-select").value || state.voiceId;
    state.model = byId("model").value;
    state.stability = Number(byId("stability").value);
    state.similarity = Number(byId("similarity").value);
    state.style = Number(byId("style").value);
    state.speakerBoost = byId("speaker-boost").checked;
    state.compatMode = byId("compat-mode").checked;
    state.autoDelete = byId("auto-delete").checked;
  }

  function persist() {
    if (!bridge) return;
    collectControls();
    bridge.saveState(JSON.stringify(state));
  }

  function persistSoon() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(persist, 280);
  }

  function renderControls() {
    byId("output-dir").value = state.outputDir || "";
    byId("sub-folder").value = state.subFolder || "批量导出";
    byId("voice-id").value = state.voiceId || "";
    byId("model").value = state.model || defaultState.model;
    byId("stability").value = String(state.stability ?? 0.5);
    byId("similarity").value = String(state.similarity ?? 0.75);
    byId("style").value = String(state.style ?? 0);
    byId("stability-value").textContent = Number(state.stability ?? 0.5).toFixed(2);
    byId("similarity-value").textContent = Number(state.similarity ?? 0.75).toFixed(2);
    byId("style-value").textContent = Number(state.style ?? 0).toFixed(2);
    byId("speaker-boost").checked = state.speakerBoost !== false;
    byId("compat-mode").checked = state.compatMode !== false;
    byId("auto-delete").checked = state.autoDelete !== false;
  }

  function renderAccounts() {
    const account = currentAccount();
    byId("account-dot").classList.toggle("active", Boolean(state.currentToken));
    byId("account-name").textContent = account?.alias || (state.currentToken ? "网页账号" : "未授权");
    byId("account-quota").textContent = quotaText(account);

    const select = byId("account-select");
    select.innerHTML = "";
    if (!state.accounts.length) {
      select.innerHTML = "<option value=''>暂无授权账号</option>";
    } else {
      state.accounts.forEach((item, index) => {
        const option = document.createElement("option");
        option.value = item.token;
        option.textContent = (item.alias || "网页账号 " + (index + 1)) + " · " + quotaText(item);
        select.appendChild(option);
      });
      select.value = state.currentToken || state.accounts[0]?.token || "";
    }

    const list = byId("token-list");
    list.innerHTML = "";
    if (!state.accounts.length) {
      list.innerHTML = `<div class="sc-note">暂无授权账号。点击“网页登录并自动授权”后保存。</div>`;
    } else {
      state.accounts.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "sc-key" + (item.token === state.currentToken ? " active" : "");
        row.innerHTML = `
          <div><strong>${escapeHtml(item.alias || `网页账号 ${index + 1}`)}</strong><div class="sc-note">**** ${escapeHtml(item.token.slice(-6))}</div></div>
          <span class="sc-note">${quotaText(item)}</span>
          <button class="sc-button danger">删除</button>
        `;
        row.addEventListener("click", (event) => {
          if (event.target.tagName === "BUTTON") return;
          switchAccount(item.token);
        });
        row.querySelector("button").addEventListener("click", () => {
          state.accounts.splice(index, 1);
          if (state.currentToken === item.token) state.currentToken = state.accounts[0]?.token || "";
          renderAccounts();
          persist();
        });
        list.appendChild(row);
      });
    }
    renderStats();
  }

  function renderVoices() {
    const select = byId("voice-select");
    select.innerHTML = "";
    const voices = state.voices || [];
    if (!voices.length) {
      select.innerHTML = "<option value=''>请先刷新声音</option>";
      return;
    }
    voices
      .slice()
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""))
      .forEach((voice) => {
        const option = document.createElement("option");
        option.value = voice.voice_id || "";
        option.textContent = voice.category ? `${voice.name} · ${voice.category}` : voice.name || "Unnamed";
        select.appendChild(option);
      });
    if (state.voiceId && [...select.options].some((option) => option.value === state.voiceId)) {
      select.value = state.voiceId;
      byId("voice-id").value = "";
    }
  }

  function renderCards() {
    const list = byId("card-list");
    list.innerHTML = "";
    if (!state.cards.length) state.cards = [""];
    state.cards.forEach((text, index) => {
      const card = document.createElement("section");
      card.className = "sc-editor-card";
      card.innerHTML = `
        <textarea class="sc-textarea" placeholder="输入第 ${index + 1} 段文案">${escapeHtml(text)}</textarea>
        <footer><span>段落 ${index + 1} · <b>${text.length}</b> 字</span><button class="sc-button danger">删除</button></footer>
      `;
      const textarea = card.querySelector("textarea");
      const count = card.querySelector("b");
      textarea.addEventListener("paste", (event) => applySpreadsheetPaste(event, index));
      textarea.addEventListener("input", () => {
        state.cards[index] = textarea.value;
        count.textContent = String(textarea.value.length);
        renderStats();
        persistSoon();
      });
      card.querySelector("button").addEventListener("click", () => {
        state.cards.splice(index, 1);
        if (!state.cards.length) state.cards = [""];
        renderCards();
        persist();
      });
      list.appendChild(card);
    });
    renderStats();
  }

  function renderStats() {
    const total = state.cards.reduce((sum, text) => sum + (text || "").length, 0);
    const segments = state.cards.filter((text) => text.trim()).length;
    byId("stats").textContent = total.toLocaleString() + " 字 · " + segments + " 段";
  }

  function renderAll() {
    renderControls();
    renderAccounts();
    renderVoices();
    renderCards();
  }

  function switchAccount(token, shouldPersist = true) {
    state.currentToken = token;
    renderAccounts();
    if (shouldPersist) persist();
    if (bridge && token) {
      setStatus("正在刷新授权账号...");
      bridge.checkQuota(token);
      bridge.refreshVoices(token);
    }
  }

  function setProgress(value) {
    byId("progress").style.width = Math.max(0, Math.min(100, value)) + "%";
  }

  function onBridgeEvent(raw) {
    const event = parseJson(raw, {});
    if (event.type === "status") setStatus(event.message || "");
    if (event.type === "error") {
      setStatus(event.message || "操作失败", true);
      byId("log-line").textContent = event.message || "";
      byId("generate").disabled = false;
      if (event.popup) window.alert(event.message || "操作失败");
    }
    if (event.type === "capturedToken" && event.token) {
      const exists = state.accounts.some((item) => item.token === event.token);
      if (!exists) state.accounts.push({ alias: "网页账号 " + (state.accounts.length + 1), token: event.token });
      switchAccount(event.token, false);
      persist();
    }
    if (event.type === "voices") {
      state.voices = event.voices || [];
      renderVoices();
    }
    if (event.type === "quota" && event.token) {
      const account = state.accounts.find((item) => item.token === event.token);
      if (account) {
        account.left = event.left;
        account.total = event.total;
      }
      renderAccounts();
      persist();
    }
    if (event.type === "progress") {
      setProgress(event.value || 0);
      setStatus(event.message || "");
    }
    if (event.type === "log") byId("log-line").textContent = event.message || "";
    if (event.type === "generationStart") {
      byId("generate").disabled = true;
      setProgress(0);
      setStatus("开始生成...");
    }
    if (event.type === "generated") {
      state.outputDir = event.outputDir || state.outputDir;
      byId("output-dir").value = state.outputDir;
      setProgress(100);
      setStatus("生成完成");
      if (state.autoDelete) {
        state.cards = [""];
        renderCards();
      }
      persist();
    }
    if (event.type === "generationFinished") byId("generate").disabled = false;
  }

  function generate() {
    if (!bridge) return;
    collectControls();
    const segments = state.cards.map((text) => text.trim()).filter(Boolean);
    bridge.generate(JSON.stringify({ ...state, segments }));
  }

  function wireUi() {
    byId("open-settings").addEventListener("click", () => byId("settings-modal").classList.add("open"));
    byId("close-settings").addEventListener("click", () => byId("settings-modal").classList.remove("open"));
    byId("capture-token").addEventListener("click", () => bridge?.openTokenCapture());
    byId("official-generator").addEventListener("click", () => bridge?.openOfficialGenerator());
    byId("capture-token-modal").addEventListener("click", () => bridge?.openTokenCapture());
    byId("account-select").addEventListener("change", () => {
      const token = byId("account-select").value;
      if (token) switchAccount(token);
    });
    byId("pick-output").addEventListener("click", () => bridge?.selectOutputDir((path) => {
      if (!path) return;
      state.outputDir = path;
      byId("output-dir").value = path;
      persist();
    }));
    byId("open-output").addEventListener("click", () => {
      collectControls();
      bridge?.openOutputDir(state.outputDir);
    });
    byId("refresh-voices").addEventListener("click", () => bridge?.refreshVoices(state.currentToken));
    byId("add-card").addEventListener("click", () => {
      state.cards.push("");
      renderCards();
      persist();
    });
    byId("clear-cards").addEventListener("click", () => {
      state.cards = [""];
      renderCards();
      persist();
    });
    byId("generate").addEventListener("click", generate);
    byId("stop").addEventListener("click", () => bridge?.stopGeneration());
    ["output-dir", "sub-folder", "voice-id", "model", "stability", "similarity", "style", "speaker-boost", "compat-mode", "auto-delete"].forEach((id) => byId(id).addEventListener("input", () => {
      if (id === "stability" || id === "similarity" || id === "style") {
        byId(id + "-value").textContent = Number(byId(id).value).toFixed(2);
      }
      persistSoon();
    }));
    byId("voice-select").addEventListener("change", () => {
      state.voiceId = byId("voice-select").value;
      byId("voice-id").value = "";
      persist();
    });
  }

  function connectQtBridge(objectName) {
    return new Promise((resolve, reject) => {
      if (!window.qt || !window.QWebChannel) {
        reject(new Error("Qt WebChannel is not available."));
        return;
      }
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        const candidate = channel.objects[objectName];
        if (!candidate) {
          reject(new Error("Bridge object not found: " + objectName));
          return;
        }
        resolve(candidate);
      });
    });
  }

  wireUi();
  renderAll();

  connectQtBridge("elevenAssistBridge")
    .then((connectedBridge) => {
      bridge = connectedBridge;
      byId("ready-pill").textContent = "已连接";
      bridge.event.connect(onBridgeEvent);
      bridge.getState((raw) => {
        Object.assign(state, defaultState, parseJson(raw, {}));
        if (!state.cards.length) state.cards = [""];
        renderAll();
        if (state.currentToken) {
          bridge.checkQuota(state.currentToken);
          bridge.refreshVoices(state.currentToken);
        }
      });
    })
    .catch(() => {
      byId("ready-pill").textContent = "离线预览";
      setStatus("Qt Bridge 未连接，当前是前端预览模式", true);
    });
})();
