"""数据库连接配置（本地开发用）。

说明：
- 用 conda 环境里的 PostgreSQL（带 PostGIS），端口 5433，和本机系统 PG17(5432) 错开。
- initdb 用 trust 认证（开发方便，免密码）。生产环境务必改成密码认证，
  且不要把密码写死在代码里（用环境变量 / .env / 密钥管理）。
"""
import os

# conda 环境里 postgres 的 bin 目录（含 postgres.exe / initdb.exe / pg_ctl.exe / psql.exe）
# 可用环境变量 GANNAN_PG_BIN 覆盖，方便别人换路径。
CONDA_ENV = os.environ.get("GANNAN_PG_BIN", r"E:\adaconda\envs\gannan-pg\Library\bin")

PG = {
    "host": "127.0.0.1",
    "port": 5433,          # 与系统 PG17(5432) 冲突，故用 5433
    "user": "postgres",
    "password": "",        # trust 认证，开发期留空
    "dbname": "gannan_ore",
}

# 数据目录放在 backend/pgdata（不入库，见根 .gitignore）
PGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pgdata")
