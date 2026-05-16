# Security Policy

## Supported Versions

Only the latest GitHub Release is supported for security fixes.

## Reporting A Vulnerability

Open a private security advisory in GitHub if available, or contact the repository owner privately. Do not publish working exploits or leaked credentials in public issues.

## Secret Handling

- `settings.json` is local-only and ignored.
- Use `settings.example.json` as the safe template.
- Cloud sync credentials belong in local `settings.json` or environment variables.
<<<<<<< HEAD
- The public release tree must not contain a real default sync URL or embedded cloud secret.
=======
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
- Rotate any token that was committed, staged, pasted into an issue, or included in a release artifact.

## Build Provenance

Release artifacts are built by `.github/workflows/release.yml`, checksummed, and attested with GitHub artifact attestations. See `docs/SECURITY_ATTESTATION.md` for verification commands.
<<<<<<< HEAD

Bundled fonts under `fonts/open` must keep their manifest and license files in release artifacts.
=======
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
