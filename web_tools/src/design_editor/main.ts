import Konva from "konva";
import "../shared/theme.css";
import { connectQtBridge, parseJson, type BridgeSignal } from "../shared/qwebchannel";

type DesignLayer = {
  id: string;
  type: "text" | "rect" | "image";
  name: string;
  text?: string;
  src?: string;
  fit?: "cover" | "contain" | "stretch";
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string;
  fill?: string;
  background?: string;
  cornerRadius?: number;
  align?: "left" | "center" | "right";
  opacity?: number;
  start?: number;
  end?: number;
  zIndex?: number;
  shadow?: boolean;
};

type DesignPage = {
  id: string;
  name: string;
  duration: number;
  layers: DesignLayer[];
};

type DesignState = {
  version: number;
  width: number;
  height: number;
  pages: DesignPage[];
};

type DesignBridge = {
  event: BridgeSignal;
  getState: (callback: (raw: string) => void) => void;
  saveState: (payload: string) => void;
};

type AssetKind =
  | "title"
  | "body"
  | "prayer"
  | "rect"
  | "highlight"
  | "lower-third"
  | "quote-card"
  | "divider";

type TimelineDrag = {
  layerId: string;
  mode: "move" | "start" | "end";
  originX: number;
  originStart: number;
  originEnd: number;
  duration: number;
  laneWidth: number;
};

declare global {
  interface Window {
    designEditorSetState?: (payload: string) => void;
  }
}

const defaultState: DesignState = {
  version: 1,
  width: 1080,
  height: 1920,
  pages: [
    {
      id: "page-1",
      name: "页面 1",
      duration: 5,
      layers: []
    }
  ]
};

let bridge: DesignBridge | null = null;
function cloneDesign<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

let state: DesignState = cloneDesign(defaultState);
let currentPageIndex = 0;
let selectedLayerId = "";
let saveTimer = 0;
let stageScale = 0.5;
let timelineDrag: TimelineDrag | null = null;

const imageCache = new Map<string, HTMLImageElement | "loading" | "error">();

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("Missing #app");

app.innerHTML = `
  <div class="design-room">
    <aside class="design-panel design-left">
      <div class="design-brand">
        <strong>Design Room</strong>
        <span>素材 / 模板 / 页面</span>
      </div>
      <div class="design-tabs" role="tablist">
        <button class="design-tab active" data-tab="assets" type="button">素材</button>
        <button class="design-tab" data-tab="templates" type="button">模板</button>
      </div>
      <section class="design-pane active" data-pane="assets">
        <label class="design-label">常用素材</label>
        <div class="asset-grid">
          <button class="asset-card" data-asset="title" type="button"><strong>T</strong><span>标题</span></button>
          <button class="asset-card" data-asset="body" type="button"><strong>¶</strong><span>正文</span></button>
          <button class="asset-card" data-asset="prayer" type="button"><strong>“</strong><span>祷告词</span></button>
          <button class="asset-card" data-asset="rect" type="button"><strong>■</strong><span>色块</span></button>
          <button class="asset-card" data-asset="highlight" type="button"><strong>▰</strong><span>强调条</span></button>
          <button class="asset-card" data-asset="lower-third" type="button"><strong>▤</strong><span>下三分之一</span></button>
          <button class="asset-card" data-asset="quote-card" type="button"><strong>□</strong><span>引用卡片</span></button>
          <button class="asset-card" data-asset="divider" type="button"><strong>—</strong><span>分隔线</span></button>
        </div>
        <div class="design-divider"></div>
        <section class="design-section">
          <label>图片素材 URL</label>
          <input id="image-url" placeholder="https://... 或 file:///..." />
          <button id="add-image" type="button">添加图片</button>
        </section>
      </section>
      <section class="design-pane" data-pane="templates">
        <button id="tpl-title" class="design-primary" type="button">标题页模板</button>
        <button id="tpl-prayer" type="button">祷告词模板</button>
        <button id="tpl-verse" type="button">金句模板</button>
      </section>
      <div class="design-divider"></div>
      <section class="design-section">
        <label>页面</label>
        <button id="add-page" type="button">新页面</button>
        <button id="duplicate-page" type="button">复制页面</button>
        <button id="delete-page" class="design-danger" type="button">删除页面</button>
      </section>
    </aside>
    <main class="design-main">
      <div class="design-canvas-shell">
        <div id="stage-wrap"></div>
      </div>
      <div class="design-timeline">
        <header class="timeline-head">
          <div>
            <strong>图层时长</strong>
            <span id="timeline-duration">0.0s</span>
          </div>
          <div class="duration-presets" aria-label="页面时长">
            <button type="button" data-duration="3">3s</button>
            <button type="button" data-duration="5">5s</button>
            <button type="button" data-duration="8">8s</button>
          </div>
        </header>
        <div id="timeline-ruler" class="timeline-ruler"></div>
        <div id="timeline-tracks" class="timeline-tracks"></div>
      </div>
      <div class="design-page-strip" id="page-strip"></div>
    </main>
    <aside class="design-panel design-right">
      <section class="design-section">
        <label>当前页面时长</label>
        <input id="page-duration" type="number" min="0.1" step="0.1" />
      </section>
      <section class="design-section">
        <label>图层</label>
        <div id="layer-list" class="design-layer-list"></div>
      </section>
      <section class="design-section" id="props">
        <label>选中图层属性</label>
        <input id="layer-name" placeholder="图层名" />
        <textarea id="layer-text" placeholder="文字内容"></textarea>
        <input id="layer-src" placeholder="图片地址" />
        <div class="design-grid">
          <input id="layer-start" type="number" min="0" step="0.1" title="开始时间" />
          <input id="layer-end" type="number" min="0" step="0.1" title="结束时间，0=跟随页面" />
          <input id="layer-size" type="number" min="8" step="1" title="字号" />
          <input id="layer-opacity" type="number" min="0" max="1" step="0.05" title="透明度" />
        </div>
        <div class="design-grid">
          <input id="layer-fill" type="color" title="文字/色块颜色" />
          <select id="layer-align" title="对齐">
            <option value="left">左</option>
            <option value="center">中</option>
            <option value="right">右</option>
          </select>
        </div>
        <button id="fit-page-duration" type="button">跟随页面时长</button>
        <button id="delete-layer" class="design-danger" type="button">删除图层</button>
      </section>
    </aside>
  </div>
`;

