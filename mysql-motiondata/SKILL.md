---
name: mysql-motiondata
description: 连接和操作 HYMotion 项目的 MySQL 数据库（hymotion_data）。当用户提到 MySQL、数据库查询、建表、导数据、SQL 操作，或者需要在 MySQL 中存储/读取项目数据时，使用此 skill。也适用于用户说"连一下数据库"、"查个表"、"mysql 里看看"、"写入 mysql"、"数据库里有什么"等场景。
---

# MySQL HYMotion Data

项目使用的 MySQL 远程数据库，所有开发者共享同一实例。

## 连接信息

| 参数 | 值 |
|------|-----|
| Host | `9.134.93.150` |
| Port | `3306` |
| User | `root` |
| Password | `EwuMJ*9382VTWv` |
| Database | `hymotion_data` |
| Version | MySQL 8.0.30-txsql (腾讯云) |

## 命令行连接

```bash
mysql -h 9.134.93.150 -P 3306 -u root -p'EwuMJ*9382VTWv' hymotion_data
```

执行单条 SQL：

```bash
mysql -h 9.134.93.150 -P 3306 -u root -p'EwuMJ*9382VTWv' hymotion_data -e "YOUR SQL HERE"
```

## Python 连接

```python
import pymysql

conn = pymysql.connect(
    host="9.134.93.150",
    port=3306,
    user="root",
    password="EwuMJ*9382VTWv",
    database="hymotion_data",
    charset="utf8mb4",
)
```

## 使用注意

- 这是共享数据库，执行 DROP/DELETE/TRUNCATE 前先确认用户意图
- 建表时使用 `utf8mb4` 字符集和 `InnoDB` 引擎
- 大批量写入使用事务 + 批量 INSERT，避免逐条插入
- 密码直接写在命令行中即可，团队内部使用不需要额外加密
