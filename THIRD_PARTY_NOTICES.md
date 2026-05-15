# Third-Party Notices

Generated: 2026-05-15

This file summarizes direct runtime dependencies and release-relevant components. See `LICENSE.LIST` for the formal direct dependency audit.

## Direct Runtime Dependencies

| Component | Version | License | Source |
| --- | --- | --- | --- |
| PyQt6 | 6.11.0 | GPL-3.0-only or Riverbank commercial license | https://pypi.org/project/PyQt6/ |
| PyQt6-WebEngine | 6.11.0 | GPL-3.0-only or Riverbank commercial license | https://pypi.org/project/PyQt6-WebEngine/ |
| requests | 2.34.2 | Apache-2.0 | https://pypi.org/project/requests/ |
| playwright | 1.59.0 | Apache-2.0 | https://pypi.org/project/playwright/ |

## Release-Relevant Components

| Component | License / Notice | Source | Notes |
| --- | --- | --- | --- |
| PyInstaller | GPL-2.0-or-later with bootloader exception; selected files Apache-2.0 | https://pyinstaller.org/en/stable/license.html | Used to produce Windows release artifacts |
| FFmpeg BtbN GPL build | GPL/LGPL FFmpeg components depending on build variant | https://github.com/BtbN/FFmpeg-Builds | App can download FFmpeg on demand; do not bundle silently without notices/source-offer handling |
| Playwright Chromium browser | Chromium and bundled component licenses | https://playwright.dev/python/ | If bundled into the release artifact, keep browser notices under review |

## Project License Baseline

This repository is prepared for `GPL-3.0-only` open-source distribution because PyPI PyQt6/PyQt6-WebEngine require GPL-compatible distribution unless a commercial Riverbank license is documented.
