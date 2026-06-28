---
name: paper-read
description: >
  精读一篇研究论文（URL 或本地 PDF 路径），输出结构化的七问分析笔记：
  任务/问题、技术挑战与传统方法的不足、方法模块（动机/原理/有效性）、
  方法如何解决挑战、实验设计与指标、局限性、未来工作。
  触发词：/paper-read、paper-read、读论文、精读论文、paper review、paper analysis、
  论文精读、解析论文、summarize paper、paper 7Q、七问论文。
argument-hint: "<论文 URL 或本地 PDF 路径>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch
---

# paper-read Skill — 论文七问精读

对一篇论文做结构化深度精读，输出统一的 **七问笔记**（Q1–Q7）。
输入可以是 **arXiv / OpenReview / 出版商 URL**，也可以是 **本地 PDF 路径**。
输出为 Markdown 文档，位于论文所在目录或用户指定位置。

## 使用方式

```
/paper-read https://arxiv.org/abs/2405.12345
/paper-read /path/to/paper.pdf
/paper-read ./downloads/SomePaper.pdf "帮我顺便提炼一下可以借鉴的地方"
```

自然语言也行：
- "帮我读一下这篇论文：https://arxiv.org/pdf/2410.01234"
- "精读 /data/papers/foo.pdf，按七问输出"
- "/paper-read arxiv.org/abs/xxxx 中文输出"

**参数解析规则**：
- 第一个空白前的 token = 目标（URL 或路径）
- 其余内容 = 用户补充需求（可选），原样并入笔记的"读者补充问题"小节

---

## 必答的七个问题（严格覆盖，缺一不可）

输出 Markdown 必须按以下 7 个二级标题、以下顺序给出。**不要合并、不要改名**。

1. **Q1 — 这篇论文打算解决什么任务或问题？**
2. **Q2 — 这篇论文想解决的 technical challenge 有哪些？传统方法为什么不能解决这些 challenge？**
   → 必须 *分点列出*（每个 challenge 独立编号），每点都要显式说明 "传统方法失败的原因"。
3. **Q3 — 这篇论文的方法是什么样的，包含哪些模块？**
   → 必须 *分模块列出*，每个模块给三个子项：
      - **3.a 动机**（motivation：为什么需要这个模块）
      - **3.b 原理**（how：数学公式 / 核心流程 / 架构细节）
      - **3.c 为什么有效**（why it works：直觉 + 支撑证据，如消融、理论分析）
3. **Q4 — 文中提出的模块是怎么解决论文强调的 challenge 的？**
   → 建议用 *映射表*：`Challenge i → Module j → 如何解决`。
4. **Q5 — 作者是如何设计实验的？在什么数据集上、用什么指标评估？**
   → 至少覆盖：数据集清单、指标清单、baselines、主结果表概述、消融实验、（如有）定性可视化。
5. **Q6 — 这篇论文有哪些 limitation？**
   → 既包含作者自陈的 limitation，也包含你作为 reviewer 能观察到的问题（方法假设、数据规模、指标单一性、泛化性等）。
6. **Q7 — 这篇论文可能有哪些方向的 future work？**
   → 既包含作者提出的 future work，也包含你基于 Q6 延伸出的机会点。**优先给可以快速复现/立刻能做的方向**。

> **IRON RULE**：所有结论必须可追溯到论文具体章节 / 公式编号 / 图表编号。引用格式 `§3.2`、`Eq. (4)`、`Table 2`、`Fig. 3`。
> **IRON RULE**：不要编造实验数字或引用；查不到就写 "未在原文中找到"。

---

## 执行流程

### Phase 0 — 识别输入类型

根据 `$ARGUMENTS` 第一个 token：

| 输入形态 | 判定规则 | 加载方式 |
|---------|---------|---------|
| `http(s)://...pdf` 或 arXiv `abs/`/`pdf/` | 以 `http` 开头 / 含 `arxiv.org` | 先用 `WebFetch` 抓取 **摘要页** 得到题目+作者+摘要；再尝试 `curl -L -o <tmp>.pdf <pdf_url>` 下载 PDF 走本地路径 |
| 本地 PDF (`*.pdf`) | 路径以 `/` 开头或以 `./` 开头且文件存在 | 直接用 `Read` 工具（PDF > 10 页必须用 `pages` 参数分段读） |
| OpenReview / 其它 HTML | 不是 `.pdf` 也不是本地文件 | `WebFetch` 读 HTML，抓正文或追 PDF 链接 |
| 含空格 / 非 URL 非文件 | 其余 | **停下来**用 `AskUserQuestion` 追问准确路径 |

**arXiv URL 规范化**：
- `arxiv.org/abs/XXXX.YYYYY` → PDF: `https://arxiv.org/pdf/XXXX.YYYYY.pdf`
- `arxiv.org/pdf/XXXX.YYYYY` → 直接下载
- 带版本号 `v1/v2` 的也保留

**PDF 分段读取**（> 10 页必须分段）：
```
Read(file_path=..., pages="1-10")
Read(file_path=..., pages="11-20")
...
```
每 20 页一批，覆盖到参考文献前结束。

### Phase 1 — 元数据抽取（必做，最先做）

建立 `paper_meta`：
- 题目、作者、机构
- 会议 / 期刊 / 年份 / arXiv ID
- Abstract 原文（英文原文，不翻译）

这一步先做的原因：后面每次引用段号、图号都要回到这份 anchor。

### Phase 2 — 全文分段摘要

按节逐段提取要点（Introduction、Related Work、Method、Experiments、Discussion、Conclusion、Appendix）。每节产出一个 2–5 条 bullet 的压缩版。**这一步的产物不进入最终交付**，是 Q1–Q7 的素材。