const style = document.createElement("style");
style.textContent = `
  html, body, #app { margin:0; width:100%; height:100%; overflow:hidden; background:#101113; color:#edf2f7; font-family: "Segoe UI", "Microsoft YaHei", "Noto Sans SC", Arial, sans-serif; }
  button, input, textarea, select { font: inherit; }
  button { cursor:pointer; }
  .design-room { height:100vh; min-width:0; display:grid; grid-template-columns: minmax(190px, 240px) minmax(280px, 1fr) minmax(220px, 292px); background:#101113; }
  .design-panel { min-width:0; background:#181a1f; border-color:#343a46; border-style:solid; padding:14px; box-sizing:border-box; overflow:auto; }
  .design-left { border-width:0 1px 0 0; }
  .design-right { border-width:0 0 0 1px; }
  .design-brand { display:flex; flex-direction:column; gap:3px; margin-bottom:12px; }
  .design-brand strong { color:#ffffff; font-size:18px; letter-spacing:0; }
  .design-brand span, .design-label { color:#9aa4b2; font-size:12px; line-height:1.5; }
  .design-label { display:block; margin:0 0 8px; font-weight:800; }
  button { width:100%; min-height:36px; border:1px solid #343a46; border-radius:7px; padding:8px 10px; margin:4px 0; background:#252932; color:#edf2f7; font-weight:800; }
  button:hover { background:#20232a; border-color:#4b5565; }
  .design-primary { border-color:rgba(78,163,255,0.7); background:#4ea3ff; color:#07111f; }
  .design-danger { border-color:rgba(251,113,133,0.5); color:#fb7185; }
  .design-divider { height:1px; background:#343a46; margin:12px 0; }
  .design-main { min-width:0; display:grid; grid-template-rows:minmax(0, 1fr) 150px 112px; }
  .design-canvas-shell { display:flex; align-items:center; justify-content:center; overflow:hidden; padding:18px; background:#111419; }
  #stage-wrap { background:rgba(255,255,255,0.055); box-shadow:0 18px 60px rgba(0,0,0,0.42); border:1px solid rgba(255,255,255,0.12); }
  .design-page-strip { border-top:1px solid #343a46; background:#181a1f; display:flex; align-items:center; gap:10px; overflow:auto; padding:10px 12px; box-sizing:border-box; }
  .design-page-card { width:92px; min-width:92px; height:88px; border:1px solid #343a46; border-radius:8px; background:#20232a; color:#c5ccd6; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; }
  .design-page-card span { max-width:78px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .design-page-card.active { border-color:#6ee7b7; color:#6ee7b7; box-shadow:0 0 0 2px rgba(110,231,183,0.18); }
  .design-page-card small { color:#9aa4b2; }
  .design-section { display:flex; flex-direction:column; gap:8px; margin-bottom:14px; }
  .design-section label { color:#9aa4b2; font-size:12px; font-weight:800; }
  input, textarea, select { width:100%; box-sizing:border-box; border:1px solid #343a46; background:#121419; color:#edf2f7; border-radius:7px; padding:8px; outline:none; }
  input:focus, textarea:focus, select:focus { border-color:#4ea3ff; background:#252932; }
  textarea { min-height:94px; resize:vertical; line-height:1.45; }
  .design-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .design-tabs { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px; }
  .design-tab { margin:0; }
  .design-tab.active { border-color:#4ea3ff; color:#4ea3ff; background:rgba(78,163,255,0.08); }
  .design-pane { display:none; }
  .design-pane.active { display:block; }
  .asset-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .asset-card { height:74px; margin:0; display:grid; place-items:center; gap:3px; background:#20232a; }
  .asset-card strong { font-size:22px; line-height:1; color:#6ee7b7; }
  .asset-card span { font-size:12px; color:#c5ccd6; }
  .design-layer-list { display:flex; flex-direction:column; gap:6px; }
  .design-layer { border:1px solid #343a46; border-radius:7px; padding:8px; background:#20232a; display:grid; grid-template-columns:minmax(0, 1fr) 28px 28px; gap:6px; align-items:center; }
  .design-layer.active { border-color:#6ee7b7; color:#6ee7b7; }
  .layer-title { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; }
  .layer-order { width:28px; height:28px; min-height:28px; margin:0; padding:0; }
  #props.disabled { opacity:0.45; pointer-events:none; }
  .design-timeline { min-width:0; border-top:1px solid #343a46; background:#181a1f; padding:10px 12px; overflow:hidden; }
  .timeline-head { height:28px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .timeline-head strong { font-size:13px; }
  .timeline-head span { color:#9aa4b2; margin-left:8px; font-size:12px; }
  .duration-presets { display:flex; gap:6px; }
  .duration-presets button { width:42px; min-height:28px; margin:0; padding:0; }
  .timeline-ruler { margin-left:112px; height:18px; position:relative; border-bottom:1px solid #343a46; color:#9aa4b2; font-size:10px; }
  .timeline-mark { position:absolute; bottom:2px; transform:translateX(-50%); }
  .timeline-tracks { height:84px; overflow:auto; padding-top:6px; display:flex; flex-direction:column; gap:6px; }
  .timeline-row { display:grid; grid-template-columns:104px minmax(0, 1fr); gap:8px; align-items:center; min-height:26px; }
  .timeline-name { min-width:0; color:#c5ccd6; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .timeline-row.active .timeline-name { color:#6ee7b7; }
  .timeline-lane { height:24px; position:relative; border:1px solid #343a46; border-radius:7px; background:#121419; overflow:hidden; }
  .timeline-bar { position:absolute; top:3px; bottom:3px; min-width:10px; border-radius:5px; background:#4ea3ff; box-shadow:0 0 0 1px rgba(255,255,255,0.18) inset; cursor:grab; }
  .timeline-row.active .timeline-bar { background:#6ee7b7; }
  .timeline-handle { position:absolute; top:0; bottom:0; width:7px; background:rgba(7,17,31,0.72); border:1px solid rgba(255,255,255,0.28); }
  .timeline-handle.start { left:0; cursor:w-resize; border-radius:5px 0 0 5px; }
  .timeline-handle.end { right:0; cursor:e-resize; border-radius:0 5px 5px 0; }
  .timeline-empty { color:#9aa4b2; font-size:12px; padding:8px 0 0 112px; }
  @media (max-width:1180px) {
    .design-room { grid-template-columns:minmax(180px, 220px) minmax(260px, 1fr) minmax(210px, 260px); }
    .design-main { grid-template-rows:minmax(0, 1fr) 142px 104px; }
  }
  @media (max-width:760px) {
    .design-room { grid-template-columns:180px minmax(260px, 1fr); overflow:auto; }
    .design-right { grid-column:1 / -1; border-width:1px 0 0 0; max-height:260px; }
    .design-main { min-width:360px; }
  }
`;
document.head.appendChild(style);

