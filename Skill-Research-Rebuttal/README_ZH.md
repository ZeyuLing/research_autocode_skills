# skill-rebuttal

[English](README.md)

一个 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 技能插件，帮助研究者整理审稿意见、生成可视化思维导图，并撰写结构化的 rebuttal 回复。

## 功能概述

当你收到会议/期刊投稿的审稿意见后，这个 skill 会引导你完成三个阶段的工作流：

1. **整理 Review** — 解析审稿人原始评论，将 weakness 归入标准类别，识别每位审稿人的核心关注点
2. **生成思维导图** — 创建 draw.io 图表，以树状结构可视化展示所有审稿意见
3. **撰写 Rebuttal** — 按照经过实战检验的 rebuttal 写作原则，为每位审稿人起草专业的回复

你可以从任何阶段开始，取决于你的需求。

## 快速开始

### 安装 Rebuttal Skill

将 skill 目录复制到 Claude Code 的 skills 文件夹：

```bash
# 全局安装（所有项目可用）
cp -r skills/rebuttal ~/.claude/skills/rebuttal

# 或项目级安装
mkdir -p .claude/skills
cp -r skills/rebuttal .claude/skills/rebuttal
```

重启 Claude Code 会话，skill 会自动生效。

### 安装 draw.io Skill（可选，推荐）

