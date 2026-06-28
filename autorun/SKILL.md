---
name: autorun
description: >
  自动批量执行 TODO_LIST.md 中的待办任务。通过 SQLite 数据库管理任务队列，
  引入 Team Lead 智能调度：分析任务依赖关系，决定并行/串行执行策略。
  Task Analyst 子代理负责评估任务复杂度和拆分建议。
  Task Reviewer 子代理对完成的任务进行代码验收，检查 diff 是否满足需求。
  执行 subagent 通过任务 ID 直接获取任务，主会话统一更新 DB 状态。
  并行任务中某个失败不阻塞其他任务，最后统一汇报。
  当用户说"自动执行 TODO"、"批量处理 TODO"、"auto run"、"跑一下 TODO"、
  "帮我把 TODO 做了"、"执行待办"、"run todos"时触发。
  也适用于用户说"继续做 TODO"、"接着上次的 TODO"、"把剩下的任务做完"等场景。
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Agent
---

# autorun Skill（SQLite 版 — Team Lead 调度模式）

通过 SQLite 数据库精确管理任务队列。引入 **Team Lead** 智能调度角色，
分析所有待办任务的依赖关系，决定哪些可以并行、哪些必须串行。
**Task Analyst** 子代理评估每条任务的复杂度和涉及模块。
**Task Reviewer** 子代理对每条已完成任务进行代码验收，检查 diff 是否满足需求。
执行 subagent 通过任务 ID 获取任务，主会话统一更新 DB。

## 使用方式

- `/autorun` 或 `/autorun --all` — 执行所有未完成任务，自动连续运行直到完成
- `/autorun 3` — 最多执行 3 条任务后停止
- `/autorun --dry-run` — 查看待办任务数量和 Team Lead 分析结果，不实际执行
- 自然语言："帮我跑一下 TODO"、"自动执行待办任务"

根据 `$ARGUMENTS` 决定行为：
- 空 或 `--all` → 执行所有未完成任务，自动连续运行，不中途询问
- 数字 N → 最多执行 N 条后停止
- `--dry-run` → 只执行到 Phase 1（Team Lead 分析），展示调度计划，不执行

---

## 任务管理工具

所有任务管理通过 `task_manager.py` CLI 完成：

```bash
TM=".claude/skills/autorun/task_manager.py"
```

| 命令 | 作用 |
|------|------|
| `python $TM init` | 建库建表（幂等） |
| `python $TM sync --file TODO_LIST.md` | 增量同步 TODO_LIST.md → DB |
| `python $TM next` | 取一条 pending 任务（JSON），标记 in_progress |
| `python $TM peek` | 预览下一条 pending 任务（JSON），**不改变状态**，用于 dry-run |
| `python $TM get <id>` | 按 ID 获取任务详情（不改状态），供执行 subagent 使用 |
| `python $TM start <id>` | 标记指定任务为 in_progress，供主会话调度使用 |
| `python $TM list-pending` | 获取所有 pending 任务（**Team Lead 专用**） |
| `python $TM complete <id> --conclusion "..." --files '[...]' --notes "..."` | 标记完成 |
| `python $TM fail <id> --notes "..."` | 标记失败 |
| `python $TM retry <id>` | 重置为 pending |
| `python $TM decompose <id> --subtasks '<JSON array>'` | 拆解为子任务 |
| `python $TM count [--status pending]` | 返回数量（轻量，推荐） |
| `python $TM list` | 任务摘要（⚠️ **禁止在常规流程中使用**，仅调试用） |
| `python $TM export [--output FINISH_LIST.md]` | 导出完成记录 |

所有命令输出 JSON，便于精确解析。

---

## 文件约定

### TODO_LIST.md 格式

```markdown
- [ ] [模块标签] 任务描述
- [ ] [模块标签] 另一条任务
```

- `- [ ]` 表示未完成，待导入
- `- [>]` 表示已导入 DB，不再重复导入
- `- [x]` 表示 DB 中已完成
- 模块标签（如 `[前端]`、`[后端]`）是可选的，用于分类

### FINISH_LIST.md

由 `export` 命令自动生成，包含所有已完成任务的详细记录。

---

## 核心原则

### Team Lead 智能调度

