<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/research-autocode-toolkit-logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/research-autocode-toolkit-logo.png">
    <img src="docs/assets/research-autocode-toolkit-logo.png" alt="Research AutoCode Toolkit 标志" width="170">
  </picture>
</p>

<h1 align="center">Research AutoCode Toolkit</h1>

<p align="center">
  <strong>面向 Agent 辅助科研的可组合、证据可追溯工作流。</strong>
</p>

<p align="center">
  覆盖文献发现、idea 打磨、实验规划、论文写作、科研作图、<br>
  对抗性评审与 rebuttal。
</p>

<p align="center">
  <a href="README.md">English</a>
  ·
  <a href="README.zh-CN.md"><strong>简体中文</strong></a>
</p>

<p align="center">
  <a href="https://github.com/ZeyuLing/research_autocode_skills/stargazers"><img src="https://img.shields.io/github/stars/ZeyuLing/research_autocode_skills?style=flat-square&amp;color=4f46e5" alt="GitHub stars"></a>
  <a href="https://github.com/ZeyuLing/research_autocode_skills/commits/main"><img src="https://img.shields.io/github/last-commit/ZeyuLing/research_autocode_skills?style=flat-square&amp;color=0f766e" alt="最近提交"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/docs-English%20%7C%20%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-d97706?style=flat-square" alt="文档语言：English 和简体中文"></a>
</p>

<p align="center">
  <a href="#why-this-toolkit">项目定位</a> ·
  <a href="#research-lifecycle">科研生命周期</a> ·
  <a href="#start-with-an-outcome">选择工作流</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#tool-map">工具地图</a> ·
  <a href="#contributing">参与贡献</a>
</p>

---

<a id="why-this-toolkit"></a>

## 为什么需要这个工具库

科研不是一串彼此孤立的 prompt。一个可靠的工作流需要随着项目推进，持续维持研究问题、来源证据、创新性论证、实验方案、论文叙事、视觉表达和评审反馈之间的一致性。

Research AutoCode Toolkit 围绕**科研结果**组织可复用的 `SKILL.md` 工作流，而不是平铺 Agent 命令。每个组件既可以独立使用，也可以组合成更大的科研管线。

| 层次 | 职责 | 示例 |
|---|---|---|
| **端到端编排工作流** | 协调多个科研阶段、保存状态并执行质量门禁 | [idea2paper](idea2paper/)、[academic-pipeline](academic-research-skills/academic-pipeline/)、[autorun](autorun/) |
| **单点科研工具** | 解决文献检索、论文修改、科研作图、排版修复或调试等边界明确的问题 | [ai-literature-survey](ai-literature-survey/)、[paperjury](paperjury/)、[latex-float-layout](latex-float-layout/)、[autodebug](autodebug/) |
| **项目适配器** | 连接特定数据库、数据管线或存储服务 | [mysql-motiondata](mysql-motiondata/)、[query-motion-database](query-motion-database/)、[sync-ceph-data](sync-ceph-data/) |

四项共同约束贯穿整个工具库：

- **Evidence / 证据**——重要判断应能追溯到论文、实验、代码或数据。
- **Alignment / 对齐**——论断、方法、实验、图表和正文叙事应互相支撑。
- **Validation / 验证**——交付物应经过测试、独立评审、编译或渲染后检查。
- **Provenance / 来源记录**——实测事实、预测值、未验证方案和外部来源必须保持可区分。

> [!NOTE]
> 这是一个按组件组织的科研工具集合，不是单体软件包。不同组件的运行环境、依赖、来源、验证覆盖和许可证并不统一。

<a id="research-lifecycle"></a>

## 科研生命周期

```mermaid
flowchart LR
    A["发现问题<br/>论文 · 证据 · 开放问题"] --> B["形成研究<br/>定位 · 创新 · 方法"]
    B --> C["验证研究<br/>实验 · 代码 · 数据"]
    C --> D["表达研究<br/>论文 · 图表 · 排版"]
    D --> E["压力测试<br/>评审 · 修改 · Rebuttal"]
    E -. "新证据与新问题" .-> A
```

