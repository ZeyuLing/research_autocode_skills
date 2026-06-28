---
name: sync-ceph-data
description: "Sync data between CEPH storage paths using the Zhiyan OpenAPI. Use this skill whenever the user wants to copy, sync, or transfer data between CEPH directories, mentions 'ceph sync', 'data sync', 'sync data', or needs to move datasets between different CEPH shares."
---

# sync-ceph-data — CEPH 数据同步

通过织云 OpenAPI 在 CEPH 存储路径之间同步数据。

## 使用方式

用户提供源路径 (SRC) 和目标路径 (DEST)，skill 调用织云 API 提交同步任务。

## API 配置

- **API endpoint**: `http://openapi.zhiyan.woa.com/operate/v1/exec_task`
- **Token**: `f4c77d5cca892599e511bbcf05d31499`
- **Staff**: `chingshuai`
- **Project**: `hunyuan_aide_taiji`
- **Task ID**: `17658`

## 执行步骤

1. 从用户输入中提取源路径和目标路径（可以是单个或多个路径对）
2. 对每一对路径，执行如下 curl 命令：

```bash
curl -X POST "http://openapi.zhiyan.woa.com/operate/v1/exec_task" \
  -H "content-type: application/json" \
  -H "token: f4c77d5cca892599e511bbcf05d31499" \
  -H "staffname: chingshuai" \
  -H "projectname: hunyuan_aide_taiji" \
  -d '{"id":17658,"act":"query","task_value":{"SRC_CEPH_PATH":"<源路径>","DEST_CEPH_PATH":"<目标路径>","DIST_STORAGE_TYPE":"ceph"}}'
```

3. 检查返回结果，确认任务是否提交成功（返回 JSON 中 `ret` 为 0 表示成功）
4. 向用户报告每个同步任务的状态

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| SRC_CEPH_PATH | 源 CEPH 路径 | `/apdcephfs_cq10/share_1330077/chingshuai/...` |
| DEST_CEPH_PATH | 目标 CEPH 路径 | `/apdcephfs_cq10/share_1467498/datasets/...` |
| DIST_STORAGE_TYPE | 存储类型，固定为 `ceph` | `ceph` |

## 批量同步

当用户需要同步多个路径时，逐个执行 curl 命令，每个命令执行后检查返回状态。

## API 文档

更多 API 信息参考：https://iwiki.woa.com/pages/viewpage.action?pageId=316246306