不再串行逐条执行。由 Team Lead 分析所有待办任务的依赖关系，
决定并行/串行策略，提高执行效率。

### 最小改动原则

每条 TODO 只做完成该任务所必需的最少代码改动。不顺手重构，不添加额外功能，
不修改不相关的代码。

### 复杂任务拆解

判断一条任务是否"复杂"的标准：
- 需要修改 3 个以上文件
- 涉及多个独立的逻辑变更
- 改动之间没有强耦合关系

如果任务复杂，使用 `decompose` 命令拆解为 2-5 个子任务，然后重新调度。

### 上下文管理

每条任务通过 **Agent 工具派发给独立子代理（subagent）** 执行。
子代理拥有独立上下文窗口，任务间互不干扰，主会话只保留调度信息。

### 并行任务失败隔离

并行组中某个任务失败**不阻塞**其他独立任务继续执行。
依赖链中某个任务失败，该链条后续任务跳过。最后统一汇报所有结果。

### 任务验收机制

每条任务执行完成后，由 **Task Reviewer** 验收代码 diff，确保改动满足任务需求。
验收未通过的任务不会标记 complete，而是重新派发修复。
这避免了"任务标记完成但实际未完成"的问题。

---

## 执行流程

### Phase 0 — 初始化与同步

```bash
python $TM init
python $TM sync --file TODO_LIST.md
python $TM count --status pending
```

每次启动都执行：
1. `init` 确保数据库和表存在（幂等）
2. `sync` 检测 TODO_LIST.md 中的新增 `- [ ]` 行，导入 DB 后标记为 `- [>]`
3. `count` 查看待办数量（**不要用 `list`**，避免大量任务污染上下文）

### Phase 1 — Team Lead 分析（智能调度）

```bash
python $TM list-pending
```

1. 获取所有 pending 任务列表
2. 启动 **Team Lead Agent**（Plan 类型 subagent），传入：
   - `list-pending` 的全部任务 JSON
   - 项目 CLAUDE.md 的模块索引信息
3. Team Lead 内部对每个任务分发 **Task Analyst Agent**（Explore 类型 subagent，可并行最多 3 个）
4. Team Lead 汇总分析结果，输出调度计划：

```json
{
  "decompose": [{"id": 3, "subtasks": ["子任务1", "子任务2"]}],
  "chains": [[1, 5, 7]],
  "parallel": [2, 4, 6, 8]
}
```

- `decompose`：需要拆分的任务及其子任务建议
- `chains`：必须按顺序执行的依赖链（同模块修改、有逻辑先后关系）
- `parallel`：可以并行执行的独立任务

5. 如果 `--dry-run`，展示调度计划后停止

#### Team Lead Agent 详细规格

- **角色**: Plan 类型 subagent
- **输入**: `list-pending` 的全部任务 JSON + 项目 CLAUDE.md 模块索引
- **职责**:
  1. 对每个任务分发 Task Analyst subagent（Explore 类型，可并行最多 3 个）
  2. 汇总 Task Analyst 的分析结果
  3. 对需要拆分的任务，返回拆分建议
  4. 识别任务间依赖关系（同模块、同文件修改、有逻辑先后）
  5. 输出调度计划：依赖链 + 独立任务组
- **输出格式**: 上述 JSON 结构

#### Task Analyst Agent 详细规格

- **角色**: Explore 类型 subagent
- **输入**: 单条任务的 id、description、tag + 对应 CLAUDE.md 模块文档路径
- **职责**:
  1. 阅读任务对应的 CLAUDE.md 模块文档
  2. 评估任务复杂度（修改文件数、逻辑变更数）
  3. 判断是否需要拆分
  4. 识别任务涉及的代码模块和可能的文件范围
- **输出**: 复杂度评估 + 拆分建议（如需要） + 涉及模块列表

#### Task Reviewer Agent 详细规格

- **角色**: Explore 类型 subagent
- **触发时机**: 每个执行 subagent 返回完成报告后、主会话标记 `complete` 之前
- **输入**:
  - 任务 ID、description、tag（通过 `get <id>` 获取）
  - 执行 subagent 的完成报告（结论、修改文件列表）
  - 代码 diff（通过 `git diff HEAD` 或 `git diff --cached` 获取相关文件的变更）
