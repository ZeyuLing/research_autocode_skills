# 太极平台 (Taiji) 使用指南

本项目集成了腾讯太极 GPU 集群平台的操作能力。你可以用自然语言管理太极任务。

## 快速开始：`/taiji` Skill

输入 `/taiji <你想做的事>` 即可操作太极平台，例如：

- `/taiji 查一下 AILab_DHC_DC 的资源`
- `/taiji 提交一个 V100 单卡任务跑 sleep infinity`
- `/taiji 看看我的任务`
- `/taiji 停止 my-task-flag`
- `/taiji 查看历史`

## 核心命令速查

| 操作 | 命令 | 说明 |
|------|------|------|
| 查资源 | `taiji_client brl <business_flag>` | 查看业务标识下可用 GPU 资源 |
| 提交任务 | `taiji_client start -scfg config.json` | 提交任务，返回 task_flag + instance_id |
| 任务列表 | `taiji_client trl` | 查看运行中的任务列表 |
| 任务详情 | `taiji_client td <task_flag>` | 查看特定任务详细信息 |
| 实例列表 | `taiji_client il <task_flag>` | 查看任务下的实例列表 |
| 登录容器 | `taiji_client exec <task_flag> <instance_id> bash` | SSH 进入运行中的容器 |
| 停止任务 | `taiji_client stop <task_flag>` | 停止指定任务 |
| 修改任务 | `taiji_client modify_task <task_flag> ...` | 修改任务配置 |
| 查日志 | `taiji_client logs <task_flag>` | 查看任务日志 |

### 命令缩写对照

| 缩写 | 全称 | 说明 |
|------|------|------|
| `brl` | `business_resource_list` | 业务资源列表 |
| `trl` | `task_running_list` | 运行中任务列表 |
| `td` | `task_detail` | 任务详情 |
| `il` | `instance_list` | 实例列表 |

## 配置 JSON 核心字段

提交任务时需要一个配置 JSON，关键字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `Token` | string | 是 | 认证 Token（从 `$TOKEN` 环境变量读取） |
| `business_flag` | string | 是 | 业务标识，决定资源池 |
| `host_num` | int | 是 | 机器数量 |
| `host_gpu_num` | int | 是 | 每台机器 GPU 数量 |
| `GPUName` | string | 是 | GPU 型号：V100/A100/H20/H800 |
| `image_full_name` | string | 是 | Docker 镜像完整地址 |
| `task_flag` | string | 是 | 任务标识（自动生成） |
| `start_cmd` | string | 是 | 启动命令 |
| `is_elasticity` | bool | 否 | 是否弹性任务（可被抢占） |
| `enable_rdma` | bool | 否 | 是否要求 RDMA 同机房 |
| `mount_ceph_business_flag` | string | 否 | 挂载 CephFS 的业务标识 |
| `extra_plat_business` | string | 否 | 额外平台业务权限 |
| `envs` | object | 否 | 环境变量（混元模式需要） |

## 常用业务标识

| 标识 | 用途 |
|------|------|
| `AILab_DHA` | DHA 资源池 |
| `AILab_DHC_DC` | 通用资源池（默认） |
| `AILab_DHC_DD` | DD 资源池 |
| `TaiJi_HYAide_MMD_DHC_A1` | 混元模式专用 |
| `TaiJi_HYAide_NEO_PRI_CQ_V100` | 混元 NEO V100 私有 |

## 常用 Docker 镜像

| 别名 | 镜像地址 |
|------|----------|
| `mocap` | `mirrors.tencent.com/leotungtrain/easymocap:0726` |
| `t2m` | `mirrors.tencent.com/jeffryli/tlinux3.2-python3.10-cuda11.8:v0.2` |
| `t2m3` | `mirrors.tencent.com/jeffryli/tlinux3.2-python3.10-cuda11.8:v0.3` |
| 默认 | `mirrors.tencent.com/kdkd006/centos8-gpu-conda:update_ninja` |

## 认证

太极平台通过 `TOKEN` 环境变量认证。使用前确保已设置：

```bash
export TOKEN=HzrPZC3djhwaU9HPdEA_Bg
```

> 该 token 已固定记录于此（用户授权，非高敏感凭证），提交任务前直接 `export` 即可，无需再询问。

## 文件结构

```
.claude/skills/taiji/
├── SKILL.md              # Skill 定义
├── taiji_ops.py          # 核心操作脚本（submit/history/build-config）
├── taiji_monitor.py      # 守护进程（监控/重试/通知）
├── task_history.jsonl    # 任务历史记录
└── config/
    ├── defaults.json     # 默认配置模板
    ├── business_flags.json   # 业务标识注册表
    ├── docker_images.json    # Docker 镜像注册表
    └── gpu_types.json        # GPU 类型注册表
```

详细参考文档见 `docs/taiji_reference.md`。