const stageWrap = document.querySelector<HTMLDivElement>("#stage-wrap")!;
const pageStrip = document.querySelector<HTMLDivElement>("#page-strip")!;
const layerList = document.querySelector<HTMLDivElement>("#layer-list")!;
const timelineTracks = document.querySelector<HTMLDivElement>("#timeline-tracks")!;
const timelineRuler = document.querySelector<HTMLDivElement>("#timeline-ruler")!;
const timelineDuration = document.querySelector<HTMLSpanElement>("#timeline-duration")!;
const pageDurationInput = document.querySelector<HTMLInputElement>("#page-duration")!;
const propsPanel = document.querySelector<HTMLElement>("#props")!;
const layerNameInput = document.querySelector<HTMLInputElement>("#layer-name")!;
const layerTextInput = document.querySelector<HTMLTextAreaElement>("#layer-text")!;
const layerSrcInput = document.querySelector<HTMLInputElement>("#layer-src")!;
const layerStartInput = document.querySelector<HTMLInputElement>("#layer-start")!;
const layerEndInput = document.querySelector<HTMLInputElement>("#layer-end")!;
const layerSizeInput = document.querySelector<HTMLInputElement>("#layer-size")!;
const layerOpacityInput = document.querySelector<HTMLInputElement>("#layer-opacity")!;
const layerFillInput = document.querySelector<HTMLInputElement>("#layer-fill")!;
const layerAlignInput = document.querySelector<HTMLSelectElement>("#layer-align")!;
const imageUrlInput = document.querySelector<HTMLInputElement>("#image-url")!;

const stage = new Konva.Stage({ container: "stage-wrap", width: 405, height: 720 });
const bgLayer = new Konva.Layer();
const contentLayer = new Konva.Layer();
function createTransformer(): Konva.Transformer {
  return new Konva.Transformer({
    rotateEnabled: true,
    enabledAnchors: ["top-left", "top-right", "bottom-left", "bottom-right", "middle-left", "middle-right"]
  });
}

let transformer = createTransformer();
stage.add(bgLayer);
stage.add(contentLayer);

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function normalizeState(next: DesignState): DesignState {
  const clean = next && Array.isArray(next.pages) && next.pages.length ? next : cloneDesign(defaultState);
  clean.version = Number(clean.version) || 1;
  clean.width = Math.max(1, Number(clean.width) || 1080);
  clean.height = Math.max(1, Number(clean.height) || 1920);
  clean.pages.forEach((item, pageIndex) => {
    item.id = item.id || uid("page");
    item.name = item.name || `页面 ${pageIndex + 1}`;
    item.duration = Math.max(0.1, Number(item.duration) || 5);
    item.layers = Array.isArray(item.layers) ? item.layers : [];
    item.layers.forEach((layer, layerIndex) => {
      layer.id = layer.id || uid("layer");
      layer.name = layer.name || (layer.type === "text" ? "文字" : layer.type === "image" ? "图片" : "图层");
      layer.type = layer.type === "image" || layer.type === "rect" ? layer.type : "text";
      layer.x = Number(layer.x) || 0;
      layer.y = Number(layer.y) || 0;
      layer.width = Math.max(1, Number(layer.width) || 300);
      layer.height = Math.max(1, Number(layer.height) || 80);
      layer.opacity = Math.max(0, Math.min(1, Number(layer.opacity ?? 1)));
      layer.start = Math.max(0, Number(layer.start) || 0);
      layer.end = Math.max(0, Number(layer.end) || 0);
      layer.zIndex = Number.isFinite(Number(layer.zIndex)) ? Number(layer.zIndex) : layerIndex;
    });
  });
  return clean;
}

