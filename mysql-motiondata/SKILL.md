---
name: mysql-motiondata
description: 连接和操作 HYMotion 项目的 MySQL 数据库（hymotion_data）。当用户提到 MySQL、数据库查询、建表、导数据、SQL 操作，或者需要在 MySQL 中存储/读取项目数据时，使用此 skill。也适用于用户说"连一下数据库"、"查个表"、"mysql 里看看"、"写入 mysql"、"数据库里有什么"等场景。
---

# MySQL HYMotion Data

项目使用的 MySQL 远程数据库，所有开发者共享同一实例。

## 连接信息

| 参数 | 值 |
|------|-----|
| Host | `$HYMOTION_MYSQL_HOST` |
| Port | `$HYMOTION_MYSQL_PORT`（默认 `3306`） |
| User | `$HYMOTION_MYSQL_USER` |
| Password | `$HYMOTION_MYSQL_PASSWORD`（必须由密钥管理或环境注入） |
| Database | `$HYMOTION_MYSQL_DATABASE` |
| Version | MySQL 8.0.30-txsql (腾讯云) |

## 环境配置

连接参数必须由受控环境、密钥管理器或当前会话注入。运行前确认以下变量均已配置，且不要把实际值写入仓库、命令历史或日志：

- `HYMOTION_MYSQL_HOST`
- `HYMOTION_MYSQL_PORT`（可选，默认 `3306`）
- `HYMOTION_MYSQL_USER`
- `HYMOTION_MYSQL_PASSWORD`
- `HYMOTION_MYSQL_DATABASE`

## 命令行连接

首次使用时，通过交互式密码提示创建本机 login path：

```bash
mysql_config_editor set --login-path=hymotion \
  --host="$HYMOTION_MYSQL_HOST" \
  --port="${HYMOTION_MYSQL_PORT:-3306}" \
  --user="$HYMOTION_MYSQL_USER" \
  --password
mysql --login-path=hymotion "$HYMOTION_MYSQL_DATABASE"
```

执行单条 SQL：

```bash
mysql --login-path=hymotion "$HYMOTION_MYSQL_DATABASE" -e "YOUR SQL HERE"
```

## Python 连接

```python
import os

import pymysql

conn = pymysql.connect(
    host=os.environ["HYMOTION_MYSQL_HOST"],
    port=int(os.environ.get("HYMOTION_MYSQL_PORT", "3306")),
    user=os.environ["HYMOTION_MYSQL_USER"],
    password=os.environ["HYMOTION_MYSQL_PASSWORD"],
    database=os.environ["HYMOTION_MYSQL_DATABASE"],
    charset="utf8mb4",
)
```

## 使用注意

- 这是共享数据库，执行 DROP/DELETE/TRUNCATE 前先确认用户意图
- 建表时使用 `utf8mb4` 字符集和 `InnoDB` 引擎
- 大批量写入使用事务 + 批量 INSERT，避免逐条插入
- 禁止在命令、脚本、日志或仓库中写入明文密码；优先使用密钥管理、MySQL login path 或临时环境注入