### Phase 3 — 回答七问（按上面结构化输出）

严格按 Q1–Q7 的模板填写。空白字段用 `未在原文中找到` 或 `作者未明确说明`。

### Phase 4 — 交叉校验（防幻觉）

- 每个方法模块至少引用一个原文章节号 / 公式号。
- 每个数据集 / 指标必须能在实验章节找到对应表格。
- 对可疑的创新性表述，用 `WebSearch` 抽一次同领域 prior work，交叉印证"是否真的新"。

### Phase 5 — 写出 Markdown

输出位置（按优先级）：
1. 如果用户指定了输出路径 → 用指定路径
2. 本地 PDF 输入 → `<pdf 同目录>/<pdf_basename>.read.md`
3. URL 输入 → 当前工作目录 `./paper_read_<arxiv_id_or_slug>.md`

输出文件命名示例：
- `2405.12345.read.md`
- `DiffusionXYZ.read.md`

---

## 输出模板（交付物）

```markdown
# Paper Read — <Paper Title>

- **Authors / Affiliation**：...
- **Venue / Year**：...
- **Link**：<原始输入链接或本地路径>
- **Abstract**（原文）：...
- **Reader's extra questions**：<如果用户在 $ARGUMENTS 里追加过问题>

---

## Q1 — 这篇论文打算解决什么任务或问题？

<任务定义 + 应用场景 + 为什么重要。必须引用 §1 / Abstract。>

---

## Q2 — Technical challenges 与传统方法的不足

| # | Challenge | 传统方法 | 传统方法为什么失败 |
|---|-----------|---------|------------------|
| 1 | ... | ... | ... |
| 2 | ... | ... | ... |
| 3 | ... | ... | ... |

---

## Q3 — 方法模块

### Module 1 — <名字>（对应 §x.x / Fig. y）

- **3.a 动机**：...
- **3.b 原理**：
  - 输入 / 输出
  - 关键公式 `Eq. (n)`
  - 架构细节
- **3.c 为什么有效**：...（理论论证 + 消融实验 Table z 支撑）

### Module 2 — ...

（每个模块都要有三段式 3.a / 3.b / 3.c，缺一不可）

---

## Q4 — 模块 × Challenge 映射

| Challenge | 由哪个 Module 解决 | 如何解决 |
|-----------|------------------|---------|
| Challenge 1 | Module A | ... |
| Challenge 2 | Module B + C | ... |

---

## Q5 — 实验

- **数据集**：... （规模 / 划分 / 是否标准 benchmark）
- **指标**：... （定义 + 越大越好/越小越好）
- **Baselines**：...
- **主结果**：Table x — <一句话归纳，并给出关键数字>
- **消融**：Table y — 逐项说明 "去掉哪个模块掉多少点"
- **定性**：Fig. z — ...
- **训练/资源细节**：GPU 型号 / 训练时长 / 超参（如原文给出）

---

## Q6 — Limitations

- **作者自述**：...
- **Reader additional**（我作为审稿人看到的问题）：
  - 方法假设层面：...
  - 数据层面：...
  - 指标层面：...
  - 泛化性：...

---

## Q7 — Future Work

- **作者 proposed**：...
- **Reader extension**（基于 Q6 的延伸机会）：
  - 立刻能做：...
  - 需要较大工程量：...
  - 长线研究方向：...

---

## Reviewer verdict（可选）

- **Novelty**：高 / 中 / 低 — 原因
- **Technical soundness**：...
- **Clarity**：...
- **Reproducibility**：是否放代码 / 数据，见 §x
- **一句话评价**：...
```

---

## Anti-Patterns（严禁出现）

| # | Anti-Pattern | 正确做法 |
|---|-------------|---------|
| 1 | 跳过 Q3 的 3.a/3.b/3.c 三段式，直接堆模块介绍 | 每个模块必须三段式 |
| 2 | 不引用章节号 / 公式号 / 图表号 | 凡涉及方法或实验的陈述，都要有 anchor |
| 3 | 把 Introduction 的 claim 直接抄到 Q5 当实验结果 | Q5 必须来自 Experiments 章节原始数据 |
| 4 | 用 "该方法效果显著" 这类空话 | 必须给出具体数字（如 +2.3 mAP on COCO） |
| 5 | 编造论文没提过的 baseline / dataset | 没写就写 "未在原文中找到" |
| 6 | Q6 只抄作者自述 | 必须同时给 Reader additional 观察 |
| 7 | Q7 只抄作者 proposed | 必须同时给 Reader extension，并区分时间成本 |
| 8 | PDF 超过 10 页却只读前几页 | 强制分段读，覆盖到 References 之前 |

---

## 失败路径

| 场景 | 处理 |
|------|------|
| URL 无法访问（403 / 404） | 提示用户提供本地 PDF 或换镜像（arxiv.org → export.arxiv.org） |
| PDF 加密 / 扫描件无文字层 | 提示用户提供可搜索的 PDF，或手动粘贴正文 |
| 非英文论文 | 照常按七问输出，笔记用中文，引用原文术语 |
| 文件不存在 | 用 `AskUserQuestion` 让用户提供正确路径 |
| 方法部分过于复杂，七问笔记会 > 3000 字 | 在 Q3 用分节，保留主干模块，细节放到 References 小节 |

---

## 输出语言

跟随用户语言。默认中文；用户若在 `$ARGUMENTS` 里带英文或明确要求 "English notes" 则用英文。
专业术语（loss、attention、diffusion、backbone、等）保持英文原词。

---

## Version Info

| Item | Content |
|------|---------|
| Skill Version | 1.0.0 |
| Last Updated | 2026-05-08 |
| Trigger | `/paper-read`, `paper-read`, 读论文, 精读论文 |