工具库支持的是一个持续循环，而不是把论文发表当作线性流程的终点。

<a id="start-with-an-outcome"></a>

## 从科研结果开始

| 你希望得到什么 | 推荐入口 | 典型交付物 |
|---|---|---|
| 把早期 idea 推进为实验就绪的论文骨架 | [idea2paper](idea2paper/) | 会议模板、LaTeX 项目、文献语料、细化方法、实验矩阵、图表和显式验证 TODO |
| 建立可审计的“研究到写作”流程 | [academic-research-skills](academic-research-skills/) | 研究综合、论文、完整性检查、多视角评审和修订 |
| 梳理 prior art 或修复 Related Work | [ai-literature-survey](ai-literature-survey/) | 高召回、来源可审计的文献语料与覆盖报告 |
| 持续追踪某个方向的重要论文 | [track-ai-papers](track-ai-papers/) | 经过筛选和排序的研究雷达摘要 |
| 深入理解一篇论文 | [nature-paper-card](nature-paper-card/) 或 [paper-read](.claude/skills/paper-read/) | 证据链接的 Paper Card 或结构化七问精读笔记 |
| 对 CS 论文做投稿前压力测试和修改 | [paperjury](paperjury/) | reviewer 视角问题、裁决记录和受控 LaTeX 修改 |
| 对中国计算机学科硕博学位论文进行盲审预检 | [thesis_review](thesis_review/) | 3/5 位独立审稿意见、主席裁决、全文身份泄露与逐物理页分页检查、可执行修改台账 |
| 修复 LaTeX 图表分布与分页 | [latex-float-layout](latex-float-layout/) | 基于编译和检查的 float 重排与分页修复 |
| 准备 author response | [Skill-Research-Rebuttal](Skill-Research-Rebuttal/) | 审稿意见图谱、回复策略和 rebuttal 草稿 |
| 迭代诊断科研代码问题 | [autodebug](autodebug/) | 假设驱动的调试闭环和持久化观测 |
| 批量执行科研 TODO | [autorun](autorun/) | 依赖感知执行、任务状态和 reviewer 风格验收 |

<a id="quick-start"></a>

## 快速开始

### 1. 克隆工具库

```bash
git clone https://github.com/ZeyuLing/research_autocode_skills.git
cd research_autocode_skills
```

### 2. 选择组件

从上面的科研结果表选择入口，然后完整阅读组件的 `SKILL.md` 或 README。若组件同时包含脚本、参考资料、素材、模板或测试，不要只复制一个 `SKILL.md`。

### 3. 安装到你的 Agent 环境

安装范围以组件为单位。常见位置如下：

| 运行环境 | 常见目标目录 | 重要说明 |
|---|---|---|
| Codex | `$CODEX_HOME/skills/<component>` | `imagegen` 等由运行环境提供的系统 skill 必须单独可用 |
| Claude Code | `.claude/skills/<component>` | 部分工具包已经带有 `.claude/skills` 目录结构 |
| Cursor、Gemini、OpenCode 等 | 遵循组件自己的 README | 本仓库不同组件的平台支持并不统一 |

安装一个独立组件的示例：

```bash
# Codex 示例（先设置 CODEX_HOME）
mkdir -p "$CODEX_HOME/skills"
cp -R ai-literature-survey "$CODEX_HOME/skills/ai-literature-survey"

# Claude Code 项目示例
mkdir -p .claude/skills
cp -R autodebug .claude/skills/autodebug
```

Codex 的 PowerShell 示例：

```powershell
if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) { throw '请先设置 CODEX_HOME。' }
$skillRoot = Join-Path $env:CODEX_HOME 'skills'
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -Recurse -Force ai-literature-survey (Join-Path $skillRoot 'ai-literature-survey')
```

[academic-research-skills](academic-research-skills/)、[Skill-Research-Figure](Skill-Research-Figure/) 和 [Skill-Research-Rebuttal](Skill-Research-Rebuttal/) 等 bundle 有各自的安装说明。应保留它们原有的目录结构，而不是把内部文件拍平。

