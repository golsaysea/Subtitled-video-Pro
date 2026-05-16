# Release Process

## Pre-Release Checklist

1. Confirm the project license baseline is acceptable: `GPL-3.0-only`.
2. Confirm no `settings.json`, API keys, Cloudflare tokens, ElevenLabs tokens,
   or personal local workspace paths are staged.
3. Rotate any credentials that previously existed in the directory, repository,
   release artifact, or local git history.
4. Run the dependency license audit after dependency or bundled-font changes.
5. Confirm `fonts/open/open_fonts_manifest.json` matches the bundled font files
   and that font license files remain beside the fonts.
6. Build `web_tools/dist` from current TypeScript sources.
7. Push a clean tag such as `v0.1.0`.

## Recommended First Public Push

The prepared package is intended as a sanitized public-release workspace.

For the first public GitHub repository, use one of these paths:

| Path | When To Use |
| --- | --- |
| Fresh public repo from sanitized files | Recommended first release path |
| Copy sanitized files into an existing private repo | Use only after reviewing old history and rotating credentials |
| History rewrite before public push | Use only if you must preserve existing commit history |

Example first push:

```powershell
git init
git add .
git status --short
git commit -m "Prepare public release"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

## Tag Release

```powershell
git status --short
git tag v0.1.0
git push origin v0.1.0
```

The `Release` workflow will:

1. install locked Node dependencies with `npm ci` and Python dependencies;
2. build Vite web panels;
3. validate that required release notices and font manifest files exist;
4. reject a checkout that contains local-only `settings.json`;
5. build Windows x64 with PyInstaller on `windows-latest`;
6. build macOS x64 on `macos-15-intel`;
7. build macOS arm64 on `macos-15`;
8. bundle `fonts/open`, `font_registry.json`, `nlp_dictionary.txt`, and notices;
9. apply ad-hoc signing to the macOS `.app` bundles;
10. create per-platform checksum files and a combined `checksums.sha256`;
11. create GitHub artifact attestations;
12. publish or update the GitHub release.

The macOS packages are ad-hoc signed, not Apple Developer ID notarized. If you
want a Gatekeeper-friendly public macOS release, add Apple signing certificate
and notarization secrets to the workflow before publishing broadly.

## Manual Workflow Release

In GitHub Actions, run `Release` manually and enter a version like `v0.1.0`.

## Verify After Release

```powershell
gh release download v0.1.0 -R <owner>/<repo>
Get-FileHash .\SubtitleComposer-v0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\checksums.sha256
gh attestation verify .\SubtitleComposer-v0.1.0-windows-x64.zip -R <owner>/<repo>
```

For macOS:

```bash
gh release download v0.1.0 -R <owner>/<repo>
shasum -a 256 SubtitleComposer-v0.1.0-macos-arm64.zip
cat checksums.sha256
gh attestation verify SubtitleComposer-v0.1.0-macos-arm64.zip -R <owner>/<repo>
```

## Rollback

If a bad release is published, mark the GitHub release as pre-release or delete
the release artifact, then cut a new tag after fixing the issue. Avoid reusing
the same tag for public releases unless the release never left private testing.
