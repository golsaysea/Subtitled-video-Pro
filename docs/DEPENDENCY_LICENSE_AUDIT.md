# 依赖协议审计报告

## 项目信息

- 项目名称：Subtitle Composer / Subtitled Video Pro
- 项目路径：`0516`
- 项目类型：Python desktop app + Vite web tool panels + bundled open font assets
- 审计时间：2026-05-30
- 审计基准：公开 GitHub 开源分发
- 审计范围：直接运行依赖；构建工具、外部可执行组件和字体资产单独列示

## 版权协议合规结论

最终判定：有条件合规，可开源分发。

条件是：项目必须按 `GPL-3.0-only` 分发，并随 release 提供完整对应源代码、许可证声明、第三方 notices、字体许可证文件和构件证明。

原因：当前直接运行依赖中包含 `PyQt6` 与 `PyQt6-WebEngine`。两者在 PyPI 的开源分发路径为 `GPL-3.0-only`，另有 Riverbank 商业许可路径。如果没有商业 PyQt 授权，项目不应以 MIT、Apache-2.0 或闭源专有协议公开分发。

0516 新增的 `fonts/open` 字体包按发布资产审计：当前 manifest 记录 21 个字体文件，许可证为 `OFL-1.1` 或兼容开放字体许可证。字体资产与 GPL-3.0-only 项目分发兼容，但必须保留各字体目录内的 `OFL.txt`、`LICENSE.txt` 或 `LICENSE.md`。

0519 新增的 `web_tools` 设计房间依赖 `konva@10.3.0`，许可证为 `MIT`，用于 Canva 式页面/图层画布编辑。该依赖与 GPL-3.0-only 项目基准兼容，需在发布包中保留 MIT notices。

## 审计结果摘要

| 指标 | 数值 |
| --- | ---: |
| 直接运行依赖总数 | 5 |
| 已确认协议 | 5 |
| 未确认协议 | 0 |
| 低风险 | 3 |
| 需关注 | 2 |
| 需手动确认 | 0 |
| 发布相关字体文件 | 21 |

## 协议分布

| 协议 | 数量 | 占比 | 说明 |
| --- | ---: | ---: | --- |
| GPL-3.0-only | 2 | 40% | 强 copyleft；决定项目开源分发基准 |
| Apache-2.0 | 2 | 40% | 与 GPL-3.0-only 兼容；需保留 notices |
| MIT | 1 | 20% | 与 GPL-3.0-only 兼容；需保留 notices |

字体资产：21 个字体文件，按 `OFL-1.1` 或兼容开放字体许可证单独记录，不计入直接运行依赖总数。

## 依赖明细

| 依赖名称 | 版本 | 协议 | 来源 | 结论 |
| --- | --- | --- | --- | --- |
| PyQt6 | 6.11.0 | GPL-3.0-only 或商业许可 | https://pypi.org/project/PyQt6/ | 需按 GPL-3.0-only 分发，除非有商业授权 |
| PyQt6-WebEngine | 6.11.0 | GPL-3.0-only 或商业许可 | https://pypi.org/project/PyQt6-WebEngine/ | 需按 GPL-3.0-only 分发，Riverbank 说明其不提供 LGPL 路径 |
| requests | 2.34.2 | Apache-2.0 | https://pypi.org/project/requests/ | 与 GPL-3.0-only 兼容 |
| playwright | 1.59.0 | Apache-2.0 | https://pypi.org/project/playwright/ | 与 GPL-3.0-only 兼容 |
| konva | 10.3.0 | MIT | https://www.npmjs.com/package/konva | 与 GPL-3.0-only 兼容；用于设计房间 canvas 图层编辑 |

## 发布资产明细

