---
name: db-analyze
description: >
  分析项目 SQLite 数据库的表和列大小。统计各表行数、各列平均/最大长度、
  磁盘占用估算，以清晰表格形式输出。
  支持分析主数据库 (pipeline.db) 和标注数据库 (annotations.db)。
  当用户说"分析数据库"、"数据库大小"、"表大小"、"db analyze"、
  "数据库占用"、"看看数据库"、"db size"时触发。
argument-hint: "[all|pipeline|annotation]"
allowed-tools: Bash, Read
---

# db-analyze Skill

分析项目的 SQLite 数据库，输出各表行数、各列的数据大小分布，以及磁盘占用估算。

## 使用方式

- `/db-analyze` 或 `/db-analyze all` — 分析所有数据库
- `/db-analyze pipeline` — 仅分析主管线数据库 (pipeline.db)
- `/db-analyze annotation` — 仅分析标注数据库 (annotations.db)
- 自然语言："分析一下数据库大小"、"看看数据库各表占用"

根据 `$ARGUMENTS` 决定行为：
- 空 或 `all` → 分析所有数据库
- `pipeline` → 仅分析 pipeline.db
- `annotation` → 仅分析 annotations.db

---

## 数据库路径

项目使用两个 SQLite 数据库：

| 数据库 | 路径 | 说明 |
|--------|------|------|
| 主管线 DB | `/apdcephfs_cq11/share_1467498/home/chingshuai/HYMotion/output/pipeline.db` | Retarget 管线数据 |
| 标注 DB | `/apdcephfs_cq11/share_1467498/home/chingshuai/HYMotion/data/annotations/annotations.db` | 旋转/Pose 标注数据 |

---

## 执行流程

### Phase 1 — 确定分析范围

根据 `$ARGUMENTS` 确定要分析哪些数据库。

### Phase 2 — 收集数据库文件信息

对每个数据库文件：

1. 用 `ls -lh` 检查文件大小
2. 用 `sqlite3` 的 `PRAGMA page_count;` 和 `PRAGMA page_size;` 获取数据库总大小
3. 用 `sqlite3` 的 `PRAGMA freelist_count;` 获取空闲页数

### Phase 3 — 分析各表

对每个数据库中的每张表，使用 **一条** sqlite3 命令批量执行以下查询，减少进程开销：

```sql
-- 1. 获取所有表名
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;

-- 2. 对每张表获取行数
SELECT COUNT(*) FROM <table>;

-- 3. 对每张表获取列信息
PRAGMA table_info(<table>);

-- 4. 对每张表的每一列，估算数据大小
-- 文本/BLOB 列: AVG(LENGTH(col)), MAX(LENGTH(col)), SUM(LENGTH(col))
-- 数值列: 固定大小估算（INTEGER=8字节, REAL=8字节）
-- 空值比例: COUNT(col) vs COUNT(*)
```

**关键**: 将所有 SQL 语句拼成一个脚本一次性传给 sqlite3，避免对大型数据库反复建立连接。

示例命令模式：

```bash
sqlite3 /path/to/db.sqlite <<'SQLEOF'
.headers on
.mode csv
-- 查询写在这里
SQLEOF
```

### Phase 4 — 输出报告

以 Markdown 表格形式输出结果，格式如下：

#### 数据库概览

```
## <数据库名称>

- 文件路径: /path/to/db
- 文件大小: XXX MB
- 数据库页数: XXXX (页大小: XXXX bytes)
- 空闲页数: XXXX (可回收空间: XX MB)
```

#### 各表行数汇总

```
| 表名 | 行数 | 估算大小 |
|------|------|----------|
| motion_files | 125,000 | 45.2 MB |
| segments | 380,000 | 89.1 MB |
| ... | ... | ... |
```

#### 各表列级别详情

对每张表输出列级分析：

```
### <表名> (N 行)

| 列名 | 类型 | 非空率 | 平均长度 | 最大长度 | 总大小估算 |
|------|------|--------|----------|----------|------------|
| id | TEXT | 100% | 32 B | 64 B | 3.8 MB |
| data_source | TEXT | 100% | 8 B | 15 B | 0.95 MB |
| poses_data | BLOB | 85% | 12.4 KB | 48.2 KB | 4.6 GB |
| ... | ... | ... | ... | ... | ... |
```

大小单位自动换算：B / KB / MB / GB，保留 1-2 位小数。

### Phase 5 — 输出优化建议（可选）

如果发现以下情况，给出简要建议：
- 空闲页比例 > 20%：建议运行 `VACUUM`
- 某列空值率 > 80%：提示该列大量为空
- BLOB 列占比超过 80% 数据库大小：标记为主要存储消耗来源

---

## 重要约束

- **只读操作**：不修改数据库，不执行 VACUUM、DELETE 等写操作
- **使用批量 SQL**：尽量减少 sqlite3 进程调用次数，一次传入多条查询
- **中文输出**：报告使用中文
- **大小换算**：自动选择合适的单位 (B/KB/MB/GB)
- **超时保护**：单次 sqlite3 命令设置合理 timeout（数据库可能较大）
- **不分析数据目录**：遵守项目安全规则，只分析已知的两个 DB 文件