### 4. 只安装当前组件需要的依赖

仓库有意不提供根级 `pip install` 或 `npm install` 命令。组件级依赖示例：

- [idea2paper](idea2paper/)——Python 3.10+、`pdfplumber`、LaTeX/PDF 工具、`ai-literature-survey`、`paperjury` 和 Codex 系统 `imagegen`；
- [paperjury](paperjury/)——使用自己的 Node.js/工具链依赖；
- [image-to-editable-ppt-skill](image-to-editable-ppt-skill/)——使用自己的 Python CLI 环境；
- [Skill-Research-Figure](Skill-Research-Figure/)——仅在选择对应路径时需要 LaTeX/TikZ 或 Blender。

如果缺少强依赖，工作流应报告具体缺口，而不是静默替换为语义不同的工具。

### 5. 直接描述科研目标

```text
用 idea2paper 把这个 motion generation idea 写成实验就绪的论文骨架。
调研显式动作规划与 text-to-motion 的相关工作，并记录来源和代码开放状态。
精读这篇论文，梳理每个模块解决的 challenge 及其证据。
对这个 CVPR LaTeX 项目做投稿前对抗性评审，并应用安全修改。
修复附录图表扎堆和单栏大面积留白。
```

## 旗舰工作流

| 工作流 | 组合方式 | 设计目标 |
|---|---|---|
| **Idea → 论文骨架** | `idea2paper` → `ai-literature-survey` → Agent 讨论 → `imagegen` → `paperjury` → PDF/排版检查 | 生成带证据语料、方法论证、实验规划、图表和验证 TODO 的投稿导向草稿 |
| **证据 → 学术论文** | `deep-research` → `academic-paper` → 完整性检查 → `academic-paper-reviewer` → 修订 | 形成结构化研究综合与经过多轮评审的论文 |
| **投稿前加固** | `research-paper-writing` → `paperjury` → `latex-float-layout` | 加强论证、发现对抗性问题、实施受控修改并做渲染验证的排版修复 |
| **科研工程** | `generate-docs` / `autorun` → `autodebug` → 验收检查 | 建立项目上下文、依赖感知执行和证据驱动调试 |

预测实验数字不是实测结果。使用预测值的工作流必须将其绑定到显式替换 TODO；作者仍需亲自完成实验并在投稿前核验每一项论断。

<a id="tool-map"></a>

## 工具地图

<details open>
<summary><strong>文献、证据与研究发现</strong></summary>

| 组件 | 作用 |
|---|---|
| [track-ai-papers](track-ai-papers/) | 针对研究方向发现、筛选、排序和推送近期论文 |
| [ai-literature-survey](ai-literature-survey/) | 面向 AI 及相邻领域的高召回、来源可审计文献检索 |
| [paper-read](.claude/skills/paper-read/) | 单篇论文七问精读 |
| [nature-paper-card](nature-paper-card/) | 包含模块逻辑和结论边界的证据约束 16 节 Paper Card |
| [deep-research](academic-research-skills/deep-research/) | 多 Agent 深度研究、系统综述、事实核查与方法学设计 |

</details>

<details>
<summary><strong>Idea 打磨、论文写作与评审</strong></summary>

| 组件 | 作用 |
|---|---|
| [idea2paper](idea2paper/) | 将粗略 idea 编排为实验就绪的 LaTeX 论文骨架 |
| [academic-pipeline](academic-research-skills/academic-pipeline/) | 协调调研、写作、完整性检查、评审、修订与定稿 |
| [academic-paper](academic-research-skills/academic-paper/) | 论文起草、修订、摘要、引用检查和格式转换 |
| [academic-paper-reviewer](academic-research-skills/academic-paper-reviewer/) | 模拟多视角编辑与同行评审 |
| [research-paper-writing](research-paper-writing/) | 改善章节结构、段落流和论断—证据对齐 |
| [Research-Paper-Writing-Skills](Research-Paper-Writing-Skills/) | `research-paper-writing` 的跨平台独立分发包装 |
| [paperjury](paperjury/) | 直接修改或对抗性压力测试 CS 会议 LaTeX 论文 |
| [thesis_review](thesis_review/) | 按学校规则模拟中国计算机学科学位论文的 3/5 人独立审查与复审，并生成逐物理页及强制浮动命令审计台账 |
| [latex-float-layout](latex-float-layout/) | 重平衡 LaTeX 图表、空白和分页 |
| [Skill-Research-Rebuttal](Skill-Research-Rebuttal/) | 组织审稿意见并形成 author response |

