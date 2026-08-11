---
name: query-motion-database
description: 查询 HYMotion 动作数据管线的处理进度。当用户想了解管线状态、数据处理进度、漏斗数据、队列情况，或者说"查一下进度"、"看看管线状态"、"pipeline status"、"多少文件完成了"、"数据处理到哪了"时触发此 skill。
argument-hint: "[overview|funnel|progress|queue|health|all]"
allowed-tools: Bash
---

# query-motion-database Skill

通过远程只读 API 查询 HYMotion 动作数据管线的处理进度。

**API 地址**: `$HYMOTION_STATUS_API`

运行前从受控环境设置 `HYMOTION_STATUS_API`。该变量应包含 API 根路径，但不要以 `/` 结尾；不要在公开仓库中写入内部 IP、主机名或认证信息。

## 使用方式

- `/query-motion-database` 或 `/query-motion-database all` — 查询全部统计并汇总展示
- `/query-motion-database overview` — 数据概览（总文件数、时长、各阶段完成数）
- `/query-motion-database funnel` — 管线漏斗（各阶段 input/done/failed/pending）
- `/query-motion-database progress <stage>` — 指定阶段进度
- `/query-motion-database queue <stage>` — 队列进度
- `/query-motion-database health` — 健康检查

## 查询接口

### health — 健康检查

```bash
curl -s "$HYMOTION_STATUS_API/health" | python3 -m json.tool
```

期望返回 `{"status": "ok", "readonly": true, ...}`。

### overview — 数据概览

```bash
curl -s "$HYMOTION_STATUS_API/stats/overview" | python3 -m json.tool
```

支持过滤参数：`?source=xxx&sub_source=yyy`

返回字段：
- `total_files`: 总文件数
- `total_duration_hours`: 总时长（小时）
- `stages.{read,fit,repair,split,render,annotate}`: 各阶段的 `done_count` 和 `done_duration_seconds`
- `stages.split` 额外包含 `segment_count`（切片总数）

### funnel — 管线漏斗

```bash
curl -s "$HYMOTION_STATUS_API/stats/funnel" | python3 -m json.tool
```

支持过滤参数：`?source=xxx&sub_source=yyy`

返回每个阶段的 `input / done / failed / pending`，split 阶段额外有 `output_segments`。

### progress — 阶段进度

```bash
curl -s "$HYMOTION_STATUS_API/stats/progress?stage=<stage>" | python3 -m json.tool
```

`stage` 可选值：`read`, `fit`, `repair`, `split`, `render`, `annotate`。
支持过滤：`&source=xxx&sub_source=yyy`。
返回 `pending / done / failed / total`。

### queue — 队列进度

```bash
curl -s "$HYMOTION_STATUS_API/queue/progress?stage=<stage>" | python3 -m json.tool
```

支持过滤：`&batch_id=xxx`。
返回 `pending / running / done / failed / total`。

### all — 查询全部

依次调用 health → overview → funnel，然后汇总展示。以**人类可读的摘要**形式呈现，而不是输出原始 JSON。例如：

```
📊 HYMotion 管线状态
━━━━━━━━━━━━━━━━━━
总文件数: <total_files> | 总时长: <total_hours> 小时

阶段进度:
  read:     <completed> 完成 (<percent>%)
  fit:      <completed> 完成
  split:    <completed> 完成 → <segments> 个片段
  render:   <completed> 完成
  annotate: <completed> 完成
```

## 注意事项

- 这是只读 API，不会修改任何数据。
- 数据可能有短时缓存，不是实时值；以 API 元数据返回的缓存窗口为准。
- 如果连接失败，说明远程服务不可用，提示用户联系服务端管理员。
