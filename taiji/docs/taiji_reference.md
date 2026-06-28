# 太极平台 (Taiji) 完整参考文档

## 1. 平台概述

太极 (Taiji) 是腾讯内部 GPU 集群管理平台，用于提交和管理 GPU 训练任务。通过 `taiji_client` 命令行工具与平台交互。

官方文档: https://iwiki.woa.com/p/456384856

### 核心概念

- **业务标识 (business_flag)**: 资源池标识，不同标识对应不同的 GPU 资源配额
- **任务标识 (task_flag)**: 每个提交的任务唯一标识
- **实例 (instance)**: 任务运行的容器实例，一个多机任务有多个实例
- **CephFS**: 共享文件系统，路径 `/apdcephfs_cq11/share_1467498/`

## 2. 认证

```bash
# 设置 TOKEN 环境变量
export TOKEN=<your_token>

# 验证
taiji_client trl
```

TOKEN 获取方式: 登录太极平台 Web 界面，在个人设置中获取 API Token。

## 3. 命令详解

### 3.1 查看资源 (business_resource_list / brl)

```bash
# 查看特定业务标识下的可用资源
taiji_client brl AILab_DHC_DC

# 输出包含:
# - 可用 GPU 数量
# - 各类型 GPU 配额
# - 当前使用量
```

### 3.2 提交任务 (start)

```bash
# 通过配置文件提交
taiji_client start -scfg config.json

# 返回:
# task_flag: <任务标识>
# instance_id: <实例ID>
```

### 3.3 查看运行中的任务 (task_running_list / trl)

```bash
taiji_client trl

# 输出: 所有运行中任务的列表
```

### 3.4 查看任务详情 (task_detail / td)

```bash
taiji_client td <task_flag>

# 输出: 任务的详细信息（状态、配置、运行时间等）
```

### 3.5 查看实例列表 (instance_list / il)

```bash
taiji_client il <task_flag>

# 输出: 任务下所有实例（对多机任务有多个实例）
# 包含 instance_id、状态、IP 等
```

### 3.6 登录容器 (exec)

```bash
taiji_client exec <task_flag> <instance_id> bash

# 进入容器的交互式 shell
```

### 3.7 停止任务 (stop)

```bash
taiji_client stop <task_flag>
```

### 3.8 修改任务 (modify_task)

```bash
taiji_client modify_task <task_flag> [options]
```

### 3.9 查看日志 (logs)

```bash
taiji_client logs <task_flag>
```

## 4. 配置 JSON 完整字段说明

```json
{
    "Token": "认证Token (必填, 从$TOKEN环境变量)",
    "business_flag": "业务标识 (必填)",
    "mount_ceph_business_flag": "CephFS挂载标识 (可选, 如AILab_DHA)",
    "extra_plat_business": "额外平台权限 (可选, 如AILab_DHC_DD)",
    "host_num": 1,                    // 机器数量 (必填)
    "host_gpu_num": 1,                // 每机器GPU数 (必填)
    "image_full_name": "镜像地址",     // Docker镜像 (必填)
    "task_flag": "任务标识",           // 自动生成
    "GPUName": "V100",                // GPU型号 (必填): V100/A100/H20/H800
    "is_elasticity": false,           // 弹性模式
    "start_cmd": "启动命令",          // 容器启动命令 (必填)
    "exit_cmd": "",                   // 退出命令 (可选)
    "init_cmd": "",                   // 初始化命令 (可选)
    "exec_start_in_all_mpi_pods": true,  // 所有pod执行start_cmd
    "enable_evicted_pulled_up": false,   // 被抢占后自动拉起
    "enable_evicted_end_task": true,     // 被抢占后结束任务
    "keep_alive": false,              // 容器退出后保持存活
    "cuda_version": "11.0",           // CUDA版本
    "report_period": 60,              // 状态上报周期(秒)
    "model_local_file_path": "本地模型路径",
    "project_id": 0,                  // 项目ID
    "enable_rdma": false,             // RDMA同机房
    "rdma_in_same_module": false,     // RDMA同模块
    "priority_level": "LOW",          // 弹性任务优先级
    "elastic_level": 1,               // 弹性等级
    "envs": {}                        // 环境变量(混元模式需要)
}
```

## 5. 工作流

### 5.1 提交单卡训练任务

```bash
# 1. 查资源
taiji_client brl AILab_DHC_DC

# 2. 提交
python .claude/skills/taiji/taiji_ops.py submit \
    -n train-v1 --gpu V100 --num_gpu 1 --num_host 1 \
    --docker t2m3 -b AILab_DHC_DC \
    --cmd "cd /path/to/project && python train.py" \
    --no-confirm

# 3. 等待任务启动，然后登录
taiji_client exec <task_flag> <instance_id> bash
```

### 5.2 提交分布式多机训练

```bash
python .claude/skills/taiji/taiji_ops.py submit \
    -n ddp-train --gpu A100 --num_gpu 8 --num_host 4 \
    --docker t2m3 -b TaiJi_HYAide_MMD_DHC_A1 --hunyuan \
    --cmd "cd /path && torchrun --nproc_per_node=8 train.py" \
    --rdma --no-confirm
```

### 5.3 弹性任务（可被抢占）

```bash
python .claude/skills/taiji/taiji_ops.py submit \
    -n elastic-job --gpu V100 --num_gpu 1 \
    --cmd "sleep infinity" --elastic --no-confirm
```