</details>

<details>
<summary><strong>科研图表与成果展示</strong></summary>

| 组件 | 作用 |
|---|---|
| [gpt-image](gpt-image/) | Codex 系统 `imagegen` 的参考与提示层 |
| [Skill-Research-Figure](Skill-Research-Figure/) | 生成 TikZ pipeline 和基于 Blender 的 3D 科研图 |
| [drawio-figure-replicator](drawio-figure-replicator/) | 将参考图复刻为可编辑 draw.io 资产 |
| [image-to-editable-ppt-skill](image-to-editable-ppt-skill/) | 把图片式幻灯片或扫描 deck 重建为对象级可编辑 PowerPoint |
| [frontend-design](frontend-design/) | 构建科研主页、demo、Dashboard、poster 和交互展示 |

在 `idea2paper` 工作流内，其 `imagegen`-only 作图合同优先。独立作图任务可以根据交付格式选择 ImageGen、TikZ/Blender 或 draw.io。

</details>

<details>
<summary><strong>科研工程与 Agent 自动化</strong></summary>

| 组件 | 作用 |
|---|---|
| [autodebug](autodebug/) | 带持久化研究记录的假设驱动 ReAct 调试 |
| [autorun](autorun/) | 使用 SQLite 状态和验收评审调度、执行 TODO 队列 |
| [full-auto](full-auto/) | 对边界明确的任务执行规划、实现、自检和修复 |
| [generate-docs](generate-docs/) | 增量生成分层项目文档 |
| [pua](pua/) | 提供 Agent 主动性、失败恢复和多语言压力模式 |

训练和推理不绑定固定集群。工具应先检查当前环境；只有用户明确提供并授权外部计算后端时，才可以使用。

</details>

<details>
<summary><strong>项目专用数据适配器</strong></summary>

| 组件 | 适用范围 |
|---|---|
| [db-analyze](db-analyze/) | 分析特定 SQLite 布局的表、列和存储占用 |
| [mysql-motiondata](mysql-motiondata/) | 操作 HYMotion `hymotion_data` MySQL 数据库 |
| [query-motion-database](query-motion-database/) | 查看 HYMotion 管线漏斗、队列和完成状态 |
| [sync-ceph-data](sync-ceph-data/) | 通过指定存储 API 在 CEPH 路径间同步数据 |

这些适配器与具体环境绑定。使用前必须检查服务地址、路径、凭据、权限和写操作。

</details>

[nature-shared](nature-shared/) 包含 `nature-paper-card` 等工具复用的来源准备和证据处理代码，属于内部支持模块，不是独立入口。

## 工具如何组合

```text
编排器
  ├─ 单点科研工具
  ├─ 证据与产物存储
  ├─ 验证 / 评审门禁
  └─ 可选项目适配器
```

组合规则：

1. **依赖必须显式。** 编排器必须声明需要的工具。
2. **适配器必须按需启用。** 项目专用基础设施不能成为静默默认项。
3. **回退方案必须保持语义。** 如果替代会改变科研合同，应报告缺少依赖，而不是自动降级。
4. **产物必须可检查。** 来源、prompt、TODO、评审、图表和验证记录应与项目一起保存。
5. **外部写操作必须获得授权。** 发布、任务提交、数据库写入和数据移动都需要明确的用户范围和目标。

## 示例