function page(): DesignPage {
  return state.pages[currentPageIndex] ?? state.pages[0];
}

function selectedLayer(): DesignLayer | undefined {
  return page().layers.find((layer) => layer.id === selectedLayerId);
}

function sortedLayers(layers = page().layers): DesignLayer[] {
  return [...layers].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
}

function nextZIndex(): number {
  return page().layers.reduce((max, layer) => Math.max(max, Number(layer.zIndex) || 0), -1) + 1;
}

function saveSoon(): void {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    bridge?.saveState(JSON.stringify(state));
  }, 180);
}

function stageSize(): { width: number; height: number } {
  const shell = document.querySelector<HTMLDivElement>(".design-canvas-shell")!;
  const maxW = Math.max(260, shell.clientWidth - 48);
  const maxH = Math.max(360, shell.clientHeight - 48);
  const scale = Math.min(maxW / state.width, maxH / state.height);
  return { width: Math.round(state.width * scale), height: Math.round(state.height * scale) };
}

function resizeStage(): void {
  const size = stageSize();
  stage.width(size.width);
  stage.height(size.height);
  stageWrap.style.width = `${size.width}px`;
  stageWrap.style.height = `${size.height}px`;
  stageScale = size.width / state.width;
  renderStage();
}

function requestImage(src: string): HTMLImageElement | null {
  const cleanSrc = src.trim();
  if (!cleanSrc) return null;
  const cached = imageCache.get(cleanSrc);
  if (cached instanceof HTMLImageElement) return cached;
  if (cached === "loading" || cached === "error") return null;
  const img = new Image();
  imageCache.set(cleanSrc, "loading");
  img.onload = () => {
    imageCache.set(cleanSrc, img);
    renderStage();
  };
  img.onerror = () => {
    imageCache.set(cleanSrc, "error");
    renderStage();
  };
  img.src = cleanSrc;
  return null;
}

function layerToNode(layer: DesignLayer): Konva.Node {
  const attrs = {
    id: layer.id,
    x: layer.x * stageScale,
    y: layer.y * stageScale,
    width: layer.width * stageScale,
    height: layer.height * stageScale,
    rotation: layer.rotation ?? 0,
    opacity: layer.opacity ?? 1,
    draggable: true
  };
  if (layer.type === "rect") {
    return new Konva.Rect({
      ...attrs,
      fill: layer.fill ?? "#000000",
      cornerRadius: (layer.cornerRadius ?? 14) * stageScale
    });
  }
  if (layer.type === "image") {
    const image = requestImage(layer.src ?? "");
    if (image) {
      return new Konva.Image({ ...attrs, image });
    }
    return new Konva.Rect({
      ...attrs,
      fill: "#20232a",
      stroke: "#6ee7b7",
      dash: [8, 8],
      cornerRadius: 12 * stageScale
    });
  }
  return new Konva.Text({
    ...attrs,
    text: layer.text ?? "",
    fontSize: (layer.fontSize ?? 48) * stageScale,
    fontFamily: layer.fontFamily ?? "Noto Sans SC",
    fontStyle: layer.fontWeight ?? "700",
    fill: layer.fill ?? "#ffffff",
    align: layer.align ?? "center",
    lineHeight: 1.18,
    shadowColor: "rgba(0,0,0,0.75)",
    shadowBlur: layer.shadow === false ? 0 : 10 * stageScale,
    shadowOffsetY: layer.shadow === false ? 0 : 4 * stageScale
  });
}

function syncNodeToLayer(node: Konva.Node, layer: DesignLayer): void {
  layer.x = Math.round(node.x() / stageScale);
  layer.y = Math.round(node.y() / stageScale);
  layer.rotation = Math.round(node.rotation() * 10) / 10;
  layer.opacity = node.opacity();
  const width = Math.max(20, (node.width() * node.scaleX()) / stageScale);
  const height = Math.max(20, (node.height() * node.scaleY()) / stageScale);
  layer.width = Math.round(width);
  layer.height = Math.round(height);
  node.scale({ x: 1, y: 1 });
}

function editLayerText(layer: DesignLayer): void {
  if (layer.type === "text") {
    const text = prompt("文字内容", layer.text ?? "");
    if (text !== null) {
      layer.text = text;
      selectedLayerId = layer.id;
      renderAll(true);
    }
  } else if (layer.type === "image") {
    const src = prompt("图片地址", layer.src ?? "");
    if (src !== null) {
      layer.src = src.trim();
      selectedLayerId = layer.id;
      renderAll(true);
    }
  }
}

