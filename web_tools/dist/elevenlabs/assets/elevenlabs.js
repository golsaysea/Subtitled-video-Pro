(function () {
  const defaultState = {
    accounts: [],
    currentKey: "",
    voiceId: "",
    model: "eleven_multilingual_v2",
    format: "mp3_44100_128",
    outputDir: "",
    stability: 0.5,
    similarity: 0.75,
    style: 0,
    speakerBoost: true,
    clearAfter: false,
    splitMode: 0,
    apiKeyLink: "https://elevenlabs.io/app/settings/api-keys",
    cards: [""],
    voices: []
  };

  let bridge = null;
  let saveTimer = 0;
  const state = { ...defaultState, currentQuota: null, currentLimit: null };
  const app = document.getElementById("app");

  app.innerHTML = `
    <div class="sc-tool">
      <aside class="sc-sidebar">
        <div class="sc-brand">
          <div class="sc-title"><strong>ElevenLabs</strong><span>批量语音控制台</span></div>
          <span class="sc-pill" id="ready-pill">Bridge</span>
        </div>

        <section class="sc-card sc-account" id="account-card">
          <span class="sc-dot" id="account-dot"></span>
          <div>
            <div class="sc-account-name" id="account-name">未配置账号</div>
            <div class="sc-account-quota" id="account-quota">请添加 API Key</div>
          </div>
          <button class="sc-icon-button" id="open-settings" title="账号设置">设置</button>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">账号切换</label>
          <div class="sc-row">
            <select class="sc-select" id="account-select"></select>
            <button class="sc-button" id="manage-accounts">管理</button>
          </div>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">快速 API Key</label>
          <div class="sc-row">
            <input class="sc-field" id="quick-key" type="password" placeholder="粘贴 Key 后回车" />
            <button class="sc-icon-button" id="quick-add" title="使用 Key">用</button>
          </div>
          <button class="sc-button" id="open-key-link">打开 API Key 页面</button>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">输出目录</label>
          <div class="sc-row">
            <input class="sc-field" id="output-dir" placeholder="选择音频输出目录" />
            <button class="sc-icon-button" id="pick-output" title="选择目录">...</button>
            <button class="sc-icon-button" id="open-output" title="打开目录">开</button>
          </div>
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">声音</label>
          <div class="sc-row">
            <select class="sc-select" id="voice-select"></select>
            <button class="sc-icon-button" id="refresh-voices" title="刷新声音">刷</button>
          </div>
          <input class="sc-field" id="voice-id" placeholder="或手动填写 Voice ID" />
        </section>

        <section class="sc-card sc-section sc-stack">
          <label class="sc-label">模型与格式</label>
          <select class="sc-select" id="model">
            <option value="eleven_multilingual_v2">Multilingual v2</option>
            <option value="eleven_turbo_v2_5">Turbo v2.5</option>
            <option value="eleven_flash_v2_5">Flash v2.5</option>
            <option value="eleven_v3">Eleven v3</option>
          </select>
          <select class="sc-select" id="format">
            <option value="mp3_44100_128">MP3 128k</option>
            <option value="mp3_44100_192">MP3 192k</option>
            <option value="pcm_44100">WAV PCM</option>
            <option value="mp3_as_mp4">MP4 伪装 / Canva</option>
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
          <label class="sc-note"><input id="clear-after" type="checkbox" /> 生成后清空文案</label>
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
            <button class="sc-button success" id="generate">批量生成</button>
          </footer>
        </div>
      </main>
    </div>

    <div class="sc-modal" id="settings-modal">
      <div class="sc-modal-panel sc-stack">
        <div class="sc-brand">
          <div class="sc-title"><strong>账号与备份</strong><span>管理 API Key、额度和配置</span></div>
          <button class="sc-icon-button" id="close-settings">关</button>
        </div>
        <input class="sc-field" id="api-key-link" placeholder="API Key 获取链接" />
        <div class="sc-key-list" id="key-list"></div>
        <div class="sc-row">
          <input class="sc-field" id="new-alias" placeholder="备注" />
          <input class="sc-field" id="new-key" type="password" placeholder="API Key" />
          <button class="sc-button primary" id="new-key-save">添加</button>
        </div>
        <div class="sc-row">
          <button class="sc-button" id="quota-all">查全部额度</button>
          <button class="sc-button" id="import-keys">导入 CSV</button>
          <button class="sc-button" id="export-keys">导出 CSV</button>
          <button class="sc-button" id="backup-config">备份</button>
          <button class="sc-button" id="restore-config">恢复</button>
        </div>
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
    return state.accounts.find((item) => item.key === state.currentKey) || null;
  }

  function quotaText(account) {
    if (!account || typeof account.quota_left !== "number") return "未查询额度";
    return "剩余 " + account.quota_left.toLocaleString() + " 字";
  }

  function setStatus(message, isError) {
    const status = byId("status");
    status.textContent = message || "就绪";
    status.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  function collectControls() {
    state.outputDir = byId("output-dir").value.trim();
    state.voiceId = byId("voice-id").value.trim() || byId("voice-select").value || state.voiceId;
    state.model = byId("model").value;
    state.format = byId("format").value;
    state.stability = Number(byId("stability").value);
    state.similarity = Number(byId("similarity").value);
    state.style = Number(byId("style").value);
    state.speakerBoost = byId("speaker-boost").checked;
    state.clearAfter = byId("clear-after").checked;
    state.apiKeyLink = byId("api-key-link").value.trim() || defaultState.apiKeyLink;
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
    byId("voice-id").value = state.voiceId || "";
    byId("model").value = state.model || defaultState.model;
    byId("format").value = state.format || defaultState.format;
    byId("stability").value = String(state.stability ?? 0.5);
    byId("similarity").value = String(state.similarity ?? 0.75);
    byId("style").value = String(state.style ?? 0);
    byId("stability-value").textContent = Number(state.stability ?? 0.5).toFixed(2);
    byId("similarity-value").textContent = Number(state.similarity ?? 0.75).toFixed(2);
    byId("style-value").textContent = Number(state.style ?? 0).toFixed(2);
    byId("speaker-boost").checked = state.speakerBoost !== false;
    byId("clear-after").checked = Boolean(state.clearAfter);
    byId("api-key-link").value = state.apiKeyLink || defaultState.apiKeyLink;
  }

  function renderAccount() {
    const account = currentAccount();
    byId("account-dot").classList.toggle("active", Boolean(state.currentKey));
    byId("account-name").textContent = account?.alias || (state.currentKey ? "未命名账号" : "未配置账号");
    byId("account-quota").textContent = quotaText(account);
    const select = byId("account-select");
    select.innerHTML = "";
    if (!state.accounts.length) {
      select.innerHTML = "<option value=''>暂无账号</option>";
    } else {
      state.accounts.forEach((item, index) => {
        const option = document.createElement("option");
        option.value = item.key;
        option.textContent = (item.alias || "账号 " + (index + 1)) + " · " + quotaText(item);
        select.appendChild(option);
      });
      select.value = state.currentKey || state.accounts[0]?.key || "";
    }
    if (account && typeof account.quota_left === "number") {
      state.currentQuota = account.quota_left;
      state.currentLimit = account.quota_limit ?? 0;
    }
    renderKeys();
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

  function renderKeys() {
    const list = byId("key-list");
    list.innerHTML = "";
    if (!state.accounts.length) {
      list.innerHTML = `<div class="sc-note">暂无账号。添加 API Key 后会自动保存。</div>`;
      return;
    }
    state.accounts.forEach((account, index) => {
      const item = document.createElement("div");
      item.className = "sc-key" + (account.key === state.currentKey ? " active" : "");
      item.innerHTML = `
        <div><strong>${escapeHtml(account.alias || `账号 ${index + 1}`)}</strong><div class="sc-note">**** ${escapeHtml(account.key.slice(-4))}</div></div>
        <span class="sc-note">${quotaText(account)}</span>
        <button class="sc-button danger">删除</button>
      `;
      item.addEventListener("click", (event) => {
        if (event.target.tagName === "BUTTON") return;
        switchAccount(account.key);
      });
      item.querySelector("button").addEventListener("click", () => {
        state.accounts.splice(index, 1);
        if (state.currentKey === account.key) state.currentKey = state.accounts[0]?.key || "";
        renderAccount();
        persist();
      });
      list.appendChild(item);
    });
  }

  function renderStats() {
    const total = state.cards.reduce((sum, text) => sum + (text || "").length, 0);
    const segments = state.cards.filter((text) => text.trim()).length;
    const quota = typeof state.currentQuota === "number" ? " · 生成后剩余 " + (state.currentQuota - total).toLocaleString() + " 字" : "";
    byId("stats").textContent = total.toLocaleString() + " 字 · " + segments + " 段" + quota;
  }

  function renderAll() {
    renderControls();
    renderAccount();
    renderVoices();
    renderCards();
  }

  function addOrSwitchAccount(alias, key) {
    const cleanKey = key.trim();
    if (!cleanKey) {
      setStatus("请先输入 API Key", true);
      return;
    }
    const existing = state.accounts.find((item) => item.key === cleanKey);
    if (existing) {
      if (alias.trim()) existing.alias = alias.trim();
    } else {
      state.accounts.push({ alias: alias.trim() || "账号 " + (state.accounts.length + 1), key: cleanKey });
    }
    switchAccount(cleanKey, false);
    persist();
    bridge?.checkQuota(cleanKey);
    bridge?.refreshVoices(cleanKey);
  }

  function switchAccount(key, shouldPersist = true) {
    state.currentKey = key;
    renderAccount();
    if (shouldPersist) persist();
    if (bridge && key) {
      setStatus("正在刷新账号信息...");
      bridge.checkQuota(key);
      bridge.refreshVoices(key);
    }
  }

  function setProgress(value) {
    byId("progress").style.width = Math.max(0, Math.min(100, value)) + "%";
  }

  function generate() {
    if (!bridge) return;
    collectControls();
    const segments = state.cards.map((text) => text.trim()).filter(Boolean);
    bridge.generate(JSON.stringify({ ...state, segments }));
  }

  function onBridgeEvent(raw) {
    const event = parseJson(raw, {});
    if (event.type === "status") setStatus(event.message || "");
    if (event.type === "error") {
      setStatus(event.message || "操作失败", true);
      byId("log-line").textContent = event.message || "";
      byId("generate").disabled = false;
    }
    if (event.type === "voices") {
      state.voices = event.voices || [];
      renderVoices();
    }
    if (event.type === "quota" && event.key) {
      const account = state.accounts.find((item) => item.key === event.key);
      if (account) {
        account.quota_left = event.left;
        account.quota_limit = event.limit;
      }
      if (event.key === state.currentKey) {
        state.currentQuota = event.left ?? null;
        state.currentLimit = event.limit ?? null;
      }
      renderAccount();
      persist();
    }
    if (event.type === "generationStart") {
      byId("generate").disabled = true;
      setProgress(0);
      setStatus("开始生成 " + (event.total || 0) + " 段...");
    }
    if (event.type === "progress") {
      setProgress(event.value || 0);
      setStatus(event.message || "");
    }
    if (event.type === "log") byId("log-line").textContent = event.message || "";
    if (event.type === "generated") {
      state.outputDir = event.outputDir || state.outputDir;
      byId("output-dir").value = state.outputDir;
      setProgress(100);
      setStatus("生成完成");
      if (state.clearAfter) {
        state.cards = [""];
        renderCards();
      }
      persist();
    }
    if (event.type === "generationFinished") byId("generate").disabled = false;
  }

  function normalizeImportedState(source) {
    if (!source || typeof source !== "object") return {};
    if (typeof source.elevenlabs_tool === "object") return normalizeImportedState(source.elevenlabs_tool);
    return source;
  }

  function wireUi() {
    byId("open-settings").addEventListener("click", () => byId("settings-modal").classList.add("open"));
    byId("manage-accounts").addEventListener("click", () => byId("settings-modal").classList.add("open"));
    byId("close-settings").addEventListener("click", () => byId("settings-modal").classList.remove("open"));
    byId("account-select").addEventListener("change", () => {
      const key = byId("account-select").value;
      if (key) switchAccount(key);
    });
    byId("quick-add").addEventListener("click", () => {
      addOrSwitchAccount("", byId("quick-key").value);
      byId("quick-key").value = "";
    });
    byId("quick-key").addEventListener("keydown", (event) => {
      if (event.key === "Enter") byId("quick-add").click();
    });
    byId("open-key-link").addEventListener("click", () => {
      collectControls();
      persist();
      bridge?.openExternalUrl(state.apiKeyLink);
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
    byId("refresh-voices").addEventListener("click", () => bridge?.refreshVoices(state.currentKey));
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
    byId("new-key-save").addEventListener("click", () => {
      addOrSwitchAccount(byId("new-alias").value, byId("new-key").value);
      byId("new-alias").value = "";
      byId("new-key").value = "";
    });
    byId("quota-all").addEventListener("click", () => bridge?.checkAllQuotas(JSON.stringify(state.accounts)));
    byId("import-keys").addEventListener("click", () => bridge?.importAccountsCsv((raw) => {
      const result = parseJson(raw, {});
      let added = 0;
      for (const account of result.accounts || []) {
        if (account.key && !state.accounts.some((item) => item.key === account.key)) {
          state.accounts.push(account);
          added += 1;
        }
      }
      if (!state.currentKey && state.accounts.length) state.currentKey = state.accounts[0].key;
      renderAccount();
      persist();
      setStatus(added ? "已导入 " + added + " 个账号" : result.message || "没有新账号");
    }));
    byId("export-keys").addEventListener("click", () => bridge?.exportAccountsCsv(JSON.stringify(state.accounts), (raw) => {
      setStatus(parseJson(raw, {}).message || "");
    }));
    byId("backup-config").addEventListener("click", () => bridge?.exportConfig(JSON.stringify(state), (raw) => {
      setStatus(parseJson(raw, {}).message || "");
    }));
    byId("restore-config").addEventListener("click", () => bridge?.importConfig((raw) => {
      const result = parseJson(raw, {});
      Object.assign(state, normalizeImportedState(result.state || {}));
      renderAll();
      persist();
      setStatus(result.message || "");
    }));

    ["output-dir", "voice-id", "model", "format", "stability", "similarity", "style", "speaker-boost", "clear-after", "api-key-link"]
      .forEach((id) => byId(id).addEventListener("input", () => {
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

  connectQtBridge("elevenlabsBridge")
    .then((connectedBridge) => {
      bridge = connectedBridge;
      byId("ready-pill").textContent = "已连接";
      bridge.event.connect(onBridgeEvent);
      bridge.getState((raw) => {
        Object.assign(state, defaultState, parseJson(raw, {}));
        if (!state.cards.length) state.cards = [""];
        renderAll();
        if (state.currentKey) {
          bridge?.checkQuota(state.currentKey);
          bridge?.refreshVoices(state.currentKey);
        }
      });
    })
    .catch(() => {
      byId("ready-pill").textContent = "离线预览";
      setStatus("Qt Bridge 未连接，当前是前端预览模式", true);
    });
})();
