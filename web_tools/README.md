# Subtitle Composer Web Tools

This folder is the front-end workspace for WebEngine-based tool panels.

The Python app remains the host and engine layer. Web tools are loaded through
`QWebEngineView` and communicate with Python through `QWebChannel`.

## Layout

- `src/shared`: typed bridge helpers, common UI utilities, shared theme CSS.
- `src/elevenlabs`: the ElevenLabs API tool source page.
- `dist`: checked-in runtime build loaded by PyQt when present.

## Commands

```powershell
npm install
npm run dev
npm run build
```

After `npm run build`, PyQt will load `web_tools/dist/<tool>/index.html`.
If a built page is missing, Python falls back to the legacy embedded HTML.
