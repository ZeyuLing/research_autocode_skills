---
name: sync-ceph-data
description: "Sync data between CEPH storage paths using the Zhiyan OpenAPI. Use this skill whenever the user wants to copy, sync, or transfer data between CEPH directories, mentions 'ceph sync', 'data sync', 'sync data', or needs to move datasets between different CEPH shares."
---

# sync-ceph-data — CEPH 数据同步

通过织云 OpenAPI 在 CEPH 存储路径之间同步数据。

## 使用方式

用户提供源路径 (SRC) 和目标路径 (DEST)，skill 调用织云 API 提交同步任务。

## API 配置

- **API endpoint**: `$ZHIYAN_API_ENDPOINT`
- **Token**: `$ZHIYAN_API_TOKEN`（必须由密钥管理或环境注入）
- **Staff**: `$ZHIYAN_STAFF`
- **Project**: `$ZHIYAN_PROJECT`
- **Task ID**: `$ZHIYAN_TASK_ID`

这些值必须由受控环境或密钥管理器提供。提交任务前先验证配置，且不要把实际 Token、内部端点或人员信息写入仓库和日志：

```bash
: "${ZHIYAN_API_ENDPOINT:?Set ZHIYAN_API_ENDPOINT}"
: "${ZHIYAN_API_TOKEN:?Set ZHIYAN_API_TOKEN}"
: "${ZHIYAN_STAFF:?Set ZHIYAN_STAFF}"
: "${ZHIYAN_PROJECT:?Set ZHIYAN_PROJECT}"
: "${ZHIYAN_TASK_ID:?Set ZHIYAN_TASK_ID}"
```

## 执行步骤

1. 从用户输入中提取源路径和目标路径（可以是单个或多个路径对），分别写入当前会话的 `SRC` 与 `DEST`
2. 对每一对路径，执行如下 curl 命令：

```bash
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to encode the request payload safely." >&2
  exit 127
}

case "$ZHIYAN_TASK_ID" in
  ''|*[!0-9]*)
    echo "ZHIYAN_TASK_ID must be an integer." >&2
    exit 2
    ;;
esac

payload="$(python3 - "$ZHIYAN_TASK_ID" "$SRC" "$DEST" <<'PY'
import json
import sys

try:
    task_id = int(sys.argv[1])
except ValueError as exc:
    raise SystemExit("ZHIYAN_TASK_ID must be an integer") from exc

src, dest = sys.argv[2:4]
print(json.dumps({
    "id": task_id,
    "act": "query",
    "task_value": {
        "SRC_CEPH_PATH": src,
        "DEST_CEPH_PATH": dest,
        "DIST_STORAGE_TYPE": "ceph",
    },
}))
PY
)"

curl --fail-with-body --show-error --silent -X POST "$ZHIYAN_API_ENDPOINT" \
  -H "content-type: application/json" \
  -H "token: $ZHIYAN_API_TOKEN" \
  -H "staffname: $ZHIYAN_STAFF" \
  -H "projectname: $ZHIYAN_PROJECT" \
  --data "$payload"
```

3. 检查返回结果，确认任务是否提交成功（返回 JSON 中 `ret` 为 0 表示成功）
4. 向用户报告每个同步任务的状态

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| SRC_CEPH_PATH | 源 CEPH 路径 | `/ceph/source/dataset` |
| DEST_CEPH_PATH | 目标 CEPH 路径 | `/ceph/destination/dataset` |
| DIST_STORAGE_TYPE | 存储类型，固定为 `ceph` | `ceph` |

## 批量同步

当用户需要同步多个路径时，逐个执行 curl 命令，每个命令执行后检查返回状态。

## API 文档

更多 API 信息请参考组织内部文档，并通过 `$ZHIYAN_API_ENDPOINT` 配置当前端点。
