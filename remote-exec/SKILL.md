---
name: remote-exec
description: 管理远程/本地 GPU 服务器：查看 GPU 状态、执行命令/训练、终止任务、跟踪任务占用。
argument-hint: "<status|run|kill|refresh> [参数]"
allowed-tools: Bash, Read, Write
---

# remote-exec Skill

管理远程和本地 GPU 服务器。所有机器共享 apdcephfs 存储，本地改代码远程立即可见。

## 连接信息

| 名称 | IP | GPU | 卡数 | 显存/卡 |
|------|----|-----|------|---------|
| A100-0 | 11.216.61.32 | A100-SXM 40GB | 8 | 40 GB |
| A100-1 | 11.216.73.34 | A100-SXM 40GB | 8 | 40 GB |
| V100-0 | 11.214.27.250 | V100-SXM2 32GB | 8 | 32 GB |
| V100-1 | 11.213.38.249 | V100-SXM2 32GB | 8 | 32 GB |
| A800-0 | 11.216.67.240 | A800-SXM4 80GB | 8 | 80 GB |
| A100-2 | 11.220.38.24 | A100-SXM4 40GB | 8 | 40 GB |
| A100-3 | 11.220.5.102 | A100-SXM4 40GB | 8 | 40 GB |
| A100-4 | 11.220.10.240 | A100-SXM4 40GB | 8 | 40 GB |

SSH 端口: 36000, 用户: root, 密码见 `gpu_servers.json`。

## 脚本路径

```
SCRIPT=".claude/skills/remote-exec/remote_exec.py"
```

**所有调用必须加 `--no-confirm`**，否则脚本会等待 stdin 阻塞。

---

## 功能路由

根据 `$ARGUMENTS` 第一个关键词决定操作。

### 1. `status` — 查看 GPU 状态和任务占用

当 `$ARGUMENTS` 为空、`status`、`status a100`、`status local` 时：

```bash
# 刷新状态（SSH 探测 GPU + 进程分类）
python $SCRIPT --state refresh --no-confirm

# 查看状态（含进程分类：TRAINING / other / idle）
python $SCRIPT --state show --no-confirm

# 查看所有远程机器 GPU
python $SCRIPT --cmd gpu_stat --no-confirm

# 只看 A100 / A800
python $SCRIPT --gpu a100 --cmd gpu_stat --no-confirm
python $SCRIPT --gpu a800 --cmd gpu_stat --no-confirm

# 本地 GPU
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader
```

**进程分类**（refresh 时自动判断）：
- `[TRAINING xN]`: 检测到训练进程（关键词: `train.py`, `accelerate launch`, `torchrun`, `deepspeed`, `pipeline.trainer` 等）
- `[other xN]`: 有 python 进程但非训练（如 `fc.py`, `gpustat`, `nvitop` 等）
- `[idle]`: 无 python 进程

建议先 `refresh` 再 `show`。输出汇总表：机器名 | GPU 型号 | 进程分类 | 训练命令摘要。

### 2. `run` — 执行命令（含智能调度）

当 `$ARGUMENTS` 匹配 `run [@target] <command>` 时：

**目标指定**:
- `@local` — 本机执行
- `@a100` — A100 机器执行 (`--gpu a100`)
- `@a800` — A800 机器执行 (`--gpu a800`)
- `@v100` — V100 机器执行 (`--gpu v100`)
- `@0`...`@7` — 按序号指定 (`--host N`)
- 无前缀 — 自动调度（见下方规则）

**自动调度规则**:
1. **debug/可视化类** (`visualize`, `test_`, `check_`, 单卡脚本) → 本地执行
2. **小规模训练** (≤100 步, `debug10`, `debug100`) → 优先本地
3. **大规模训练** → 优先 A100 空闲机器

**执行方式**:

```bash
# 本地执行
cd PROJECT_ROOT && <command>

# 远程执行
python $SCRIPT --host N --cmd "<command>" --no-confirm

# 异步远程（长任务）
python $SCRIPT --host N --async --cmd "<command>" --no-confirm
```

执行后自动注册任务：
```bash
python $SCRIPT --state register --target <name> --job-desc "<desc>" --job-cmd "<cmd>" --no-confirm
```

**预定义快捷方式**:

| 快捷名 | 展开命令 | 默认目标 |
|--------|----------|----------|
| `debug10` | `bash scripts/test_training_10step.sh` | local |
| `debug100` | `bash scripts/test_training_100step.sh` | local |
| `debug1000` | `bash scripts/test_training_1000step.sh` | local/A100 |
| `nvidia_smi` | `nvidia-smi` | all |
| `gpu_stat` | GPU 利用率摘要 | all |
| `ps_python` | 查看 python 进程 | all |
| `kill_python` | 杀 python 进程 | 指定机器 |

### 3. `kill` — 终止任务

当 `$ARGUMENTS` 匹配 `kill [@target|all]` 时：

```bash
# 先查看目标机器上的进程
python $SCRIPT --host N --cmd ps_python --no-confirm

# 确认后 kill
python $SCRIPT --host N --cmd kill_python --no-confirm

# 更新状态
python $SCRIPT --state free --target <name> --no-confirm
```

### 4. `refresh` — 强制刷新状态

当 `$ARGUMENTS` = `refresh` 时：

```bash
python $SCRIPT --state refresh --no-confirm
```

SSH 探测所有服务器 GPU + 进程，重建 `server_state.json`。

---

## 状态管理

```bash
# 查看状态
python $SCRIPT --state show --no-confirm

# 刷新（SSH 探测）
python $SCRIPT --state refresh --no-confirm

# 注册任务
python $SCRIPT --state register --target A100-0 --job-desc "desc" --job-cmd "cmd" --no-confirm

# 释放任务
python $SCRIPT --state free --target A100-0 --no-confirm

# 清空所有
python $SCRIPT --state clean --no-confirm
```

---

## 注意事项

1. **共享存储**: 所有机器挂载同一个 apdcephfs，代码修改立即可见
2. **长任务用 `--async`**: 训练等耗时命令用异步模式，日志写入 `.claude/skills/remote-exec/logs/`
3. **新增/删除机器**: 编辑 `gpu_servers.json`，然后 `--state refresh` 更新状态
4. **本地优先**: debug 和小规模任务优先本地执行，减少 SSH 延迟