Rebuttal skill 会生成 `.drawio` 文件。为了更好的图表质量，建议同时安装 [draw-io skill](https://github.com/softaworks/agent-toolkit/tree/main/skills/draw-io)：

```bash
git clone --depth 1 https://github.com/softaworks/agent-toolkit.git /tmp/agent-toolkit
cp -r /tmp/agent-toolkit/skills/draw-io ~/.claude/skills/draw-io
rm -rf /tmp/agent-toolkit
```

### 在 IDE 中查看 draw.io 文件

你可以在 VS Code 或 Cursor 中直接查看和编辑生成的 `.drawio` 文件，只需安装 **Draw.io Integration** 扩展：

1. 打开 VS Code / Cursor
2. 进入扩展商店（`Ctrl+Shift+X` / `Cmd+Shift+X`）
3. 搜索 **"Draw.io Integration"**（作者 Henning Dieterichs）
4. 点击安装

安装后，直接打开任何 `.drawio` 文件即可在编辑器中看到交互式图表。

### 使用方法

将审稿意见粘贴到 Claude Code 中，描述你的需求即可：

```
# 全流程
我投了CVPR，收到了3个reviewer的意见，帮我做rebuttal。
[粘贴审稿意见]

# 仅整理review
帮我整理这些review
[粘贴审稿意见]

# 仅生成思维导图
帮我把这些review整理成drawio图

# 仅写rebuttal
我已经整理好了review，帮我写rebuttal回复
```

## 完整示例

以下是全流程的具体示例。给定这些审稿意见：

**输入：**

```
Reviewer 1 (Score: 5, Confidence: 4):
Weaknesses: The method is a straightforward combination of NeRF and diffusion model.
The novelty is limited as similar integration has been explored. Experiments are only
conducted on synthetic datasets, which limits the practical value of this work.

Reviewer 2 (Score: 6, Confidence: 3):
Weaknesses: The writing is generally clear, but the paper lacks comparison with the
recent Method-X (CVPR 2025). The ablation study is insufficient — only one component
is ablated while the method has three major modules.

Reviewer 3 (Score: 4, Confidence: 5):
Weaknesses: The assumption that scenes are static is unrealistic for most real-world
applications. The improvement over the baseline is only 0.5dB PSNR, which is marginal.
```

**第一阶段输出 — Review 整理：**

```markdown
## Review 整理

### 审稿人 1 (分数: 5; Confidence: 4)
| 类别 | 具体问题 | 重要程度 |
|------|---------|---------|
| Insufficient Contribution | Straightforward combination of NeRF + diffusion, novelty limited | **重点** |
| Insufficient Evaluation | Only synthetic datasets, no real-world experiments | 普通 |

### 审稿人 2 (分数: 6; Confidence: 3)
| 类别 | 具体问题 | 重要程度 |
|------|---------|---------|
| Insufficient Evaluation | Missing comparison with Method-X; ablation only covers 1 of 3 modules | **重点** |

### 审稿人 3 (分数: 4; Confidence: 5)
| 类别 | 具体问题 | 重要程度 |
|------|---------|---------|
| Method Design Flaws | Static scene assumption is unrealistic | **重点** |
| Weak Experimental Results | Only 0.5dB PSNR improvement over baseline | 普通 |
```

**第二阶段输出 — draw.io 思维导图**（`.drawio` 文件，树状结构，重点问题标红）

**第三阶段输出 — Rebuttal 草稿：**

```markdown
## Response to Reviewer 1

We thank Reviewer 1 for the constructive feedback.

### [R1-W1] Novelty of NeRF + Diffusion Integration

Our method differs from naive combinations in three key aspects.
First, we introduce [specific technique] that enables [specific capability],
which prior NeRF-diffusion works cannot achieve (see ablation in Table 3).
Second, ...

### [R1-W2] Evaluation on Real-World Data

We have conducted additional experiments on [real-world dataset].
Results show our method achieves [X] PSNR / [Y] SSIM, outperforming
the baseline by [Z]dB. We will include these results in the revision.
```

## Weakness 分类体系

Skill 将审稿意见归入六个标准类别：

| 类别 | 说明 |
|------|------|
| **Insufficient Contribution** | 创新性不足 — 技术已被充分探索、改进可预见、方法太直接 |
| **Unclear Writing** | 写作不清晰 — 缺少技术细节、不可复现、缺少 motivation |
| **Weak Experimental Results** | 实验结果不足 — 提升幅度小、效果不够有说服力 |
| **Method Design Flaws** | 方法设计缺陷 — setting 不实际、技术缺陷、鲁棒性差 |
| **Insufficient Evaluation** | 评测不充分 — 缺少 ablation、baseline、metric 或数据集 |
| **Justification Breakdown** | 审稿人给分理由的拆解分析 |

## Rebuttal 写作原则

Skill 遵循以下核心原则，源自资深研究者的实战经验：

1. **Reviewer 要啥，就给啥** — 要 ablation 就给 ablation，要对比就给对比，不要争论请求是否合理
2. **不要引入新问题** — rebuttal 中每一句新的论断都可能成为新的攻击面，保持聚焦
3. **正面回答** — 每个回复直接切入审稿人的问题，让他们一看就知道你在回答什么
4. **可略读、自包含** — 审稿人不会重新看自己的 review，每个回复需独立可理解
5. **聚焦重点问题** — 每个审稿人只有 1-2 个核心关注点决定分数，务必回答到位

## 项目结构

```
skill-rebuttal/
├── README.md                              # English documentation
├── README_ZH.md                           # 本文件
├── LICENSE                                # MIT 协议
├── skills/
│   └── rebuttal/
│       ├── SKILL.md                       # Skill 主指令文件
│       ├── references/
│       │   ├── drawio-template.md         # draw.io XML 模板规范
│       │   └── rebuttal-guide.md          # Rebuttal 写作策略指南
│       └── assets/
│           └── rebuttal-template.drawio    # 原始 draw.io 模板
└── docs/
    └── rebuttal-methodology.md            # 方法论源文档
```

## 免责声明

本项目仅作为 rebuttal 回复的**辅助工具**，生成的内容仅供参考和起草使用。请**勿**将输出内容直接作为正式 rebuttal 提交，务必与合作者一起审阅、修改和确认所有内容后再提交。

## 致谢

- Rebuttal 方法论基于 [pengsida/learning_research](https://github.com/pengsida/learning_research)
- 写作策略参考 [Devi Parikh 的 rebuttal 指南](https://deviparikh.medium.com/how-we-write-rebuttals-dc84742fece1) 和 [SIGGRAPH rebuttal 指南](https://research.siggraph.org/blog/guides/writing-a-rebuttal-for-siggraph/)

## 协议

[MIT](LICENSE)
