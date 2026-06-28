---
name: query-motion-database
description: 查询 HYMotion 动作数据管线的处理进度。当用户想了解管线状态、数据处理进度、漏斗数据、队列情况，或者说"查一下进度"、"看看管线状态"、"pipeline status"、"多少文件完成了"、"数据处理到哪了"时触发此 skill。
argument-hint: "[overview|funnel|progress|queue|health|all]"
allowed-tools: Bash
---

# query-motion-database Skill

通过远程只读 API 查询 HYMotion 动作数据管线的处理进度。

**API 地址**: `http://9.134.230.186:9091`

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
curl -s http://9.134.230.186:9091/api/health | python3 -m json.tool
```

期望返回 `{"status": "ok", "readonly": true, ...}`。

### overview — 数据概览

```bash
curl -s http://9.134.230.186:9091/api/stats/overview | python3 -m json.tool
```

支持过滤参数：`?source=xxx&sub_source=yyy`

返回字段：
- `total_files`: 总文件数
- `total_duration_hours`: 总时长（小时）
- `stages.{read,fit,repair,split,render,annotate}`: 各阶段的 `done_count` 和 `done_duration_seconds`
- `stages.split` 额外包含 `segment_count`（切片总数）

### funnel — 管线漏斗

```bash
curl -s http://9.134.230.186:9091/api/stats/funnel | python3 -m json.tool
```

支持过滤参数：`?source=xxx&sub_source=yyy`

返回每个阶段的 `input / done / failed / pending`，split 阶段额外有 `output_segments`。

### progress — 阶段进度

```bash
curl -s "http://9.134.230.186:9091/api/stats/progress?stage=<stage>" | python3 -m json.tool
```

`stage` 可选值：`read`, `fit`, `repair`, `split`, `render`, `annotate`。
支持过滤：`&source=xxx&sub_source=yyy`。
返回 `pending / done / failed / total`。

### queue — 队列进度

```bash
curl -s "http://9.134.230.186:9091/api/queue/progress?stage=<stage>" | python3 -m json.tool
```

支持过滤：`&batch_id=xxx`。
返回 `pending / running / done / failed / total`。

### all — 查询全部

依次调用 health → overview → funnel，然后汇总展示。以**人类可读的摘要**形式呈现，而不是输出原始 JSON。例如：

```
📊 HYMotion 管线状态
━━━━━━━━━━━━━━━━━━
总文件数: 370,934 | 总时长: 596.93 小时

阶段进度:
  read:     323,572 完成 (87.2%)
  fit:      284,470 完成
  split:    211,206 完成 → 244,025 个片段
  render:   236,440 完成
  annotate:  12,275 完成
```

## 注意事项

- 这是只读 API，不会修改任何数据。
- 数据有 60 秒缓存，不是实时值。
- 如果连接失败，说明远程服务不可用，提示用户联系服务端管理员。
