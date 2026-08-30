# Impeccable

Impeccable is the high-craft frontend workflow vendored by this research-toolkit
repository for research homepages, paper companion sites, interactive method
demos, result browsers, and benchmark dashboards. It covers the full design
cycle: product context, visual direction, implementation guidance, critique,
accessibility and performance audits, hardening, live browser iteration, and
final polish.

This directory is the complete, provider-specific Codex runtime payload rather
than a copy of Impeccable's multi-provider monorepo. The 153 upstream runtime
files are pinned to Skill `4.1.2` for reproducibility. Exact provenance and
licensing are recorded in [VENDORED_FROM.md](VENDORED_FROM.md), [LICENSE](LICENSE),
and [NOTICE.md](NOTICE.md).

## Install for every local Codex session

Copy this directory to the user-level Codex Skill root:

```powershell
$codexSkillRoot = Join-Path $env:USERPROFILE '.codex\skills'
Copy-Item -LiteralPath '.\impeccable' `
  -Destination (Join-Path $codexSkillRoot 'impeccable') `
  -Recurse -Force
```

New or reloaded Codex sessions can then discover `impeccable`. Its scripts
require Node.js 22.18 or newer; Codex's bundled Node runtime is sufficient on the
machine used to publish this snapshot. URL scanning additionally requires
Puppeteer and a compatible Chrome/Chromium installation. Full static HTML/CSS
parsing uses `htmlparser2`, `css-select`, `css-tree`, and `domutils`; without
those packages the detector deliberately falls back to its regex engine. The
user-level installation verified for this release includes all five packages.

Automatic detector hooks are intentionally not installed globally. A hook is a
project-level, explicitly approved capability stored in that project's
`.codex/hooks.json`; enable it only for projects where continuous detector runs
are wanted. The Skill remains fully discoverable and its manual workflows remain
available without a hook.

## 中文说明

本目录提供 Impeccable 的完整 Codex 运行载荷，用于把科研成果制作成高质量的
科研主页、论文 companion site、交互式方法 demo、结果浏览器与 benchmark
dashboard。它覆盖产品上下文、视觉方向、实现指导、评审、无障碍与性能审计、
加固、浏览器实时迭代和最终润色。

将整个目录复制到用户级 `~/.codex/skills/impeccable` 后，新的或重新加载的
Codex 会话即可发现该 Skill。自动 detector hook 属于项目级能力，必须在对应
项目的 `.codex/hooks.json` 中单独配置并批准，不会随全局安装静默启用。