| 资产 | 数量 | 协议 | 来源 | 结论 |
| --- | ---: | --- | --- | --- |
| Open font pack | 21 个字体文件 | OFL-1.1 或兼容开放字体许可证 | `fonts/open/open_fonts_manifest.json` | 可随 GPL-3.0-only 项目发布；保留字体许可证文件 |
| FFmpeg | 按需下载，不在当前 workflow 中主动捆绑 | GPL/LGPL 取决于构建变体 | `core.py` 中 BtbN GPL build URL | 若未来打包进 release，需补齐 notices/source-offer |
| PyInstaller | 构建工具 | GPL-2.0-or-later with bootloader exception | https://pyinstaller.org/en/stable/license.html | 可用于构建；保留 provenance |
| Playwright browsers | release build 安装 Chromium | Chromium/browser 组件许可证 | https://playwright.dev/python/ | 若被打进产物，持续跟踪 notices |

## 风险发现

### 协议不兼容

未发现与 `GPL-3.0-only` 项目基准不兼容的直接运行依赖。

如果项目改用 `MIT`、`Apache-2.0` 或闭源专有协议，则 `PyQt6` 和 `PyQt6-WebEngine` 会成为协议冲突项。修复路径为：

| 方案 | 说明 |
| --- | --- |
| 保持 GPL-3.0-only | 当前自动化审计推荐路径，适合公开 GitHub 开源分发 |
| 购买并记录 Riverbank 商业授权 | 可另选项目协议；需在 release 合规材料中记录授权依据 |
| 替换 GUI 框架 | 例如切换到 LGPL/宽松协议 GUI 方案，但需要较大改造 |

### 协议未知

所有直接运行依赖协议均已确认。字体资产目前均有 manifest 记录，但仍需在 release 包中保留实际许可证文件。

### 外部组件风险

| 组件 | 风险 | 建议 |
| --- | --- | --- |
| FFmpeg BtbN GPL build | `core.py` 指向 `ffmpeg-master-latest-win64-gpl.zip`；若随安装包捆绑，需遵守 FFmpeg/GPL notices 与源码提供义务 | 当前 release workflow 不主动捆绑 FFmpeg；若未来捆绑，先补齐 notices/source-offer |
| 字体包 | OFL 字体可以随软件发布，但修改字体后不得违规使用 Reserved Font Name | 保留每个字体目录内的许可证文件；修改字体时重命名并更新 manifest |
| settings.json | 本地配置可能包含 token、API key、云同步地址和本地路径 | 不提交 `settings.json`；使用 `settings.example.json` 模板 |

## 生成文件

| 文件 | 路径 | 说明 |
| --- | --- | --- |
| LICENSE.LIST | `LICENSE.LIST` | 直接依赖协议清单 |
| LICENSE | `LICENSE` | 项目协议合规参考报告 |
| COPYING | `COPYING` | 项目 GPL-3.0-only 短许可证声明 |
| requirements.txt | `requirements.txt` | Python 运行依赖清单 |
| requirements-build.txt | `requirements-build.txt` | Python 构建依赖清单 |
| THIRD_PARTY_NOTICES.md | `THIRD_PARTY_NOTICES.md` | 第三方 notices 汇总 |

## 已安装 Skill

| 编辑器 | Skill 路径 | 说明 |
| --- | --- | --- |
| Codex | `.codex/skills/license-audit/SKILL.md` | 依赖声明、字体 manifest 或 release 准备变更时重新检查协议合规性 |

## 后续建议

1. 推送 GitHub 前确认项目是否接受 `GPL-3.0-only` 开源分发。
2. 如果计划闭源或使用 MIT/Apache-2.0，请先取得并记录 Riverbank PyQt/PyQt-WebEngine 商业授权。
3. 发布二进制时随包附带 `LICENSE`、`COPYING`、`LICENSE.LIST`、`THIRD_PARTY_NOTICES.md`、本报告、字体许可证文件和 release checksum。
4. 若未来把 FFmpeg 或 Playwright 浏览器二进制打进安装包，新增第三方 notices 与源码/许可证说明。
5. 每次依赖或字体资产变更后重新执行本审计。
