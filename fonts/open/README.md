# Open Font Pack

Put commercial-safe open font files here, together with their license files.

Recommended layout:

```text
fonts/open/
  NotoSansSC[wght].ttf
  OFL.txt
  open_fonts_manifest.json
```

Subtitle Composer scans this directory on startup. Registered fonts are added to
the app font picker, injected into subtitle preview/export HTML with `@font-face`,
and recorded in `font_registry.json`.

Use `scripts/download_open_fonts.py` for the Google Fonts starter pack and
`scripts/download_adobe_open_fonts.py` for Adobe Source / Source Han open fonts.

Keep license files with the font files when redistributing the app or a packaged
project.