| 方向 | 仓库示例 |
|---|---|
| 端到端学术工作流 | [academic-research-skills/examples](academic-research-skills/examples/) |
| 可编辑图形复刻 | [drawio-figure-replicator/examples](drawio-figure-replicator/examples/) |
| 论文对抗性评审 | [paperjury/samples/dogfood](paperjury/samples/dogfood/) |
| TikZ 与 Blender 科研作图 | [Skill-Research-Figure/examples](Skill-Research-Figure/examples/) |
| Rebuttal 组织 | [Skill-Research-Rebuttal/example](Skill-Research-Rebuttal/example/) |

示例属于各自组件，可能需要对应组件的运行环境或素材。

## 环境与兼容性

- 仓库没有统一的运行时或全局依赖锁。
- 组件元数据和 README 是平台支持、工具依赖和环境假设的事实来源。
- 本仓库同时包含 Codex 优先、Claude Code 优先和可移植的 prompt/workflow 工具包。
- Python、Node.js、LaTeX、Poppler、Blender、ImageGen、数据库或外部服务，仅由明确声明它们的组件使用。
- bundle 内部的文件、模板、脚本和参考资料都属于其运行合同。

采用组件前，请检查：

- `SKILL.md` front matter 和 allowed tools；
- README、requirements、package metadata 与环境变量；
- 是否进行外部读取或写入；
- 路径和服务是否与特定实验室或项目绑定；
- 许可证和上游来源。

## 质量与负责任使用

- **文献检索追求高召回，但不保证穷尽。** 重要引用应回到 primary source 核验。
- **生成正文是草稿，不是作者签字。** 论证、署名和最终投稿由作者负责。
- **预测结果是实验目标，不是测量值。** 在原始实验结果替换前必须保留显式 TODO。
- **对抗性评审是压力测试，不替代真实同行评审。**
- **渲染型产物需要渲染后检查。** 编译论文、查看 PDF，并在最终展示尺寸检查 Figure。
- **科研论断必须保持可证伪。** 工作流执行完成不能证明科学论断为真。

## 安全与内部基础设施

- 不要在公开提交中新增 API Token、SSH 密码、数据库口令或私有数据路径。
- 实验室适配器通过环境变量配置，运行时可能访问私有端点、路径或凭据；实际值不得进入提交或日志。
- 任何曾出现在历史版本中的疑似凭据都应视为已经泄漏：必须轮换、审计后续访问，并评估是否需要协同重写 Git 历史。
- 安装适配器前检查环境变量、endpoint、默认值、权限和写操作。
- 数据库、存储 API、计算后端和发布服务应使用最小权限。
- 任务提交、删除、取消、发布和数据覆盖属于外部状态变更，必须得到明确授权。

<a id="contributing"></a>

## 参与贡献

贡献应改善一个科研结果，而不是只增加一个 prompt 文件。新增组件应说明：

1. 它解决什么科研问题，可验证输出是什么；
2. 它属于编排器、单点工具、支持模块还是项目适配器；
3. 输入、输出、依赖、副作用和失败行为；
4. 用于验证的证据、测试、编译、渲染或评审；
5. 支持的运行环境和已知环境假设；
6. 来源、许可证和任何第三方素材；
7. 最小示例，以及必要时对本 README 任务地图的更新。

提交变更前，请删除密钥与私有数据，排除无关文件，并运行组件已有的检查。

## 来源与许可证

本仓库包含原创、改编、打包和 vendored 组件。**许可证以组件为单位。** 组件自己的许可证与来源声明优先于本 README。

当前可确认的组件许可证包括 MIT、Apache-2.0 和 CC BY-NC 4.0；若干组件目前没有显式许可证文件。没有显式许可证的组件不应被默认视为授予使用或再分发权利。

使用、修改、商业部署或再分发前，请检查对应组件目录。上游来源记录在组件 README、package metadata、许可证文件以及 [nature-paper-card/UPSTREAM.md](nature-paper-card/UPSTREAM.md) 等说明中。

## 反馈

当前仓库限制公众新建 Issue。外部贡献者可以从 fork 通过 [Pull Requests](https://github.com/ZeyuLing/research_autocode_skills/pulls) 提交范围明确的具体修复；目前不提供通用支持。请勿在公开 Pull Request 中披露凭据、私有端点或敏感科研数据。
