export type BridgeCallback<T = string> = (value: T) => void;

export type BridgeSignal = {
  connect: (callback: (payload: string) => void) => void;
};

export type ElevenLabsAccount = {
  alias?: string;
  key: string;
  quota_left?: number;
  quota_limit?: number;
};

export type ElevenLabsVoice = {
  voice_id: string;
  name?: string;
  category?: string;
};

export type ElevenLabsState = {
  accounts: ElevenLabsAccount[];
  currentKey: string;
  voiceId: string;
  model: string;
  format: string;
  outputDir: string;
  stability: number;
  similarity: number;
  style: number;
  speakerBoost: boolean;
  clearAfter: boolean;
  splitMode?: number;
  apiKeyLink: string;
  cards: string[];
  voices?: ElevenLabsVoice[];
};

export type ElevenLabsBridge = {
  event: BridgeSignal;
  getState: (callback: BridgeCallback) => void;
  saveState: (payload: string) => void;
  refreshVoices: (key: string) => void;
  checkQuota: (key: string) => void;
  checkAllQuotas: (payload: string) => void;
  selectOutputDir: (callback: BridgeCallback) => void;
  exportAccountsCsv: (payload: string, callback: BridgeCallback) => void;
  importAccountsCsv: (callback: BridgeCallback) => void;
  exportConfig: (payload: string, callback: BridgeCallback) => void;
  importConfig: (callback: BridgeCallback) => void;
  openOutputDir: (path: string) => void;
  openExternalUrl: (url: string) => void;
  generate: (payload: string) => void;
};

export type ElevenLabsAssistAccount = {
  alias?: string;
  token: string;
  left?: number;
  total?: number;
};

export type ElevenLabsAssistState = {
  accounts: ElevenLabsAssistAccount[];
  currentToken: string;
  voiceId: string;
  model: string;
  outputDir: string;
  subFolder: string;
  stability: number;
  similarity: number;
  style: number;
  speakerBoost: boolean;
  compatMode: boolean;
  autoDelete: boolean;
  cards: string[];
  voices?: ElevenLabsVoice[];
};

export type ElevenLabsAssistBridge = {
  event: BridgeSignal;
  getState: (callback: BridgeCallback) => void;
  saveState: (payload: string) => void;
  openTokenCapture: () => void;
  refreshVoices: (token: string) => void;
  checkQuota: (token: string) => void;
  selectOutputDir: (callback: BridgeCallback) => void;
  openOutputDir: (path: string) => void;
  openOfficialGenerator: () => void;
  stopGeneration: () => void;
  generate: (payload: string) => void;
};

type QWebChannelCtor = new (
  transport: unknown,
  callback: (channel: { objects: Record<string, unknown> }) => void
) => void;

declare global {
  interface Window {
    qt?: { webChannelTransport: unknown };
    QWebChannel?: QWebChannelCtor;
  }
}

export function connectQtBridge<TBridge>(objectName: string): Promise<TBridge> {
  return new Promise((resolve, reject) => {
    if (!window.qt || !window.QWebChannel) {
      reject(new Error("Qt WebChannel is not available."));
      return;
    }

    new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
      const bridge = channel.objects[objectName] as TBridge | undefined;
      if (!bridge) {
        reject(new Error(`Bridge object not found: ${objectName}`));
        return;
      }
      resolve(bridge);
    });
  });
}

export function parseJson<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw || "") as T;
  } catch {
    return fallback;
  }
}
