---
name: taiji
description: 太极平台任务管理：查资源、提交任务、查状态、停止任务、查历史。
argument-hint: "<自然语言描述你想做的事>"
allowed-tools: Bash, Read, Write
---

# taiji Skill

太极 GPU 集群平台的自然语言操作接口。根据 `$ARGUMENTS` 的意图匹配对应操作。

## 环境要求

- `TOKEN` 环境变量已设置（太极平台认证）。**操作前必须检查 `$TOKEN` 是否有值，如果为空则直接报错提示用户设置，不要继续执行任何操作。**
- `taiji_client` 命令可用

## 脚本路径

```
OPS_SCRIPT=".claude/skills/taiji/taiji_ops.py"
```

**所有 taiji_ops.py 调用必须加 `--no-confirm`**，否则脚本会等待 stdin 阻塞。
**所有 taiji_ops.py submit/build-config 调用必须加 `--token "$TOKEN"`**，确保 Token 正确传递。

---

## 功能路由

根据 `$ARGUMENTS` 自然语言意图判断执行哪个操作。

### 1. 查资源 — 匹配「资源」「还有多少卡」「resource」「brl」

```bash
# 查指定 business_flag 的资源
taiji_client brl <business_flag>

# 无参数时查所有已配置的 business_flag
taiji_client brl AILab_DHA
taiji_client brl AILab_DHC_DC
taiji_client brl AILab_DHC_DD
taiji_client brl TaiJi_HYAide_MMD_DHC_A1
taiji_client brl TaiJi_HYAide_NEO_PRI_CQ_V100
```

从 `$ARGUMENTS` 中提取 business_flag。如果未指定，查所有已配置的标识。

### 2. 提交任务 — 匹配「提交」「submit」「跑一个」「启动训练」「start」

```bash
python $OPS_SCRIPT submit \
    --token "$TOKEN" \
    -n <name> \
    --gpu <type> \
    --num_gpu <N> \
    --num_host <N> \
    --docker <image_alias_or_full_name> \
    -b <business_flag> \
    --cmd "<command>" \
    [--elastic] \
    [--hunyuan] \
    [--rdma] \
    [--private] \
    [--delay <hours>] \
    --no-confirm
```

**参数提取规则**：
- 从 `$ARGUMENTS` 提取可识别的参数（GPU 型号、数量、镜像、命令等）
- **缺少必要参数时向用户询问**，至少需要: `--name`, `--cmd`
- 默认值: `--gpu V100`, `--num_gpu 1`, `--num_host 1`, `-b AILab_DHC_DC`, `--docker` 使用默认镜像

**提交后输出**：
- task_flag
- instance_id
- 登录命令: `taiji_client exec <task_flag> <instance_id> bash`

### 3. 查状态 — 匹配「状态」「status」「跑得怎么样」「我的任务」「任务列表」「trl」

```bash
# 列出运行中的任务
taiji_client trl

# 查特定任务详情
taiji_client td <task_flag>

# 查实例列表
taiji_client il <task_flag>
```

如果 `$ARGUMENTS` 包含具体的 task_flag，用 `td` 和 `il` 查详情；否则用 `trl` 列出所有。

### 4. 在容器上执行命令 — 匹配「登录」「ssh」「exec」「进去看看」「连接」「debug」「调试」

`taiji_client exec` 需要交互式 TTY，在 Claude Code / autorun 等非交互环境中无法直接使用。
使用 `taiji_exec.py`（位于 skill 目录或 `tools/` 下）自动模拟 PTY 解决此问题。

**脚本位置**（按优先级查找）：
```
TAIJI_EXEC="skills/taiji/taiji_exec.py"   # skill 目录内
# 或
TAIJI_EXEC="tools/taiji_exec.py"          # 项目 tools 目录
```

**用法**: `python3 $TAIJI_EXEC <task_flag> <instance_id> "<command>" [timeout_seconds]`

```bash
# 先查 instance_id
taiji_client il <task_flag>

# 执行单条命令（默认超时 60s）
python3 $TAIJI_EXEC <task_flag> <instance_id> "hostname && nvidia-smi" 30

# 执行复杂命令（长超时）
python3 $TAIJI_EXEC <task_flag> <instance_id> "cd /workspace && python3 eval.py --config xxx" 600

# 查看文件、检查环境等
python3 $TAIJI_EXEC <task_flag> <instance_id> "ls -la /workspace/output/" 20
python3 $TAIJI_EXEC <task_flag> <instance_id> "pip list | grep torch" 20
python3 $TAIJI_EXEC <task_flag> <instance_id> "cat /workspace/train.log | tail -50" 20
```

**输出**: 命令的 stdout/stderr 会原封不动返回，可以直接用 Bash 工具捕获和分析。

**长时间任务处理**:
- 短命令（< 1分钟）：直接执行，设置合理 timeout
- 中等命令（1-10分钟）：设置足够大的 timeout（如 600）
- 长命令（> 10分钟）：在容器内用 nohup 后台执行，然后定期检查结果：
  ```bash
  # 后台提交
  python3 $TAIJI_EXEC <task_flag> <instance_id> "cd /workspace && nohup python3 train.py > train.log 2>&1 &" 20
  # 定期检查
  python3 $TAIJI_EXEC <task_flag> <instance_id> "tail -20 /workspace/train.log" 20
  ```

### 5. 停止 — 匹配「停止」「stop」「kill」「关掉」「结束」

```bash
taiji_client stop <task_flag>
```

**必须先向用户确认再执行停止操作。** 如果未指定 task_flag，先 `taiji_client trl` 列出任务让用户选择。

### 6. 历史 — 匹配「历史」「history」「之前的任务」「记录」

```bash
python $OPS_SCRIPT history [--limit N]
```

默认显示最近 20 条记录。

---

## 注意事项

1. **TOKEN**: 所有操作需要 `$TOKEN` 环境变量。操作前检查 `echo $TOKEN` 是否有值。提交任务时用 `--token "$TOKEN"` 显式传递。
2. **task_flag 格式**: `<name>-<GPU>-<NxM>-<HHMM>[-elastic]`，其中 N=host_num, M=gpu_num
3. **命令缩写**: `brl`=business_resource_list, `trl`=task_running_list, `td`=task_detail, `il`=instance_list
4. **停止操作**: 始终先确认再停止，防止误操作
5. **参数不足**: 提交任务时如果参数不足，主动向用户询问
6. **容器执行**: 使用 `python3 tools/taiji_exec.py` 替代 `taiji_client exec`，支持无 TTY 环境