function renderStage(): void {
  bgLayer.destroyChildren();
  contentLayer.destroyChildren();
  transformer = createTransformer();
  bgLayer.add(new Konva.Rect({ x: 0, y: 0, width: stage.width(), height: stage.height(), fill: "rgba(255,255,255,0.04)" }));
  const active = page();
  for (const layer of sortedLayers(active.layers)) {
    const node = layerToNode(layer);
    node.on("click tap", () => {
      selectedLayerId = layer.id;
      renderAll(false);
    });
    node.on("dblclick dbltap", () => editLayerText(layer));
    node.on("dragend transformend", () => {
      syncNodeToLayer(node, layer);
      renderAll(true);
    });
    contentLayer.add(node);
  }
  const selectedNode = selectedLayerId ? contentLayer.findOne(`#${selectedLayerId}`) : null;
  transformer.nodes(selectedNode ? [selectedNode] : []);
  contentLayer.add(transformer);
  bgLayer.draw();
  contentLayer.draw();
}

function renderPages(): void {
  pageStrip.innerHTML = "";
  state.pages.forEach((item, idx) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `design-page-card${idx === currentPageIndex ? " active" : ""}`;
    card.innerHTML = `<strong>${idx + 1}</strong><span>${item.name}</span><small>${item.duration.toFixed(1)}s</small>`;
    card.onclick = () => {
      currentPageIndex = idx;
      selectedLayerId = "";
      renderAll(false);
    };
    card.oncontextmenu = (event) => {
      event.preventDefault();
      const action = prompt("页面操作：输入 rename / duplicate / delete", "rename");
      if (action === "rename") {
        const name = prompt("页面名称", item.name);
        if (name?.trim()) item.name = name.trim();
      } else if (action === "duplicate") {
        state.pages.splice(idx + 1, 0, cloneDesign({ ...item, id: uid("page"), name: `${item.name} 副本` }));
      } else if (action === "delete" && state.pages.length > 1) {
        state.pages.splice(idx, 1);
        currentPageIndex = Math.max(0, Math.min(currentPageIndex, state.pages.length - 1));
      }
      renderAll(true);
    };
    pageStrip.appendChild(card);
  });
}

function layerIcon(layer: DesignLayer): string {
  if (layer.type === "rect") return "■";
  if (layer.type === "image") return "▧";
  return "T";
}

function renderLayerList(): void {
  layerList.innerHTML = "";
  sortedLayers().reverse().forEach((layer) => {
    const item = document.createElement("div");
    item.className = `design-layer${layer.id === selectedLayerId ? " active" : ""}`;
    const title = document.createElement("div");
    title.className = "layer-title";
    title.textContent = `${layerIcon(layer)} ${layer.name}`;
    title.onclick = () => {
      selectedLayerId = layer.id;
      renderAll(false);
    };
    const up = document.createElement("button");
    up.type = "button";
    up.className = "layer-order";
    up.textContent = "↑";
    up.title = "上移图层";
    up.onclick = (event) => {
      event.stopPropagation();
      moveLayer(layer.id, 1);
    };
    const down = document.createElement("button");
    down.type = "button";
    down.className = "layer-order";
    down.textContent = "↓";
    down.title = "下移图层";
    down.onclick = (event) => {
      event.stopPropagation();
      moveLayer(layer.id, -1);
    };
    item.append(title, up, down);
    layerList.appendChild(item);
  });
}

function renderProps(): void {
  const layer = selectedLayer();
  propsPanel.classList.toggle("disabled", !layer);
  pageDurationInput.value = String(page().duration);
  if (!layer) {
    layerNameInput.value = "";
    layerTextInput.value = "";
    layerSrcInput.value = "";
    layerTextInput.style.display = "block";
    layerSrcInput.style.display = "none";
    return;
  }
  layerNameInput.value = layer.name;
  layerTextInput.value = layer.text ?? "";
  layerSrcInput.value = layer.src ?? "";
  layerTextInput.style.display = layer.type === "text" ? "block" : "none";
  layerSrcInput.style.display = layer.type === "image" ? "block" : "none";
  layerStartInput.value = String(layer.start ?? 0);
  layerEndInput.value = String(layer.end ?? 0);
  layerSizeInput.value = String(layer.fontSize ?? 48);
  layerSizeInput.disabled = layer.type !== "text";
  layerOpacityInput.value = String(layer.opacity ?? 1);
  layerFillInput.value = normalizeColor(layer.fill ?? (layer.type === "rect" ? "#111827" : "#ffffff"));
  layerAlignInput.value = layer.align ?? "center";
  layerAlignInput.disabled = layer.type !== "text";
}

