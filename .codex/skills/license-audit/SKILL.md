---
name: license-audit
<<<<<<< HEAD
description: Dependency license compliance check for this project. Use when requirements.txt, requirements-build.txt, web_tools/package.json, web_tools/package-lock.json, fonts/open/open_fonts_manifest.json, go.mod, pyproject.toml, Cargo.toml, or any dependency declaration changes.
=======
description: Dependency license compliance check for this project. Use when requirements.txt, requirements-build.txt, web_tools/package.json, go.mod, pyproject.toml, Cargo.toml, or any dependency declaration changes.
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
---

# Dependency License Audit Skill

Use this skill whenever a dependency declaration changes, a release is prepared,
or the project license is changed.

## Scope

- Audit direct runtime dependencies only for the formal `LICENSE.LIST` count.
<<<<<<< HEAD
- Track build-only, bundled font assets, and externally downloaded release
  components separately.
=======
- Track build-only and externally downloaded release components separately.
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
- Current project baseline: `GPL-3.0-only`, because PyPI `PyQt6` and
  `PyQt6-WebEngine` are `GPL-3.0-only` unless a Riverbank commercial license is
  documented.

## Files To Watch

- `requirements.txt`
- `requirements-build.txt`
- `web_tools/package.json`
<<<<<<< HEAD
- `web_tools/package-lock.json`
- `fonts/open/open_fonts_manifest.json`
- `fonts/open/**/OFL.txt`
- `fonts/open/**/LICENSE.txt`
- `fonts/open/**/LICENSE.md`
=======
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
- `LICENSE.LIST`
- `LICENSE`
- `COPYING`
- `.github/workflows/release.yml`

## Procedure

1. Detect dependency changes by comparing the dependency files with
   `LICENSE.LIST`.
2. For new or changed direct runtime dependencies, use WebSearch with:
   - Python: `<package> pypi license`
   - npm: `<package> npm package license`
   - Go: `<module> go module license`
   - Rust: `<crate> crates.io license`
   - .NET: `<package> nuget license`
3. Record SPDX identifier, source URL, confirmation status, and open-source
   status.
4. Check compatibility against project baseline `GPL-3.0-only`.
5. Update `LICENSE.LIST` and `LICENSE` when direct runtime dependency licenses
   change.
<<<<<<< HEAD
6. If `fonts/open/open_fonts_manifest.json` changes, verify bundled fonts keep
   an open font license file next to the redistributed font file.
7. Update `docs/DEPENDENCY_LICENSE_AUDIT.md` for release-facing audit results.
8. Warn the user if:
   - a dependency is `UNKNOWN`;
   - a dependency is non-open-source;
   - PyQt commercial licensing is claimed but not documented;
   - a bundled font has no license file or uses a non-open/non-commercial-only
     font license;
=======
6. Update `docs/DEPENDENCY_LICENSE_AUDIT.md` for release-facing audit results.
7. Warn the user if:
   - a dependency is `UNKNOWN`;
   - a dependency is non-open-source;
   - PyQt commercial licensing is claimed but not documented;
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c
   - FFmpeg GPL binaries are bundled without notices/source-offer handling.

## Risk Rules

- Low: MIT, BSD-2-Clause, BSD-3-Clause, ISC, Apache-2.0, Unlicense, CC0-1.0.
- Attention: GPL, AGPL, LGPL, MPL, BSL, SSPL, CC-BY-SA-4.0.
- Manual confirmation required: UNKNOWN, CC-BY-NC, custom, proprietary, or
  commercial-only licenses.
<<<<<<< HEAD
- Bundled font assets: OFL-1.1 is acceptable when license files are preserved;
  modified OFL fonts must respect reserved font name requirements.
=======
>>>>>>> 5a04da6a531f4371718564480a44293c4ea0381c

## References

- Audit guide: https://tpscsm-docs.pages.dev/license-audit/
- Current dependency list: `LICENSE.LIST`
- Compliance report: `LICENSE`
