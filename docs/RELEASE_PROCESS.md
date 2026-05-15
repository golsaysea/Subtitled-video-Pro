# Release Process

## Pre-Release Checklist

1. Confirm the project license baseline is acceptable: `GPL-3.0-only`.
2. Confirm no `settings.json`, API keys, Cloudflare tokens, ElevenLabs tokens, or local workspace paths are staged.
3. Rotate any credentials that previously existed in the repository or local git history.
4. Run the dependency license audit after dependency changes.
5. Build `web_tools/dist` from current TypeScript sources.
6. Push a clean tag such as `v0.1.0`.

## Recommended First Public Push

This working tree previously contained local credentials in `settings.json` and a hardcoded cloud sync secret in `core.py`. The current files remove those from the working tree, but existing git history can still retain old values.

For a public GitHub repository, use one of these safe paths:

| Path | When To Use |
| --- | --- |
| Fresh public repo from sanitized files | Recommended first release path |
| History rewrite before push | Use only if you must preserve commit history |
| Private repo only | Acceptable if credentials are already rotated and access is controlled |

## Tag Release

```powershell
git status --short
git tag v0.1.0
git push origin v0.1.0
```

The `Release` workflow will:

1. install Node and Python dependencies;
2. build Vite web panels;
3. build the Windows app with PyInstaller;
4. package notices and license audit files into the zip;
5. create `checksums.sha256`;
6. create GitHub artifact attestations;
7. publish or update the GitHub release.

## Manual Workflow Release

In GitHub Actions, run `Release` manually and enter a version like `v0.1.0`.

## Verify After Release

```powershell
gh release download v0.1.0 -R secure-artifacts/Subtitled-video-Pro
Get-FileHash .\SubtitleComposer-v0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\checksums.sha256
gh attestation verify .\SubtitleComposer-v0.1.0-windows-x64.zip -R secure-artifacts/Subtitled-video-Pro
```

## Rollback

If a bad release is published, mark the GitHub release as pre-release or delete the release artifact, then cut a new tag after fixing the issue. Avoid reusing the same tag for public releases unless the release never left private testing.
