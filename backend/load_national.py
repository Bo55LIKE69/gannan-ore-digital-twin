"""把全国矿产地 CSV（33144 条）导入 PostgreSQL（gannan_ore.mines_cn）。

数据源：数据/全国矿产地分布/原始数据/全国矿产地分布数据.csv
字段映射（CSV → 表）：
    mc   → name     矿产地名称
    kz   → kind     矿种（煤/铁/稀土…）
    kcgm → scale    规模（特大型/大型/中型/小型/矿点/矿化点）
    kczk → status   开发现状（生产矿区/停采/采空/未利用…，可为空）
    lon lat → 坐标（WGS84，实测 0 条坏坐标）

自适应双模式：
- 实例里有 PostGIS → geom POINT(4326) + GiST 索引（精确空间运算）
- 没有 → 纯 SQL：lon/lat 复合 B-tree 索引，bbox 用 BETWEEN（3.3 万点毫秒级）
  将来 PostGIS 可用后重跑本脚本即自动升级为 geom 模式。

用法：
    backend/.venv/Scripts/python.exe load_national.py
"""
import csv
import os

import psycopg2
from psycopg2.extras import execute_values

from config import PG

CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "数据", "全国矿产地分布", "原始数据", "全国矿产地分布数据.csv",
)

BASE_COLS = """
    id     SERIAL PRIMARY KEY,
    name   TEXT NOT NULL,
    kind   TEXT,
    scale  TEXT,
    status TEXT,
    lon    DOUBLE PRECISION NOT NULL,
    lat    DOUBLE PRECISION NOT NULL
"""

DDL_GIS = f"""
CREATE TABLE IF NOT EXISTS mines_cn (
{BASE_COLS},
    geom   GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS mines_cn_geom_gix ON mines_cn USING GIST (geom);
"""

DDL_PLAIN = f"""
CREATE TABLE IF NOT EXISTS mines_cn (
{BASE_COLS}
);
CREATE INDEX IF NOT EXISTS mines_cn_lonlat_idx ON mines_cn (lon, lat);
"""

INSERT_GIS = """
INSERT INTO mines_cn (name, kind, scale, status, lon, lat, geom)
VALUES %s
"""

INSERT_PLAIN = """
INSERT INTO mines_cn (name, kind, scale, status, lon, lat)
VALUES %s
"""

# 中国陆地经纬度粗边界，过滤明显异常坐标
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 72, 136, 2, 54


def read_rows():
    n, bad = 0, 0
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:   # utf-8-sig 吃掉 BOM
        for r in csv.DictReader(f):
            n += 1
            try:
                lon, lat = float(r["lon"]), float(r["lat"])
                if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
                    raise ValueError("out of china bbox")
            except Exception:
                bad += 1
                continue
            name = (r.get("mc") or "").strip()
            if not name:
                bad += 1
                continue
            rows.append((
                name,
                (r.get("kz") or "").strip() or None,
                (r.get("kcgm") or "").strip() or None,
                (r.get("kczk") or "").strip() or None,
                lon, lat,
            ))
    print("CSV 总行数 %d，有效 %d，跳过 %d" % (n, len(rows), bad))
    return rows


def try_postgis(cur, conn):
    """尝试启用 PostGIS；不可用则回退纯 SQL 模式。"""
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        return True
    except Exception as e:
        conn.rollback()
        print("PostGIS 不可用（%s），退回纯 SQL bbox 模式" % str(e).splitlines()[0])
        return False


def main():
    rows = read_rows()
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()
    has_gis = try_postgis(cur, conn)
    cur.execute(DDL_GIS if has_gis else DDL_PLAIN)
    cur.execute("TRUNCATE mines_cn;")
    if has_gis:
        data = [r + (f"SRID=4326;POINT({r[4]} {r[5]})",) for r in rows]
        execute_values(cur, INSERT_GIS, data,
                       template="(%s, %s, %s, %s, %s, %s, %s::geometry)", page_size=1000)
    else:
        execute_values(cur, INSERT_PLAIN, rows, page_size=1000)
    conn.commit()

    cur.execute("SELECT count(*) FROM mines_cn;")
    total = cur.fetchone()[0]
    cur.execute("SELECT scale, count(*) FROM mines_cn GROUP BY scale ORDER BY 2 DESC;")
    print("已导入 mines_cn: %d 条 | 模式: %s" % (total, "PostGIS geom" if has_gis else "纯 SQL bbox"))
    for k, c in cur.fetchall():
        print("  %-8s %6d" % (k or "(空)", c))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
