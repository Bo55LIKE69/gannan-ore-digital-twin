"""启动一个带 PostGIS 的 PostgreSQL 实例（二进制来自 conda 环境）。

仅用于本地开发：
- initdb 用 trust 认证（免密码）
- 端口 5433，避免和本机系统 PG17(5432) 冲突
- 数据目录 backend/pgdata（不入库）

用法：
    backend/.venv/Scripts/python.exe pg_launcher.py
"""
import os
import subprocess
import sys
import time

from config import CONDA_ENV, PGDATA, PG


def bin(name: str) -> str:
    return os.path.join(CONDA_ENV, name)


def run(cmd, **kw):
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, **kw)


def initdb_if_needed():
    if os.path.exists(os.path.join(PGDATA, "PG_VERSION")):
        print("pgdata 已存在，跳过 initdb")
        return
    os.makedirs(PGDATA, exist_ok=True)
    r = run(
        [bin("initdb.exe"), "-D", PGDATA, "-U", PG["user"], "-A", "trust",
         "--encoding=UTF8", "--locale=C"],
        capture_output=True, text=True,
    )
    print(r.stdout, r.stderr)
    r.check_returncode()
    print("initdb 完成")


def is_running() -> bool:
    probe = [bin("psql.exe"), "-h", PG["host"], "-p", str(PG["port"]),
             "-U", PG["user"], "-d", "postgres", "-c", "SELECT 1;"]
    return subprocess.run(probe, capture_output=True).returncode == 0


def start():
    if is_running():
        print("postgres 已在运行")
        return
    log = os.path.join(PGDATA, "server.log")
    r = run(
        [bin("pg_ctl.exe"), "start", "-D", PGDATA,
         "-o", f"-p {PG['port']}", "-l", log],
        capture_output=True, text=True,
    )
    print(r.stdout, r.stderr)


def wait_ready(timeout=40):
    probe = [bin("psql.exe"), "-h", PG["host"], "-p", str(PG["port"]),
             "-U", PG["user"], "-d", "postgres", "-c", "SELECT 1;"]
    for _ in range(timeout):
        if subprocess.run(probe, capture_output=True).returncode == 0:
            print("postgres 就绪")
            return True
        time.sleep(1)
    raise RuntimeError("postgres 启动超时，请查看 " + os.path.join(PGDATA, "server.log"))


def setup():
    """建库 + 在库内启用 PostGIS 扩展。"""
    def psql(db, sql):
        r = run(
            [bin("psql.exe"), "-h", PG["host"], "-p", str(PG["port"]),
             "-U", PG["user"], "-d", db, "-c", sql],
            capture_output=True, text=True,
        )
        print(r.stdout, r.stderr)
        r.check_returncode()

    # 建库（已存在则忽略错误）
    r = run(
        [bin("createdb.exe"), "-h", PG["host"], "-p", str(PG["port"]),
         "-U", PG["user"], PG["dbname"]],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("(库已存在，跳过 createdb)")
    # 扩展必须在目标库里启用（扩展是 per-database 的）
    psql(PG["dbname"], "CREATE EXTENSION IF NOT EXISTS postgis;")


def stop():
    if not is_running():
        print("postgres 未在运行")
        return
    r = run([bin("pg_ctl.exe"), "stop", "-D", PGDATA, "-m", "fast"],
            capture_output=True, text=True)
    print(r.stdout, r.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop()
    else:
        initdb_if_needed()
        start()
        wait_ready()
        setup()
        print("✅ PostGIS 实例就绪 ->", f"{PG['host']}:{PG['port']}/{PG['dbname']}")
