# Subtitle Composer / Subtitled Video Pro

<<<<<<< HEAD
Desktop subtitle composition and video delivery tool for project-based editing,
batch transcription, rolling subtitle utilities, ElevenLabs voice workflows,
open-font subtitle styling, and FFmpeg-based export.
=======
Desktop subtitle composition and video delivery tool for project-based editing, batch transcription, rolling subtitle utilities, ElevenLabs voice workflows, and FFmpeg-based export.
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

## Project Layout

| Path | Purpose |
| --- | --- |
| `main.py` | PyQt6 desktop entry point |
| `room_*.py` | Main application rooms and workflows |
| `web_tools/` | Vite/TypeScript panels loaded through Qt WebEngine |
<<<<<<< HEAD
| `web_tools/package-lock.json` | Locked frontend build dependency graph |
| `fonts/open/` | Bundled open font pack and per-font license files |
| `font_registry.json` | Font policy registry used by the app and release audit |
| `scripts/download_open_fonts.py` | Google Fonts starter-pack downloader |
| `scripts/download_adobe_open_fonts.py` | Adobe Source / Source Han open-font downloader |
| `requirements.txt` | Runtime Python dependencies |
| `requirements-build.txt` | Release build dependencies |
| `main.spec` | Optional local PyInstaller spec mirroring the GitHub release bundle |
| `.github/workflows/release.yml` | GitHub release build, checksum, and artifact attestation workflow |
| `LICENSE.LIST` | Direct dependency license audit list |
| `docs/DEPENDENCY_LICENSE_AUDIT.md` | Dependency and release-asset license audit report |
| `docs/SECURITY_ATTESTATION.md` | Release provenance and verification guide |
| `docs/RELEASE_PROCESS.md` | Public release checklist |
=======
| `requirements.txt` | Runtime Python dependencies |
| `requirements-build.txt` | Release build dependencies |
| `.github/workflows/release.yml` | GitHub release build, checksum, and artifact attestation workflow |
| `LICENSE.LIST` | Direct dependency license audit list |
| `docs/DEPENDENCY_LICENSE_AUDIT.md` | Chinese dependency license audit report |
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

## Local Setup

Use Python 3.12 on Windows for the release-equivalent path.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Build the web panels when changing `web_tools/src`:

```powershell
cd web_tools
<<<<<<< HEAD
npm ci
=======
npm install
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
npm run build
cd ..
```

Run from source:

```powershell
python main.py
```

## Local Secrets

<<<<<<< HEAD
Do not commit `settings.json`. Start from the safe template:
=======
Do not commit `settings.json`. Start from the template:
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

```powershell
Copy-Item settings.example.json settings.json
```

<<<<<<< HEAD
Cloud sync credentials should be supplied locally through `settings.json` or
environment variables:
=======
Cloud sync credentials should be supplied locally through `settings.json` or environment variables:
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

```powershell
$env:SUBTITLE_COMPOSER_SYNC_URL = "https://your-worker.workers.dev/"
$env:SUBTITLE_COMPOSER_CLOUD_SECRET = "your-local-secret"
```

<<<<<<< HEAD
If real credentials ever existed in this directory or a local git history,
rotate them before publishing.

## First Public Push

The prepared `0516` package is a sanitized release workspace, not currently a
git repository. For the first public GitHub push, initialize or copy this
folder into the target repository after credential rotation:

```powershell
git init
git add .
git status --short
git commit -m "Prepare 0516 public release"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

Confirm that `settings.json`, local workspaces, generated build folders, and
personal tokens are not staged.

=======
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
## Release

Create a release by pushing a tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

You can also run the `Release` workflow manually and enter a tag like `v0.1.0`.

<<<<<<< HEAD
The workflow builds a Windows x64 zip, includes the open font pack, generates
`checksums.sha256`, uploads the files to GitHub Releases, and creates GitHub
artifact attestations with `actions/attest`.
=======
The workflow builds a Windows x64 zip, generates `checksums.sha256`, uploads the files to GitHub Releases, and creates GitHub artifact attestations with `actions/attest`.
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

## Verify Release Artifact

```powershell
<<<<<<< HEAD
gh release download v0.1.0 -R <owner>/<repo>
Get-FileHash .\SubtitleComposer-v0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\checksums.sha256
gh attestation verify .\SubtitleComposer-v0.1.0-windows-x64.zip -R <owner>/<repo>
=======
gh release download v0.1.0 -R secure-artifacts/Subtitled-video-Pro
Get-FileHash .\SubtitleComposer-v0.1.0-windows-x64.zip -Algorithm SHA256
gh attestation verify .\SubtitleComposer-v0.1.0-windows-x64.zip -R secure-artifacts/Subtitled-video-Pro
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
```

Compare the SHA256 result with `checksums.sha256`.

## License And Compliance

<<<<<<< HEAD
The prepared open-source baseline is `GPL-3.0-only` because the app uses PyPI
`PyQt6` and `PyQt6-WebEngine`, whose open-source distribution path is
GPL-3.0-only. If the project owner has a Riverbank commercial license for
PyQt/PyQt-WebEngine, the project license can be revisited before release.

The bundled `fonts/open` package contains 21 open font files recorded in
`fonts/open/open_fonts_manifest.json`; keep each font directory's `OFL.txt`,
`LICENSE.txt`, or `LICENSE.md` when redistributing the app or project packages.
=======
The prepared open-source baseline is `GPL-3.0-only` because the app uses PyPI `PyQt6` and `PyQt6-WebEngine`, whose open-source distribution path is GPL-3.0-only. If the project owner has a Riverbank commercial license for PyQt/PyQt-WebEngine, the project license can be revisited before release.
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

See:

- `LICENSE`
- `COPYING`
- `LICENSE.LIST`
<<<<<<< HEAD
- `THIRD_PARTY_NOTICES.md`
- `docs/DEPENDENCY_LICENSE_AUDIT.md`
- `docs/SECURITY_ATTESTATION.md`
- `docs/RELEASE_PROCESS.md`
=======
- `docs/DEPENDENCY_LICENSE_AUDIT.md`
- `THIRD_PARTY_NOTICES.md`
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