function normalizeColor(value: string): string {
  const clean = String(value || "").trim();
  if (/^#[0-9a-f]{6}$/i.test(clean)) return clean;
  if (/^#[0-9a-f]{3}$/i.test(clean)) {
    return `#${clean[1]}${clean[1]}${clean[2]}${clean[2]}${clean[3]}${clean[3]}`;
  }
  return "#ffffff";
}

function snapTime(value: number): number {
  return Math.round(Math.max(0, value) * 10) / 10;
}

function effectiveLayerEnd(layer: DesignLayer, duration = page().duration): number {
  const start = Number(layer.start) || 0;
  const end = Number(layer.end) || 0;
  if (end <= 0) return duration;
  return Math.max(start + 0.1, Math.min(duration, end));
}

function setLayerTimes(layer: DesignLayer, start: number, end: number, duration = page().duration): void {
  const minLength = Math.min(0.2, Math.max(0.05, duration));
  const cleanStart = snapTime(Math.min(Math.max(0, start), Math.max(0, duration - minLength)));
  const cleanEnd = snapTime(Math.max(cleanStart + minLength, Math.min(duration, end)));
  layer.start = cleanStart;
  layer.end = Math.abs(cleanEnd - duration) < 0.05 ? 0 : cleanEnd;
}

function renderTimeline(): void {
  const activePage = page();
  const duration = Math.max(0.1, Number(activePage.duration) || 5);
  timelineDuration.textContent = `${duration.toFixed(1)}s`;
  timelineRuler.innerHTML = "";
  timelineTracks.innerHTML = "";
  const markCount = Math.min(8, Math.max(2, Math.ceil(duration)));
  for (let i = 0; i <= markCount; i += 1) {
    const mark = document.createElement("span");
    mark.className = "timeline-mark";
    const t = (duration * i) / markCount;
    mark.style.left = `${(i / markCount) * 100}%`;
    mark.textContent = `${t.toFixed(t < 10 ? 1 : 0)}s`;
    timelineRuler.appendChild(mark);
  }
  if (!activePage.layers.length) {
    const empty = document.createElement("div");
    empty.className = "timeline-empty";
    empty.textContent = "当前页面还没有图层";
    timelineTracks.appendChild(empty);
    return;
  }
  sortedLayers(activePage.layers).reverse().forEach((layer) => {
    const start = Math.min(duration, Number(layer.start) || 0);
    const end = effectiveLayerEnd(layer, duration);
    const row = document.createElement("div");
    row.className = `timeline-row${layer.id === selectedLayerId ? " active" : ""}`;
    const name = document.createElement("div");
    name.className = "timeline-name";
    name.textContent = `${layerIcon(layer)} ${layer.name}`;
    const lane = document.createElement("div");
    lane.className = "timeline-lane";
    const bar = document.createElement("div");
    bar.className = "timeline-bar";
    bar.style.left = `${(start / duration) * 100}%`;
    bar.style.width = `${Math.max(1, ((end - start) / duration) * 100)}%`;
    bar.title = `${start.toFixed(1)}s - ${end.toFixed(1)}s`;
    bar.onpointerdown = (event) => beginTimelineDrag(event, layer, "move", lane);
    bar.onclick = () => {
      selectedLayerId = layer.id;
      renderAll(false);
    };
    const startHandle = document.createElement("span");
    startHandle.className = "timeline-handle start";
    startHandle.onpointerdown = (event) => beginTimelineDrag(event, layer, "start", lane);
    const endHandle = document.createElement("span");
    endHandle.className = "timeline-handle end";
    endHandle.onpointerdown = (event) => beginTimelineDrag(event, layer, "end", lane);
    bar.append(startHandle, endHandle);
    lane.appendChild(bar);
    row.append(name, lane);
    timelineTracks.appendChild(row);
  });
}

function beginTimelineDrag(event: PointerEvent, layer: DesignLayer, mode: TimelineDrag["mode"], lane: HTMLElement): void {
  event.preventDefault();
  event.stopPropagation();
  selectedLayerId = layer.id;
  const duration = page().duration;
  timelineDrag = {
    layerId: layer.id,
    mode,
    originX: event.clientX,
    originStart: Number(layer.start) || 0,
    originEnd: effectiveLayerEnd(layer, duration),
    duration,
    laneWidth: Math.max(1, lane.getBoundingClientRect().width)
  };
  renderAll(false);
}

function renderAll(shouldSave: boolean): void {
  renderStage();
  renderPages();
  renderLayerList();
  renderProps();
  renderTimeline();
  if (shouldSave) saveSoon();
}

function textLayer(partial: Partial<DesignLayer>): DesignLayer {
  return {
    id: uid("text"),
    type: "text",
    name: "文字",
    text: "Text",
    x: 120,
    y: 420,
    width: 840,
    height: 180,
    fontSize: 54,
    fontFamily: "Noto Sans SC",
    fontWeight: "700",
    fill: "#ffffff",
    align: "center",
    opacity: 1,
    start: 0,
    end: 0,
    zIndex: nextZIndex(),
    shadow: true,
    ...partial
  };
}

function rectLayer(partial: Partial<DesignLayer>): DesignLayer {
  return {
    id: uid("rect"),
    type: "rect",
    name: "色块",
    x: 150,
    y: 780,
    width: 780,
    height: 180,
    fill: "#111827",
    opacity: 0.62,
    cornerRadius: 30,
    start: 0,
    end: 0,
    zIndex: nextZIndex(),
    ...partial
  };
}

function imageLayer(src: string): DesignLayer {
  return {
    id: uid("image"),
    type: "image",
    name: "图片素材",
    src,
    fit: "cover",
    x: 140,
    y: 520,
    width: 800,
    height: 520,
    opacity: 1,
    start: 0,
    end: 0,
    zIndex: nextZIndex()
  };
}

function addLayer(kind: AssetKind): void {
  const layers: DesignLayer[] = [];
  if (kind === "title") {
    layers.push(textLayer({ name: "标题", text: "Title", x: 96, y: 230, width: 888, height: 130, fontSize: 82, fontWeight: "800" }));
  } else if (kind === "body") {
    layers.push(textLayer({ name: "正文", text: "Body text", x: 120, y: 420, width: 840, height: 300, fontSize: 48, fontWeight: "600" }));
  } else if (kind === "prayer") {
    layers.push(textLayer({ name: "祷告词", text: "Lord, guide my heart today.", x: 120, y: 820, width: 840, height: 320, fontSize: 48, fontWeight: "600", fill: "#fff7e8" }));
  } else if (kind === "rect") {
    layers.push(rectLayer({ name: "色块" }));
  } else if (kind === "highlight") {
    layers.push(rectLayer({ name: "强调条", x: 155, y: 720, width: 770, height: 92, fill: "#4ea3ff", opacity: 0.72, cornerRadius: 26 }));
  } else if (kind === "divider") {
    layers.push(rectLayer({ name: "分隔线", x: 240, y: 950, width: 600, height: 8, fill: "#6ee7b7", opacity: 0.9, cornerRadius: 6 }));
  } else if (kind === "lower-third") {
    const baseZ = nextZIndex();
    layers.push(rectLayer({ id: uid("lower"), name: "下三分之一底板", x: 92, y: 1400, width: 896, height: 160, fill: "#111827", opacity: 0.74, cornerRadius: 28, zIndex: baseZ }));
    layers.push(textLayer({ name: "下三分之一文字", text: "Lower third title", x: 140, y: 1438, width: 800, height: 80, fontSize: 44, fontWeight: "800", zIndex: baseZ + 1 }));
  } else if (kind === "quote-card") {
    const baseZ = nextZIndex();
    layers.push(rectLayer({ id: uid("card"), name: "引用卡片", x: 112, y: 520, width: 856, height: 560, fill: "#20232a", opacity: 0.86, cornerRadius: 34, zIndex: baseZ }));
    layers.push(textLayer({ name: "引用文字", text: "Peace begins with a quiet heart.", x: 165, y: 680, width: 750, height: 260, fontSize: 54, fontWeight: "700", fill: "#fff7e8", zIndex: baseZ + 1 }));
  }
  page().layers.push(...layers);
  selectedLayerId = layers[layers.length - 1]?.id ?? "";
  renderAll(true);
}

function addImageFromInput(): void {
  const src = imageUrlInput.value.trim();
  if (!src) {
    imageUrlInput.focus();
    return;
  }
  const layer = imageLayer(src);
  page().layers.push(layer);
  selectedLayerId = layer.id;
  renderAll(true);
}

function applyTemplate(kind: "title" | "prayer" | "verse"): void {
  const active = page();
  active.duration = kind === "title" ? 4.5 : 7;
  const cardRect: DesignLayer = {
    id: uid("card"),
    type: "rect",
    name: "柔光卡片",
    x: 112,
    y: kind === "title" ? 360 : 500,
    width: 856,
    height: kind === "title" ? 450 : 720,
    fill: kind === "verse" ? "#182a42" : "#141c2c",
    opacity: kind === "verse" ? 0.62 : 0.58,
    cornerRadius: 34,
    start: 0,
    end: 0,
    zIndex: 0
  };
  const title: DesignLayer = {
    id: uid("title"),
    type: "text",
    name: kind === "verse" ? "经文标题" : "标题",
    text: kind === "title" ? "Prayer Title" : kind === "verse" ? "Psalm 23:1" : "Morning Prayer",
    x: 140,
    y: kind === "title" ? 455 : 610,
    width: 800,
    height: 132,
    fontSize: kind === "title" ? 86 : 70,
    fontFamily: "Noto Sans SC",
    fontWeight: "800",
    fill: "#ffffff",
    align: "center",
    opacity: 1,
    start: 0,
    end: 0,
    zIndex: 1,
    shadow: true
  };
  const body: DesignLayer = {
    id: uid("body"),
    type: "text",
    name: kind === "verse" ? "经文正文" : "祷告词",
    text: kind === "verse" ? "The Lord is my shepherd; I shall not want." : "Lord, guide my heart today. Fill this moment with peace, grace, and quiet strength.",
    x: 165,
    y: kind === "title" ? 610 : 770,
    width: 750,
    height: kind === "title" ? 170 : 350,
    fontSize: kind === "title" ? 44 : 48,
    fontFamily: "Noto Sans SC",
    fontWeight: "600",
    fill: "#fff7e8",
    align: "center",
    opacity: 0.98,
    start: kind === "title" ? 0.4 : 0,
    end: 0,
    zIndex: 2,
    shadow: true
  };
  active.layers = [cardRect, title, body];
  selectedLayerId = title.id;
  renderAll(true);
}

function updateSelected(mutator: (layer: DesignLayer) => void): void {
  const layer = selectedLayer();
  if (!layer) return;
  mutator(layer);
  renderAll(true);
}

function moveLayer(layerId: string, direction: 1 | -1): void {
  const layers = sortedLayers();
  const index = layers.findIndex((layer) => layer.id === layerId);
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= layers.length) return;
  const currentZ = layers[index].zIndex ?? index;
  layers[index].zIndex = layers[nextIndex].zIndex ?? nextIndex;
  layers[nextIndex].zIndex = currentZ;
  selectedLayerId = layerId;
  renderAll(true);
}

