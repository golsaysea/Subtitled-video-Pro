# Subtitle Composer / Subtitled Video Pro

Desktop subtitle composition and video delivery tool for project-based editing, batch transcription, rolling subtitle utilities, ElevenLabs voice workflows, and FFmpeg-based export.

## Project Layout

| Path | Purpose |
| --- | --- |
| `main.py` | PyQt6 desktop entry point |
| `room_*.py` | Main application rooms and workflows |
| `web_tools/` | Vite/TypeScript panels loaded through Qt WebEngine |
| `requirements.txt` | Runtime Python dependencies |
| `requirements-build.txt` | Release build dependencies |
| `.github/workflows/release.yml` | GitHub release build, checksum, and artifact attestation workflow |
| `LICENSE.LIST` | Direct dependency license audit list |
| `docs/DEPENDENCY_LICENSE_AUDIT.md` | Chinese dependency license audit report |

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
npm install
npm run build
cd ..
```

Run from source:

```powershell
python main.py
```

## Local Secrets

Do not commit `settings.json`. Start from the template:

```powershell
Copy-Item settings.example.json settings.json
```

Cloud sync credentials should be supplied locally through `settings.json` or environment variables:

```powershell
$env:SUBTITLE_COMPOSER_SYNC_URL = "https://your-worker.workers.dev/"
$env:SUBTITLE_COMPOSER_CLOUD_SECRET = "your-local-secret"
```

## Release

Create a release by pushing a tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

You can also run the `Release` workflow manually and enter a tag like `v0.1.0`.

The workflow builds a Windows x64 zip, generates `checksums.sha256`, uploads the files to GitHub Releases, and creates GitHub artifact attestations with `actions/attest`.

## Verify Release Artifact

```powershell
gh release download v0.1.0 -R secure-artifacts/Subtitled-video-Pro
Get-FileHash .\SubtitleComposer-v0.1.0-windows-x64.zip -Algorithm SHA256
gh attestation verify .\SubtitleComposer-v0.1.0-windows-x64.zip -R secure-artifacts/Subtitled-video-Pro
```

Compare the SHA256 result with `checksums.sha256`.

## License And Compliance

The prepared open-source baseline is `GPL-3.0-only` because the app uses PyPI `PyQt6` and `PyQt6-WebEngine`, whose open-source distribution path is GPL-3.0-only. If the project owner has a Riverbank commercial license for PyQt/PyQt-WebEngine, the project license can be revisited before release.

See:

- `LICENSE`
- `COPYING`
- `LICENSE.LIST`
- `docs/DEPENDENCY_LICENSE_AUDIT.md`
- `THIRD_PARTY_NOTICES.md`
