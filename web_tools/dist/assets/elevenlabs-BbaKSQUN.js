import{n as e,t}from"./qwebchannel-DKbEaRWz.js";var n={accounts:[],currentKey:``,voiceId:``,model:`eleven_multilingual_v2`,format:`mp3_44100_128`,outputDir:``,stability:.5,similarity:.75,style:0,speakerBoost:!0,clearAfter:!1,splitMode:0,apiKeyLink:`https://elevenlabs.io/app/settings/api-keys`,cards:[``],voices:[]},r=null,i=0,a={...n,currentQuota:null,currentLimit:null},o=document.querySelector(`#app`);if(!o)throw Error(`Missing #app`);o.innerHTML=`
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
`;function s(e){let t=document.getElementById(e);if(!t)throw Error(`Missing element: ${e}`);return t}function c(e){return String(e??``).replace(/[&<>"']/g,e=>({"&":`&amp;`,"<":`&lt;`,">":`&gt;`,'"':`&quot;`,"'":`&#039;`})[e]??e)}function l(e){let t=e.replace(/\r\n/g,`
`).replace(/\r/g,`
`);return!t.includes(`	`)&&!t.includes(`
`)?[]:t.split(/\t|\n/).map(e=>e.trim()).filter(Boolean)}function u(e,t){let n=l(e.clipboardData?.getData(`text/plain`)||``);if(n.length<=1)return;e.preventDefault();let r=a.cards.slice(0,t),i=a.cards.slice(t+1);a.cards=i.every(e=>!e.trim())?[...r,...n]:[...r,...n,...i],b(),h(),p(`已按表格内容拆成 ${n.length} 段`)}function d(){return a.accounts.find(e=>e.key===a.currentKey)??null}function f(e){return!e||typeof e.quota_left!=`number`?`未查询额度`:`剩余 ${e.quota_left.toLocaleString()} 字`}function p(e,t=!1){let n=s(`status`);n.textContent=e||`就绪`,n.style.color=t?`var(--danger)`:`var(--muted)`}function m(){a.outputDir=s(`output-dir`).value.trim(),a.voiceId=s(`voice-id`).value.trim()||s(`voice-select`).value||a.voiceId,a.model=s(`model`).value,a.format=s(`format`).value,a.stability=Number(s(`stability`).value),a.similarity=Number(s(`similarity`).value),a.style=Number(s(`style`).value),a.speakerBoost=s(`speaker-boost`).checked,a.clearAfter=s(`clear-after`).checked,a.apiKeyLink=s(`api-key-link`).value.trim()||n.apiKeyLink}function h(){r&&(m(),r.saveState(JSON.stringify(a)))}function g(){window.clearTimeout(i),i=window.setTimeout(h,280)}function _(){s(`output-dir`).value=a.outputDir||``,s(`voice-id`).value=a.voiceId||``,s(`model`).value=a.model||n.model,s(`format`).value=a.format||n.format,s(`stability`).value=String(a.stability??.5),s(`similarity`).value=String(a.similarity??.75),s(`style`).value=String(a.style??0),s(`stability-value`).textContent=Number(a.stability??.5).toFixed(2),s(`similarity-value`).textContent=Number(a.similarity??.75).toFixed(2),s(`style-value`).textContent=Number(a.style??0).toFixed(2),s(`speaker-boost`).checked=a.speakerBoost!==!1,s(`clear-after`).checked=!!a.clearAfter,s(`api-key-link`).value=a.apiKeyLink||n.apiKeyLink}function v(){let e=d();s(`account-dot`).classList.toggle(`active`,!!a.currentKey),s(`account-name`).textContent=e?.alias||(a.currentKey?`未命名账号`:`未配置账号`),s(`account-quota`).textContent=f(e);let t=s(`account-select`);t.innerHTML=``,a.accounts.length?(a.accounts.forEach((e,n)=>{let r=document.createElement(`option`);r.value=e.key,r.textContent=`${e.alias||`账号 ${n+1}`} · ${f(e)}`,t.appendChild(r)}),t.value=a.currentKey||a.accounts[0]?.key||``):t.innerHTML=`<option value=''>暂无账号</option>`,e&&typeof e.quota_left==`number`&&(a.currentQuota=e.quota_left,a.currentLimit=e.quota_limit??0),x(),S()}function y(){let e=s(`voice-select`);e.innerHTML=``;let t=a.voices||[];if(!t.length){e.innerHTML=`<option value=''>请先刷新声音</option>`;return}t.slice().sort((e,t)=>(e.name||``).localeCompare(t.name||``)).forEach(t=>{let n=document.createElement(`option`);n.value=t.voice_id||``,n.textContent=t.category?`${t.name} · ${t.category}`:t.name||`Unnamed`,e.appendChild(n)}),a.voiceId&&[...e.options].some(e=>e.value===a.voiceId)&&(e.value=a.voiceId,s(`voice-id`).value=``)}function b(){let e=s(`card-list`);e.innerHTML=``,a.cards.length||(a.cards=[``]),a.cards.forEach((t,n)=>{let r=document.createElement(`section`);r.className=`sc-editor-card`,r.innerHTML=`
      <textarea class="sc-textarea" placeholder="输入第 ${n+1} 段文案">${c(t)}</textarea>
      <footer><span>段落 ${n+1} · <b>${t.length}</b> 字</span><button class="sc-button danger">删除</button></footer>
    `;let i=r.querySelector(`textarea`),o=r.querySelector(`b`);i.addEventListener(`paste`,e=>u(e,n)),i.addEventListener(`input`,()=>{a.cards[n]=i.value,o.textContent=String(i.value.length),S(),g()}),r.querySelector(`button`)?.addEventListener(`click`,()=>{a.cards.splice(n,1),a.cards.length||(a.cards=[``]),b(),h()}),e.appendChild(r)}),S()}function x(){let e=s(`key-list`);if(e.innerHTML=``,!a.accounts.length){e.innerHTML=`<div class="sc-note">暂无账号。添加 API Key 后会自动保存。</div>`;return}a.accounts.forEach((t,n)=>{let r=document.createElement(`div`);r.className=`sc-key${t.key===a.currentKey?` active`:``}`,r.innerHTML=`
      <div><strong>${c(t.alias||`账号 ${n+1}`)}</strong><div class="sc-note">**** ${c(t.key.slice(-4))}</div></div>
      <span class="sc-note">${f(t)}</span>
      <button class="sc-button danger">删除</button>
    `,r.addEventListener(`click`,e=>{e.target.tagName!==`BUTTON`&&T(t.key)}),r.querySelector(`button`)?.addEventListener(`click`,()=>{a.accounts.splice(n,1),a.currentKey===t.key&&(a.currentKey=a.accounts[0]?.key||``),v(),h()}),e.appendChild(r)})}function S(){let e=a.cards.reduce((e,t)=>e+(t||``).length,0),t=a.cards.filter(e=>e.trim()).length,n=typeof a.currentQuota==`number`?` · 生成后剩余 ${(a.currentQuota-e).toLocaleString()} 字`:``;s(`stats`).textContent=`${e.toLocaleString()} 字 · ${t} 段${n}`}function C(){_(),v(),y(),b()}function w(e,t){let n=t.trim();if(!n){p(`请先输入 API Key`,!0);return}let i=a.accounts.find(e=>e.key===n);i?e.trim()&&(i.alias=e.trim()):a.accounts.push({alias:e.trim()||`账号 ${a.accounts.length+1}`,key:n}),T(n,!1),h(),r?.checkQuota(n),r?.refreshVoices(n)}function T(e,t=!0){a.currentKey=e,v(),t&&h(),r&&e&&(p(`正在刷新账号信息...`),r.checkQuota(e),r.refreshVoices(e))}function E(e){s(`progress`).style.width=`${Math.max(0,Math.min(100,e))}%`}function D(){if(!r)return;m();let e=a.cards.map(e=>e.trim()).filter(Boolean);r.generate(JSON.stringify({...a,segments:e}))}function O(t){let n=e(t,{});if(n.type===`status`&&p(n.message||``),n.type===`error`&&(p(n.message||`操作失败`,!0),s(`log-line`).textContent=n.message||``,s(`generate`).disabled=!1),n.type===`voices`&&(a.voices=n.voices||[],y()),n.type===`quota`&&n.key){let e=a.accounts.find(e=>e.key===n.key);e&&(e.quota_left=n.left,e.quota_limit=n.limit),n.key===a.currentKey&&(a.currentQuota=n.left??null,a.currentLimit=n.limit??null),v(),h()}n.type===`generationStart`&&(s(`generate`).disabled=!0,E(0),p(`开始生成 ${n.total||0} 段...`)),n.type===`progress`&&(E(n.value||0),p(n.message||``)),n.type===`log`&&(s(`log-line`).textContent=n.message||``),n.type===`generated`&&(a.outputDir=n.outputDir||a.outputDir,s(`output-dir`).value=a.outputDir,E(100),p(`生成完成`),a.clearAfter&&(a.cards=[``],b()),h()),n.type===`generationFinished`&&(s(`generate`).disabled=!1)}function k(e){let t=e;return!t||typeof t!=`object`?{}:typeof t.elevenlabs_tool==`object`?k(t.elevenlabs_tool):t}function A(){s(`open-settings`).addEventListener(`click`,()=>s(`settings-modal`).classList.add(`open`)),s(`manage-accounts`).addEventListener(`click`,()=>s(`settings-modal`).classList.add(`open`)),s(`close-settings`).addEventListener(`click`,()=>s(`settings-modal`).classList.remove(`open`)),s(`account-select`).addEventListener(`change`,()=>{let e=s(`account-select`).value;e&&T(e)}),s(`quick-add`).addEventListener(`click`,()=>{w(``,s(`quick-key`).value),s(`quick-key`).value=``}),s(`quick-key`).addEventListener(`keydown`,e=>{e.key===`Enter`&&s(`quick-add`).click()}),s(`open-key-link`).addEventListener(`click`,()=>{m(),h(),r?.openExternalUrl(a.apiKeyLink)}),s(`pick-output`).addEventListener(`click`,()=>r?.selectOutputDir(e=>{e&&(a.outputDir=e,s(`output-dir`).value=e,h())})),s(`open-output`).addEventListener(`click`,()=>{m(),r?.openOutputDir(a.outputDir)}),s(`refresh-voices`).addEventListener(`click`,()=>r?.refreshVoices(a.currentKey)),s(`add-card`).addEventListener(`click`,()=>{a.cards.push(``),b(),h()}),s(`clear-cards`).addEventListener(`click`,()=>{a.cards=[``],b(),h()}),s(`generate`).addEventListener(`click`,D),s(`new-key-save`).addEventListener(`click`,()=>{w(s(`new-alias`).value,s(`new-key`).value),s(`new-alias`).value=``,s(`new-key`).value=``}),s(`quota-all`).addEventListener(`click`,()=>r?.checkAllQuotas(JSON.stringify(a.accounts))),s(`import-keys`).addEventListener(`click`,()=>r?.importAccountsCsv(t=>{let n=e(t,{}),r=0;for(let e of n.accounts||[])e.key&&!a.accounts.some(t=>t.key===e.key)&&(a.accounts.push(e),r+=1);!a.currentKey&&a.accounts.length&&(a.currentKey=a.accounts[0].key),v(),h(),p(r?`已导入 ${r} 个账号`:n.message||`没有新账号`)})),s(`export-keys`).addEventListener(`click`,()=>r?.exportAccountsCsv(JSON.stringify(a.accounts),t=>{p(e(t,{}).message||``)})),s(`backup-config`).addEventListener(`click`,()=>r?.exportConfig(JSON.stringify(a),t=>{p(e(t,{}).message||``)})),s(`restore-config`).addEventListener(`click`,()=>r?.importConfig(t=>{let n=e(t,{});Object.assign(a,k(n.state||{})),C(),h(),p(n.message||``)})),[`output-dir`,`voice-id`,`model`,`format`,`stability`,`similarity`,`style`,`speaker-boost`,`clear-after`,`api-key-link`].forEach(e=>s(e).addEventListener(`input`,()=>{(e===`stability`||e===`similarity`||e===`style`)&&(s(`${e}-value`).textContent=Number(s(e).value).toFixed(2)),g()})),s(`voice-select`).addEventListener(`change`,()=>{a.voiceId=s(`voice-select`).value,s(`voice-id`).value=``,h()})}A(),C(),t(`elevenlabsBridge`).then(t=>{r=t,s(`ready-pill`).textContent=`已连接`,r.event.connect(O),r.getState(t=>{Object.assign(a,n,e(t,{})),a.cards.length||(a.cards=[``]),C(),a.currentKey&&(r?.checkQuota(a.currentKey),r?.refreshVoices(a.currentKey))})}).catch(()=>{s(`ready-pill`).textContent=`离线预览`,p(`Qt Bridge 未连接，当前是前端预览模式`,!0)});