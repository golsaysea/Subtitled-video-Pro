import{n as e,t}from"./qwebchannel-DKbEaRWz.js";var n={accounts:[],currentToken:``,voiceId:``,model:`eleven_flash_v2_5`,outputDir:``,subFolder:`批量导出`,stability:.5,similarity:.75,style:0,speakerBoost:!0,compatMode:!0,autoDelete:!0,cards:[``],voices:[]},r=null,i=0,a={...n},o=document.querySelector(`#app`);if(!o)throw Error(`Missing #app`);o.innerHTML=`
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
`;function s(e){let t=document.getElementById(e);if(!t)throw Error(`Missing element: ${e}`);return t}function c(e){return String(e??``).replace(/[&<>"']/g,e=>({"&":`&amp;`,"<":`&lt;`,">":`&gt;`,'"':`&quot;`,"'":`&#039;`})[e]??e)}function l(e){let t=e.replace(/\r\n/g,`
`).replace(/\r/g,`
`);return!t.includes(`	`)&&!t.includes(`
`)?[]:t.split(/\t|\n/).map(e=>e.trim()).filter(Boolean)}function u(e,t){let n=l(e.clipboardData?.getData(`text/plain`)||``);if(n.length<=1)return;e.preventDefault();let r=a.cards.slice(0,t),i=a.cards.slice(t+1);a.cards=i.every(e=>!e.trim())?[...r,...n]:[...r,...n,...i],b(),h(),p(`已按表格内容拆成 ${n.length} 段`)}function d(){return a.accounts.find(e=>e.token===a.currentToken)??null}function f(e){return!e||typeof e.left!=`number`?`未查询额度`:`剩余 ${e.left.toLocaleString()} / ${(e.total||0).toLocaleString()} 字`}function p(e,t=!1){let n=s(`status`);n.textContent=e||`就绪`,n.style.color=t?`var(--danger)`:`var(--muted)`}function m(){a.outputDir=s(`output-dir`).value.trim(),a.subFolder=s(`sub-folder`).value.trim()||`批量导出`,a.voiceId=s(`voice-id`).value.trim()||s(`voice-select`).value||a.voiceId,a.model=s(`model`).value,a.stability=Number(s(`stability`).value),a.similarity=Number(s(`similarity`).value),a.style=Number(s(`style`).value),a.speakerBoost=s(`speaker-boost`).checked,a.compatMode=s(`compat-mode`).checked,a.autoDelete=s(`auto-delete`).checked}function h(){r&&(m(),r.saveState(JSON.stringify(a)))}function g(){window.clearTimeout(i),i=window.setTimeout(h,280)}function _(){s(`output-dir`).value=a.outputDir||``,s(`sub-folder`).value=a.subFolder||`批量导出`,s(`voice-id`).value=a.voiceId||``,s(`model`).value=a.model||n.model,s(`stability`).value=String(a.stability??.5),s(`similarity`).value=String(a.similarity??.75),s(`style`).value=String(a.style??0),s(`stability-value`).textContent=Number(a.stability??.5).toFixed(2),s(`similarity-value`).textContent=Number(a.similarity??.75).toFixed(2),s(`style-value`).textContent=Number(a.style??0).toFixed(2),s(`speaker-boost`).checked=a.speakerBoost!==!1,s(`compat-mode`).checked=a.compatMode!==!1,s(`auto-delete`).checked=a.autoDelete!==!1}function v(){let e=d();s(`account-dot`).classList.toggle(`active`,!!a.currentToken),s(`account-name`).textContent=e?.alias||(a.currentToken?`网页账号`:`未授权`),s(`account-quota`).textContent=f(e);let t=s(`account-select`);t.innerHTML=``,a.accounts.length?(a.accounts.forEach((e,n)=>{let r=document.createElement(`option`);r.value=e.token,r.textContent=`${e.alias||`网页账号 ${n+1}`} · ${f(e)}`,t.appendChild(r)}),t.value=a.currentToken||a.accounts[0]?.token||``):t.innerHTML=`<option value=''>暂无授权账号</option>`;let n=s(`token-list`);n.innerHTML=``,a.accounts.length?a.accounts.forEach((e,t)=>{let r=document.createElement(`div`);r.className=`sc-key${e.token===a.currentToken?` active`:``}`,r.innerHTML=`
        <div><strong>${c(e.alias||`网页账号 ${t+1}`)}</strong><div class="sc-note">**** ${c(e.token.slice(-6))}</div></div>
        <span class="sc-note">${f(e)}</span>
        <button class="sc-button danger">删除</button>
      `,r.addEventListener(`click`,t=>{t.target.tagName!==`BUTTON`&&C(e.token)}),r.querySelector(`button`)?.addEventListener(`click`,()=>{a.accounts.splice(t,1),a.currentToken===e.token&&(a.currentToken=a.accounts[0]?.token||``),v(),h()}),n.appendChild(r)}):n.innerHTML=`<div class="sc-note">暂无授权账号。点击“网页登录并自动授权”后保存。</div>`,x()}function y(){let e=s(`voice-select`);e.innerHTML=``;let t=a.voices||[];if(!t.length){e.innerHTML=`<option value=''>请先刷新声音</option>`;return}t.slice().sort((e,t)=>(e.name||``).localeCompare(t.name||``)).forEach(t=>{let n=document.createElement(`option`);n.value=t.voice_id||``,n.textContent=t.category?`${t.name} · ${t.category}`:t.name||`Unnamed`,e.appendChild(n)}),a.voiceId&&[...e.options].some(e=>e.value===a.voiceId)&&(e.value=a.voiceId,s(`voice-id`).value=``)}function b(){let e=s(`card-list`);e.innerHTML=``,a.cards.length||(a.cards=[``]),a.cards.forEach((t,n)=>{let r=document.createElement(`section`);r.className=`sc-editor-card`,r.innerHTML=`
      <textarea class="sc-textarea" placeholder="输入第 ${n+1} 段文案">${c(t)}</textarea>
      <footer><span>段落 ${n+1} · <b>${t.length}</b> 字</span><button class="sc-button danger">删除</button></footer>
    `;let i=r.querySelector(`textarea`),o=r.querySelector(`b`);i.addEventListener(`paste`,e=>u(e,n)),i.addEventListener(`input`,()=>{a.cards[n]=i.value,o.textContent=String(i.value.length),x(),g()}),r.querySelector(`button`)?.addEventListener(`click`,()=>{a.cards.splice(n,1),a.cards.length||(a.cards=[``]),b(),h()}),e.appendChild(r)}),x()}function x(){let e=a.cards.reduce((e,t)=>e+(t||``).length,0),t=a.cards.filter(e=>e.trim()).length;s(`stats`).textContent=`${e.toLocaleString()} 字 · ${t} 段`}function S(){_(),v(),y(),b()}function C(e,t=!0){a.currentToken=e,v(),t&&h(),r&&e&&(p(`正在刷新授权账号...`),r.checkQuota(e),r.refreshVoices(e))}function w(e){s(`progress`).style.width=`${Math.max(0,Math.min(100,e))}%`}function T(t){let n=e(t,{});if(n.type===`status`&&p(n.message||``),n.type===`error`&&(p(n.message||`操作失败`,!0),s(`log-line`).textContent=n.message||``,s(`generate`).disabled=!1,n.popup&&window.alert(n.message||`操作失败`)),n.type===`capturedToken`&&n.token&&(a.accounts.some(e=>e.token===n.token)||a.accounts.push({alias:`网页账号 ${a.accounts.length+1}`,token:n.token}),C(n.token,!1),h()),n.type===`voices`&&(a.voices=n.voices||[],y()),n.type===`quota`&&n.token){let e=a.accounts.find(e=>e.token===n.token);e&&(e.left=n.left,e.total=n.total),v(),h()}n.type===`progress`&&(w(n.value||0),p(n.message||``)),n.type===`log`&&(s(`log-line`).textContent=n.message||``),n.type===`generationStart`&&(s(`generate`).disabled=!0,w(0),p(`开始生成...`)),n.type===`generated`&&(a.outputDir=n.outputDir||a.outputDir,s(`output-dir`).value=a.outputDir,w(100),p(`生成完成`),a.autoDelete&&(a.cards=[``],b()),h()),n.type===`generationFinished`&&(s(`generate`).disabled=!1)}function E(){if(!r)return;m();let e=a.cards.map(e=>e.trim()).filter(Boolean);r.generate(JSON.stringify({...a,segments:e}))}function D(){s(`open-settings`).addEventListener(`click`,()=>s(`settings-modal`).classList.add(`open`)),s(`close-settings`).addEventListener(`click`,()=>s(`settings-modal`).classList.remove(`open`)),s(`capture-token`).addEventListener(`click`,()=>r?.openTokenCapture()),s(`official-generator`).addEventListener(`click`,()=>r?.openOfficialGenerator()),s(`capture-token-modal`).addEventListener(`click`,()=>r?.openTokenCapture()),s(`account-select`).addEventListener(`change`,()=>{let e=s(`account-select`).value;e&&C(e)}),s(`pick-output`).addEventListener(`click`,()=>r?.selectOutputDir(e=>{e&&(a.outputDir=e,s(`output-dir`).value=e,h())})),s(`open-output`).addEventListener(`click`,()=>{m(),r?.openOutputDir(a.outputDir)}),s(`refresh-voices`).addEventListener(`click`,()=>r?.refreshVoices(a.currentToken)),s(`add-card`).addEventListener(`click`,()=>{a.cards.push(``),b(),h()}),s(`clear-cards`).addEventListener(`click`,()=>{a.cards=[``],b(),h()}),s(`generate`).addEventListener(`click`,E),s(`stop`).addEventListener(`click`,()=>r?.stopGeneration()),[`output-dir`,`sub-folder`,`voice-id`,`model`,`stability`,`similarity`,`style`,`speaker-boost`,`compat-mode`,`auto-delete`].forEach(e=>s(e).addEventListener(`input`,()=>{(e===`stability`||e===`similarity`||e===`style`)&&(s(`${e}-value`).textContent=Number(s(e).value).toFixed(2)),g()})),s(`voice-select`).addEventListener(`change`,()=>{a.voiceId=s(`voice-select`).value,s(`voice-id`).value=``,h()})}D(),S(),t(`elevenAssistBridge`).then(t=>{r=t,s(`ready-pill`).textContent=`已连接`,r.event.connect(T),r.getState(t=>{Object.assign(a,n,e(t,{})),a.cards.length||(a.cards=[``]),S(),a.currentToken&&(r.checkQuota(a.currentToken),r.refreshVoices(a.currentToken))})}).catch(()=>{s(`ready-pill`).textContent=`离线预览`,p(`Qt Bridge 未连接，当前是前端预览模式`,!0)});