- **职责**:
  1. 运行 `git diff` 获取该任务修改文件的实际 diff
  2. 对照任务描述逐项检查：改动是否覆盖了任务需求的所有要点
  3. 检查是否有遗漏（如：任务要求删除入口但路由配置未清理）
  4. 检查是否有多余改动（违反最小改动原则）
  5. 检查明显的代码质量问题（语法错误、未关闭的标签、遗留的 debug 代码等）
- **输出格式**:
  ```json
  {
    "task_id": 2,
    "verdict": "pass",
    "summary": "所有需求点均已覆盖，代码改动合理",
    "issues": []
  }
  ```
  或：
  ```json
  {
    "task_id": 2,
    "verdict": "fail",
    "summary": "路由配置未清理，video 入口仍可访问",
    "issues": [
      {"severity": "critical", "description": "router/index.ts 中 /video 路由未删除"},
      {"severity": "minor", "description": "console.log 调试代码未清理"}
    ]
  }
  ```
  `verdict` 取值：`pass`（通过）、`fail`（不通过，需修复）
- **结果处理**:
  - `pass` → 主会话执行 `complete <id>`
  - `fail` → 主会话将 issues 反馈给 Team Lead，Team Lead 决定：
    - `critical` 问题 → 重新派发执行 subagent 修复，修复后再次验收
    - 仅 `minor` 问题 → 记录到 notes 中，仍标记 `complete`

### Phase 1b — 执行拆分

如果 Team Lead 的调度计划中有 `decompose` 项：

```bash
python $TM decompose <id> --subtasks '["子任务1", "子任务2"]'
```

拆分完成后，重新执行 `list-pending` 获取更新后的任务列表，
Team Lead 重新调度（或直接将子任务加入调度计划）。

### Phase 2 — 主会话调度执行

根据 Team Lead 的调度计划，主会话按以下策略调度执行：

#### 并行任务组执行

对 `parallel` 列表中的独立任务：

1. 主会话先为每个任务调用 `start <id>` 标记 in_progress
2. 同时启动多个 **general-purpose** subagent（通过 Agent 工具），每个传入任务 ID
3. 每个 subagent：
   - 执行 `get <id>` 获取任务详情
   - 阅读相关 CLAUDE.md 模块文档
   - 执行任务
   - 返回完成报告

```
📋 并行执行组: [任务2] [任务4] [任务6] [任务8]
   ├─ Agent #1: [前端] 删除 video 相关界面
   ├─ Agent #2: [后端] 清理过期的 API 路由
   ├─ Agent #3: [过滤器] 增加新的运动过滤算子
   └─ Agent #4: [工具] 修复 FBX 解析异常
```

#### 依赖链执行

对 `chains` 列表中的每条链：

1. 按链中顺序，逐条派发 subagent
2. 前一个任务完成后才派发下一个
3. 链中某个任务失败，该链后续任务全部跳过

```
📋 依赖链: 任务1 → 任务5 → 任务7
   ├─ Step 1: [后端] 添加新数据表字段
   ├─ Step 2: [后端] 更新 API 接口适配新字段
   └─ Step 3: [前端] 界面展示新字段
```

#### 执行 Subagent 规格

- **角色**: general-purpose subagent（通过 Agent 工具启动）
- **输入**: 任务 ID（通过 `get <id>` 获取详情）
- **变化**: 不再调用 `next`，而是 `get <id>` 获取任务详情
- **DB 更新**: 由主会话统一执行 `complete`/`fail`（subagent 不操作 DB 状态）
- **prompt 需包含**：
  - 任务 ID 和获取命令 `python $TM get <id>`
  - 相关 CLAUDE.md 模块文档路径
  - 最小改动原则的提醒
  - 要求返回以下格式的完成报告：

  ```
  【完成报告】
  结论：<一句话总结>
  修改文件：
    - path/to/file（说明）
  备注：<异常或注意事项；无则填"无">
  ```

### Phase 3 — 任务验收（Task Reviewer）

每个执行 subagent 返回完成报告后，**先进行验收再更新 DB**：