document.querySelectorAll<HTMLButtonElement>(".design-tab").forEach((button) => {
  button.onclick = () => {
    const tab = button.dataset.tab ?? "assets";
    document.querySelectorAll<HTMLButtonElement>(".design-tab").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelectorAll<HTMLElement>(".design-pane").forEach((pane) => pane.classList.toggle("active", pane.dataset.pane === tab));
  };
});
document.querySelectorAll<HTMLButtonElement>("[data-asset]").forEach((button) => {
  button.onclick = () => addLayer(button.dataset.asset as AssetKind);
});
document.querySelector<HTMLButtonElement>("#add-image")!.onclick = addImageFromInput;
imageUrlInput.onkeydown = (event) => {
  if (event.key === "Enter") addImageFromInput();
};
document.querySelector<HTMLButtonElement>("#tpl-title")!.onclick = () => applyTemplate("title");
document.querySelector<HTMLButtonElement>("#tpl-prayer")!.onclick = () => applyTemplate("prayer");
document.querySelector<HTMLButtonElement>("#tpl-verse")!.onclick = () => applyTemplate("verse");
document.querySelector<HTMLButtonElement>("#add-page")!.onclick = () => {
  state.pages.push({ id: uid("page"), name: `页面 ${state.pages.length + 1}`, duration: 5, layers: [] });
  currentPageIndex = state.pages.length - 1;
  selectedLayerId = "";
  renderAll(true);
};
document.querySelector<HTMLButtonElement>("#duplicate-page")!.onclick = () => {
  const copy = cloneDesign(page());
  copy.id = uid("page");
  copy.name = `${copy.name} 副本`;
  state.pages.splice(currentPageIndex + 1, 0, copy);
  currentPageIndex += 1;
  selectedLayerId = "";
  renderAll(true);
};
document.querySelector<HTMLButtonElement>("#delete-page")!.onclick = () => {
  if (state.pages.length <= 1) return;
  state.pages.splice(currentPageIndex, 1);
  currentPageIndex = Math.max(0, Math.min(currentPageIndex, state.pages.length - 1));
  selectedLayerId = "";
  renderAll(true);
};
document.querySelector<HTMLButtonElement>("#delete-layer")!.onclick = () => {
  page().layers = page().layers.filter((layer) => layer.id !== selectedLayerId);
  selectedLayerId = "";
  renderAll(true);
};
document.querySelector<HTMLButtonElement>("#fit-page-duration")!.onclick = () => {
  updateSelected((layer) => {
    layer.start = 0;
    layer.end = 0;
  });
};
document.querySelectorAll<HTMLButtonElement>("[data-duration]").forEach((button) => {
  button.onclick = () => {
    page().duration = Math.max(0.1, Number(button.dataset.duration) || 5);
    renderAll(true);
  };
});

