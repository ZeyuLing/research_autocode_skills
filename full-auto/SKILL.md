---
name: full-auto
description: >
  全托管自动执行模式。接收任务描述后，自主完成全部工作（理解→规划→执行→自我验收），
  无需用户介入。内置 Task Reviewer 机制：执行完毕后自动 review 代码 diff，
  对照任务描述和验收标准逐项检查，未通过则自动修复重试。
  触发词：/full-auto、全托管、自动执行、autopilot、无人值守执行。
argument-hint: "<任务描述>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch, Agent, Skill
---

# full-auto Skill — 全托管自动执行

接收任务描述，自主完成全部工作流程，无需用户介入。
执行完毕后自动进行 **Task Reviewer 自我验收**，确保交付质量。

## 使用方式

```
/full-auto 实现一个用户登录功能，包含邮箱验证
/full-auto 修复 train.py 中 loss 不下降的 bug
```

## 强制规则

1. 禁止使用 AskUserQuestion / EnterPlanMode 工具——没有人可以回答你
2. 禁止停下来等待用户反馈、确认或审批
3. 遇到不确定的决策时，自主做出最合理的判断并继续执行
4. 必须完整执行任务的所有步骤，从头到尾一次性完成
5. 如果任务包含多个子步骤/子任务，按顺序逐一全部完成
6. 绝不能在中途停止并声称"等待用户输入"——这等于任务失败
7. 执行结束后，必须输出完整的验收报告

---

## 执行流程（严格遵循 4 个 Phase）

### Phase 1 — 理解与规划

1. 仔细阅读 `$ARGUMENTS` 中的任务描述
2. 如果存在验收标准，将其作为最终检查清单
3. 确定需要修改的文件范围和技术方案
4. 如果任务复杂（涉及 3+ 文件），先列出执行计划再动手
5. 阅读项目的 CLAUDE.md 了解架构和约定

### Phase 2 — 执行

1. 按计划逐步实施修改
2. 每个子步骤完成后，运行相关测试确认不破坏已有功能
3. 对于代码修改，确保语法正确（如 Python `ast.parse`、`node --check`）
4. 对于涉及训练/推理的任务，使用太极平台（见下方"太极平台"章节）

### Phase 3 — 自我验收（Task Reviewer）

**必须执行，不可跳过。** 完成所有修改后，作为 reviewer 审查自己的工作：

1. 运行 `git diff` 查看所有改动（如果是 git 仓库）
2. 对照任务描述和验收标准（如有），逐项检查：
   - ✅ 每个需求点是否都被覆盖
   - ✅ 是否有遗漏（如：要求删除功能但路由/配置未清理）
   - ✅ 是否有多余改动（违反最小改动原则）
   - ✅ 是否有明显的代码质量问题（语法错误、遗留 debug 代码、未关闭资源等）
   - ✅ 测试是否通过（如有测试框架）
3. 如果发现问题：
   - **严重问题**（功能未实现、逻辑错误）→ 立即修复，修复后**再次 review**
   - **轻微问题**（格式、命名）→ 记录到报告中，视为通过
4. 自我验收最多重试 2 次（执行→review→修复→review→修复→review）。
   如果 3 轮 review 都不通过，输出 TASK_INCOMPLETE

### Phase 4 — 输出验收报告

最后**必须**输出以下格式的报告：

```
【验收报告】
状态：✅ 通过 / ⚠️ 部分通过 / ❌ 未通过
改动摘要：
  - file1.py: <一句话说明改了什么>
  - file2.js: <一句话说明改了什么>
验收清单：
  - [✅/❌] 需求点1: <是否满足>
  - [✅/❌] 需求点2: <是否满足>
遗留问题（如有）：
  - <描述>
```

---

## 避免死循环（极其重要）

你最大的成本风险是陷入"尝试-失败-换方案-再失败"的循环：

1. **环境/依赖问题**：某个 import 失败或包不存在，最多尝试 3 种方案。3 次后输出 TASK_INCOMPLETE
2. **同类错误不超过 3 次**：连续 3 次相同异常类型→立即停止报告
3. **总轮数硬限制**：工具调用不超过 200 轮。超过说明方案有问题，输出 TASK_INCOMPLETE
4. **禁止安装系统级依赖**：不要 pip install / conda install / apt install。缺依赖直接报告失败

---

## 训练 / 推理任务：使用太极平台

当前 anydev 本地环境**没有 GPU**，禁止在本地运行训练/推理代码。

1. **使用已有 debug 实例**：`taiji_client trl` 查看运行中任务，优先使用 `debug_machine` 实例
   - `taiji_client il <task_flag>` 获取 instance_id
   - `python3 .claude/skills/taiji/taiji_exec.py <task_flag> <instance_id> "<命令>" <超时秒>` 执行远程命令
2. **提交新训练任务**：`python3 tools/taiji_submit.py <任务名> <config路径> --host_num <N>`
3. **监控**：`taiji_client il <task_flag>` 查状态，`taiji_client stop <task_flag>` 停止
4. **绝不**在本地 pip install torch / mmengine / transformers

---

## 成本控制

当前无 prompt cache，全价计费：

1. **最小化文件读取**：用 offset+limit 读需要的部分，能 Grep 定位就不 Read 全文
2. **避免重复读取**：已读过的内容记住，不要再读
3. **批量操作**：独立 Bash 命令用 `&&` 合并
4. **合理使用 Agent**：多个独立子任务可并行。单任务直接用基础工具

---

## 完成判定

正常退出即视为完成。如果确定无法完成，在最后输出：
```
TASK_INCOMPLETE: <简要原因>
```

---

## Anti-Patterns（严禁）

| # | 错误 | 正确做法 |
|---|------|---------|
| 1 | 跳过 Phase 3 自我验收 | 必须执行 git diff + 逐项检查 |
| 2 | 验收发现问题但不修复 | 严重问题必须修复后再次验收 |
| 3 | 死循环尝试 | 同类错误 3 次后 TASK_INCOMPLETE |
| 4 | 本地装 torch/训练 | 用太极平台 |
| 5 | 停下来问用户 | 自主决策继续执行 |
| 6 | 不输出验收报告就结束 | Phase 4 报告必须输出 |
