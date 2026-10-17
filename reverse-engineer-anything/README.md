# REA: Reverse Engineer Anything

Vendored skill from the official [morluto/rea](https://github.com/morluto/rea)
project. See [UPSTREAM.json](UPSTREAM.json) for the exact revision and
[LICENSE](LICENSE) for its MIT license. `SKILL.md` and `references/` are kept
unchanged from that revision.

REA helps investigate shipped binaries, managed assemblies, JavaScript/Electron
applications, packages, firmware, and requested runtime behavior. Ordinary
source-code architecture analysis should use normal repository tools.

## Install for Codex

From this repository root, expose the skill to all projects for the current user:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/reverse-engineer-anything" \
  "${CODEX_HOME:-$HOME/.codex}/skills/reverse-engineer-anything"
```

Recent Codex versions also discover user skills in `$HOME/.agents/skills`.
Use that location when required by your client. Do not overwrite an existing
installation without inspecting it first. Invoke `$reverse-engineer-anything`
in Codex; newly installed skills should be available on the next turn. Restart
Codex if discovery has not refreshed.

## Install the runtime and register MCP

The skill contains instructions; the CLI/MCP runtime is a separate dependency.
REA 6.5.0 requires Node.js `^22.19.0 || ^24.11.0 || >=26.0.0` and npm.

```bash
npm install --global rea-agents@6.5.0
rea setup --client codex --skill=false --dry-run --json
# Review the plan, then apply within your authorized installation scope:
rea setup --client codex --skill=false --yes --json
rea doctor --client codex --json
```

`--skill=false` preserves this repository-managed skill. The setup command
registers the runtime in the user's Codex configuration and backs up existing
configuration. Restart/reconnect Codex to load newly registered MCP tools.

Linux static JavaScript analysis needs a procps-compatible `ps` but no native
decompiler. Native, Android, browser, and other analyses need their respective
providers; a missing optional provider does not establish that the whole
installation is broken. `doctor` can report a symlinked skill as `unmanaged`:
this is intentional for a repository-managed installation.

## Updates / 更新

此目录保留官方 skill 和参考文档，来源提交、npm 版本和许可证见
`UPSTREAM.json`。全局 skill 对当前机器、当前用户的 Codex 项目生效；
其他机器需要单独安装。MCP 配置更新后重启或重新连接 Codex。

Refresh the vendored files from a reviewed upstream revision, retain the license,
update `UPSTREAM.json`, and align the installed runtime with the corresponding
release. Repository main can describe features newer than the published npm
package; actual connected tool schemas take precedence.
