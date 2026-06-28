# 7Q 输出模板（Reviewer 精读版）

> 复制这个模板，按顺序填满。所有 `<...>` 都是占位符；所有 anchor (§、Eq.、Table、Fig.) 必须回指原文。

```markdown
# Paper Read — <Paper Title>

- **Authors / Affiliation**：
- **Venue / Year**：
- **Link**：
- **Abstract**（原文）：
- **Reader's extra questions**：

---

## Q1 — 这篇论文打算解决什么任务或问题？

**任务定义**：（formal task definition；输入→输出）
**应用场景**：
**为什么重要**：
**引用**：§1, Abstract

---

## Q2 — Technical Challenges 与传统方法的不足

| # | Challenge | 传统方法 | 传统方法为什么失败（Root cause） | 原文 anchor |
|---|-----------|---------|-------------------------------|-----------|
| 1 |           |         |                               | §1 / §2   |
| 2 |           |         |                               |           |
| 3 |           |         |                               |           |

---

## Q3 — 方法模块

> 每个模块严格三段式：3.a 动机、3.b 原理、3.c 为什么有效。

### Module 1 — <模块名>（§x.x, Fig. y）

- **3.a 动机**：为什么需要这个模块？它回应的是 Q2 的哪个 challenge？
- **3.b 原理**：
  - 输入：
  - 输出：
  - 关键公式：`Eq. (n)`
  - 架构细节 / 数据流：
  - 训练目标 / loss：
- **3.c 为什么有效**：
  - 直觉：
  - 理论论证（如有）：
  - 实证支撑（Table z / Fig. w 的消融）：

### Module 2 — <模块名>（§x.x）

- 3.a 动机：
- 3.b 原理：
- 3.c 为什么有效：

（按需继续 Module 3、Module 4 …）

---

## Q4 — Module × Challenge 映射

| Challenge（来自 Q2） | 由哪些 Module 解决 | 具体是怎么解决的 |
|-------------------|------------------|-----------------|
| Challenge 1       | Module A         |                 |
| Challenge 2       | Module B + C     |                 |
| Challenge 3       | Module A + D     |                 |

---

## Q5 — 实验

**数据集**：
| 数据集 | 规模 | 划分 | 是否 benchmark | 用途 |
|-------|------|------|---------------|------|
|       |      |      |               |      |

**指标**：
| 指标 | 定义 | 越大越好 / 越小越好 |
|-----|-----|-------------------|
|     |     |                   |

**Baselines**：

**主结果**（对应 Table x）：
- 最好方法：... （XX on <metric>）
- 相较 SOTA 提升：+ ... on <metric>

**消融**（对应 Table y）：
- 去掉 Module A：下降 ...
- 去掉 Module B：下降 ...

**定性结果**：Fig. z — （一句话归纳）

**训练与资源**：
- GPU：
- 训练时长：
- 关键超参：
- Batch size / 优化器：

---

## Q6 — Limitations

**作者自述**（§ 对应章节）：
- …

**Reader additional**（作为 reviewer 看到的问题）：
- 方法假设层面：
- 数据规模与多样性：
- 指标单一性 / 是否过拟合某一指标：
- 泛化性（跨域 / 跨尺度 / 跨模态）：
- 公平性 / 鲁棒性：
- 计算成本与可部署性：

---

## Q7 — Future Work

**作者 proposed**：
- …

**Reader extension**（基于 Q6）：
- 🟢 立刻能做（一周内）：
- 🟡 需要较大工程量（1–3 个月）：
- 🔵 长线研究方向（半年以上）：

---

## Reviewer Verdict（可选，作者视角）

- **Novelty**：高 / 中 / 低 — 原因
- **Technical soundness**：
- **Clarity**：
- **Reproducibility**：代码 / 数据是否开源（见 §x / 项目主页）
- **一句话评价**：
```