弹性任务特点：
- 优先级较低，可能被高优先级任务抢占
- 设置 `enable_evicted_pulled_up=true` 可在被抢占后自动重新排队
- 适合非紧急、可中断的任务

### 5.4 混元模式任务

混元模式需要额外的环境变量声明任务类别：

```bash
python .claude/skills/taiji/taiji_ops.py submit \
    -n hy-train --gpu H800 --num_gpu 8 --num_host 2 \
    -b TaiJi_HYAide_MMD_DHC_A1 --hunyuan \
    --cmd "cd /path && bash train.sh" --no-confirm
```

混元模式特点：
- 使用 `TaiJi_HYAide_MMD_DHC_A1` 业务标识
- 不需要 `mount_ceph_business_flag`
- 需要 `envs` 字段声明任务类别

## 6. 业务标识 (Business Flags)

| 标识 | 说明 | 常用 GPU |
|------|------|----------|
| `AILab_DHC_DC` | AILab 通用资源池（默认） | V100, A100 |
| `AILab_DHC_DD` | AILab DD 资源池 | V100, A100 |
| `TaiJi_HYAide_MMD_DHC_A1` | 混元模式专用 | H20, H800 |
| `TaiJi_HYAide_NEO_PRI_CQ_V100` | 混元 NEO V100 私有 | V100 |

## 7. Docker 镜像

| 别名 | 完整地址 | 说明 |
|------|----------|------|
| `mocap` | `mirrors.tencent.com/leotungtrain/easymocap:0726` | 动作捕捉 |
| `mocap2` | `mirrors.tencent.com/zyp-virtualman/easymocapa1_alg:0711` | MoCap A1 |
| `hallo` | `mirrors.tencent.com/sdh/videogen:latest` | 视频生成 |
| `megasam` | `mirrors.tencent.com/zephyrkwang/cu118_py310_pyt201_conda:camera_pose` | 相机姿态 |
| `t2m` | `mirrors.tencent.com/jeffryli/tlinux3.2-python3.10-cuda11.8:v0.2` | T2M v0.2 |
| `t2m3` | `mirrors.tencent.com/jeffryli/tlinux3.2-python3.10-cuda11.8:v0.3` | T2M v0.3 |
| (default) | `mirrors.tencent.com/kdkd006/centos8-gpu-conda:update_ninja` | 通用环境 |

## 8. GPU 类型

| 型号 | 显存 | 说明 |
|------|------|------|
| V100 | 32 GB | NVIDIA V100 SXM2，通用训练 |
| A100 | 40/80 GB | NVIDIA A100 SXM，大模型训练 |
| H20 | 96 GB | NVIDIA H20，超大模型 |
| H800 | 80 GB | NVIDIA H800 SXM，高性能训练 |

## 9. 守护进程 (Monitor)

守护进程自动监控任务状态、失败重试、发送通知。

### 配置

编辑 `.claude/skills/taiji/config/defaults.json` 的 `daemon` 部分：

```json
{
    "daemon": {
        "poll_interval": 120,    // 轮询间隔(秒)
        "max_retries": 3,        // 最大重试次数
        "webhook_url": ""        // 企业微信机器人webhook URL
    }
}
```

### 使用

```bash
# 单轮检查
python .claude/skills/taiji/taiji_monitor.py --once

# 启动后台守护
python .claude/skills/taiji/taiji_monitor.py --daemon

# 查看状态
python .claude/skills/taiji/taiji_monitor.py --status

# 停止
python .claude/skills/taiji/taiji_monitor.py --stop
```

### 重试策略

- 检测到任务失败 (status=failed) 且非手动停止
- 指数退避: 5分钟 → 10分钟 → 20分钟
- 最多重试 3 次
- 重试时生成新的 task_flag 带 `-retryN` 后缀

### 企业微信通知

配置 `webhook_url` 后，以下事件会发送通知：
- 任务状态变化（running → finished/failed）
- 自动重试
- 重试成功/失败

## 10. 故障排查

### TOKEN 无效

```
Error: TOKEN is not set
```

解决: `export TOKEN=<your_token>`

### 资源不足

查看资源: `taiji_client brl <business_flag>`
- 切换到其他 business_flag
- 使用弹性模式 `--elastic`
- 减少 GPU 数量

### 任务一直 queuing

- 资源紧张，等待调度
- 检查 GPU 类型是否在对应 business_flag 下可用
- 考虑使用弹性模式

### 容器启动失败

- 检查 Docker 镜像是否存在: 在太极平台 Web 界面查看
- 检查 `start_cmd` 是否正确
- 用 `taiji_client logs <task_flag>` 查看日志

### 多机任务通信失败

- 确保启用 RDMA: `--rdma`
- 检查 `host_num` 和 `host_gpu_num` 配置
- 确认 `exec_start_in_all_mpi_pods: true`

## 11. 最佳实践

1. **命名规范**: task_flag 自动生成为 `name-GPU-NxM-HHMM` 格式，`name` 应简洁有意义
2. **先查资源再提交**: 避免长时间排队
3. **使用守护进程**: 长时间训练任务建议开启监控守护
4. **弹性模式**: 非紧急任务使用弹性模式，可利用空闲资源
5. **日志检查**: 提交后用 `taiji_client logs` 确认启动正常
6. **清理资源**: 完成后及时 `taiji_client stop` 释放资源