pageDurationInput.onchange = () => {
  page().duration = Math.max(0.1, Number(pageDurationInput.value) || 5);
  renderAll(true);
};
layerNameInput.oninput = () => updateSelected((layer) => { layer.name = layerNameInput.value; });
layerTextInput.oninput = () => updateSelected((layer) => { layer.text = layerTextInput.value; });
layerSrcInput.onchange = () => updateSelected((layer) => { layer.src = layerSrcInput.value.trim(); });
layerStartInput.onchange = () => updateSelected((layer) => {
  const end = effectiveLayerEnd(layer);
  setLayerTimes(layer, Number(layerStartInput.value) || 0, end);
});
layerEndInput.onchange = () => updateSelected((layer) => {
  const start = Number(layer.start) || 0;
  const rawEnd = Number(layerEndInput.value) || 0;
  if (rawEnd <= 0) {
    layer.end = 0;
  } else {
    setLayerTimes(layer, start, rawEnd);
  }
});
layerSizeInput.onchange = () => updateSelected((layer) => { layer.fontSize = Math.max(8, Number(layerSizeInput.value) || 48); });
layerOpacityInput.onchange = () => updateSelected((layer) => { layer.opacity = Math.max(0, Math.min(1, Number(layerOpacityInput.value) || 0)); });
layerFillInput.oninput = () => updateSelected((layer) => { layer.fill = layerFillInput.value; });
layerAlignInput.onchange = () => updateSelected((layer) => { layer.align = layerAlignInput.value as DesignLayer["align"]; });

stage.on("click tap", (event) => {
  if (event.target === stage || event.target.getLayer() === bgLayer) {
    selectedLayerId = "";
    renderAll(false);
  }
});
window.addEventListener("pointermove", (event) => {
  if (!timelineDrag) return;
  const layer = page().layers.find((item) => item.id === timelineDrag?.layerId);
  if (!layer) return;
  const delta = ((event.clientX - timelineDrag.originX) / timelineDrag.laneWidth) * timelineDrag.duration;
  if (timelineDrag.mode === "move") {
    const length = timelineDrag.originEnd - timelineDrag.originStart;
    const start = Math.max(0, Math.min(timelineDrag.duration - length, timelineDrag.originStart + delta));
    setLayerTimes(layer, start, start + length, timelineDrag.duration);
  } else if (timelineDrag.mode === "start") {
    setLayerTimes(layer, timelineDrag.originStart + delta, timelineDrag.originEnd, timelineDrag.duration);
  } else {
    setLayerTimes(layer, timelineDrag.originStart, timelineDrag.originEnd + delta, timelineDrag.duration);
  }
  renderAll(true);
});
window.addEventListener("pointerup", () => {
  timelineDrag = null;
});
window.addEventListener("resize", resizeStage);

window.designEditorSetState = (payload: string) => {
  state = normalizeState(parseJson(payload, cloneDesign(defaultState)));
  currentPageIndex = Math.max(0, Math.min(currentPageIndex, state.pages.length - 1));
  selectedLayerId = "";
  resizeStage();
  renderAll(false);
};

state = normalizeState(state);
renderAll(false);
void connectQtBridge<DesignBridge>("designBridge")
  .then((connected) => {
    bridge = connected;
    bridge.getState((raw) => {
      state = normalizeState(parseJson(raw, cloneDesign(defaultState)));
      currentPageIndex = 0;
      selectedLayerId = "";
      resizeStage();
      renderAll(false);
    });
  })
  .catch(() => {
    resizeStage();
  });