1. 对每个报告成功的任务，启动 **Task Reviewer Agent**（Explore 类型 subagent）
2. Reviewer 检查代码 diff 是否满足任务需求（可并行验收多个任务）
3. 根据验收结果决定后续动作：

```
🔍 验收阶段:
   ├─ 任务2: ✅ 通过 — 所有需求点均已覆盖
   ├─ 任务4: ✅ 通过（minor: console.log 未清理，已记录到 notes）
   ├─ 任务6: ❌ 执行失败 — 跳过验收
   └─ 任务8: ⚠️ 未通过 — 路由配置未清理，重新派发修复
```

**验收通过** → 进入 Phase 4 更新 DB
**验收未通过（critical）** → 重新派发执行 subagent 修复，修复后再次验收（最多重试 1 次）
**验收仅 minor 问题** → 记录到 notes，视为通过
**执行已失败的任务** → 跳过验收，直接标记 failed

### Phase 4 — 主会话统一更新 DB

验收完成后，主会话根据验收结果统一处理：

**成功时**：
```bash
python $TM complete <id> --conclusion "成功删除 VideoView.vue 及相关路由" --files '["src/views/VideoView.vue", "src/router/index.ts"]' --notes "无"
```

**失败时**：
```bash
python $TM fail <id> --notes "编译报错，需要人工检查"
```

**失败处理规则**：
- 并行组中某个失败 → 标记 DB 为 failed，**其他独立任务继续执行**
- 依赖链中某个失败 → 该链条后续任务**全部跳过**，标记为 failed 并备注"前置任务失败"
- 所有任务执行完毕后统一汇报

输出批次完成摘要：
```
📊 本批次执行结果:
   ✅ 任务2: [前端] 删除 video 相关界面 — 约 5 分钟
   ✅ 任务4: [后端] 清理过期的 API 路由 — 约 3 分钟
   ❌ 任务6: [过滤器] 增加新的运动过滤算子 — 编译报错
   ✅ 任务8: [工具] 修复 FBX 解析异常 — 约 4 分钟
   ⏭️ 任务7: [前端] 界面展示新字段 — 跳过（前置任务6失败）
```

### Phase 5 — 导出并继续

```bash
python $TM export --output FINISH_LIST.md
```

导出最新的完成记录后：
- 如果还有 pending 任务 → 回到 Phase 1 重新分析调度
- 如果指定了数量 N 且已完成 N 条 → 停止并汇总
- 所有任务完成 → Phase 6

### Phase 6 — 全部完成

```bash
python $TM export --output FINISH_LIST.md
python $TM count
```

输出总结：
```
🎉 所有 TODO 已完成！共执行 N 条任务（成功 X，失败 Y），详细记录见 FINISH_LIST.md
```

---

## 边界情况处理

### 任务描述模糊

如果任务描述不够具体，用 AskUserQuestion 询问用户澄清，而不是猜测。

### 任务涉及删除功能

1. 先搜索所有引用点（import、路由、配置等）
2. 从叶子节点开始删除
3. 确认没有其他代码依赖被删除的部分

### 改动出错需要回退

发现改错时，用 `git checkout -- <file>` 恢复文件。
使用 `fail` 命令标记任务失败。

### 只有少量任务（≤2 条）

如果 pending 任务 ≤ 2 条，跳过 Team Lead 分析阶段，
直接按原有串行模式逐条执行（`next` → 执行 → `complete`/`fail`）。

### Team Lead 分析后无需拆分、无依赖

所有任务都独立 → 全部放入 `parallel` 组并行执行。

---

## 重要约束

- **禁止使用 `list` 命令**：整个执行流程中**绝对不要调用 `python $TM list`**，它会输出所有待办任务列表，污染上下文。需要了解进度时用 `count`，需要全部待办列表时用 `list-pending`
- **遵守目录安全规则**：不对数据目录递归搜索
- **中文优先**：任务描述、日志输出使用中文
- **不自动 commit**：改完代码后不自动提交，由用户决定何时 commit
- **优先读文档**：根据 CLAUDE.md 模块索引了解代码结构，减少直接读大量源码
- **subagent 不操作 DB 状态**：所有 `start`/`complete`/`fail` 操作由主会话执行
- **并行失败隔离**：独立任务失败不阻塞其他任务；依赖链失败则跳过后续
