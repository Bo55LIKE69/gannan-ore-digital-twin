"""把 point_score.js 的 408 个矿点导入 PostGIS（gannan_ore.mines）。

- 坐标系：WGS84 / EPSG:4326（和前端大屏一致，无需转换）
- 几何：Point，用 ST_SetSRID(ST_MakePoint(lon,lat),4326) 生成
- 可重复运行：先 TRUNCATE 再批量 INSERT

用法：
    backend/.venv/Scripts/python.exe load_mines.py
"""
import os
import re
import json
import psycopg2

from config import PG

SRC = os.path.join(os.path.dirname(__file__), "..", "point_score.js")

# 赣州 18 个县（区）的中英文对照；数据里 county 是英文，这里补中文方便展示
COUNTY_CN = {
    "Chongyi": "崇义", "Dayu": "大余", "Ganxian": "赣县", "Longnan": "龙南",
    "Xinfeng": "信丰", "Xingguo": "兴国", "Shangyou": "上犹", "Yudu": "于都",
    "Quannan": "全南", "Xunwu": "寻乌", "Dingnan": "定南", "Anyuan": "安远",
    "Nankang": "南康", "Ningdu": "宁都", "Huichang": "会昌", "Shicheng": "石城",
    "Zhanggong": "章贡", "Ruijin": "瑞金",
}

DDL = """
CREATE TABLE IF NOT EXISTS mines (
    id          SERIAL PRIMARY KEY,
    geom        GEOMETRY(Point, 4326) NOT NULL,
    lon         DOUBLE PRECISION,
    lat         DOUBLE PRECISION,
    dom_cat     TEXT,
    dom_cat_cn  TEXT,
    categories  TEXT[],
    county      TEXT,
    county_cn   TEXT,
    score       NUMERIC,
    level       INTEGER,
    level_cn    TEXT,
    hotspot     TEXT,
    gi          NUMERIC
);
"""

INSERT = """
INSERT INTO mines
    (geom, lon, lat, dom_cat, dom_cat_cn, categories, county, county_cn,
     score, level, level_cn, hotspot, gi)
VALUES
    (ST_SetSRID(ST_MakePoint(%s, %s), 4326),
     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def parse_points():
    s = open(SRC, encoding="utf-8").read()
    m = re.search(r"window\.POINT_SCORE\s*=\s*(\{.*\})\s*;", s, re.S)
    obj = json.loads(m.group(1))
    return obj["meta"], obj["pts"]


def main():
    meta, pts = parse_points()
    cat_cn = meta["catCn"]
    lv_cn = meta["lvCn"]

    conn = psycopg2.connect(**PG)
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("TRUNCATE mines;")
    rows = []
    for p in pts:
        cc = COUNTY_CN.get(p["county"], p["county"])
        rows.append((
            p["lon"], p["lat"],
            p["dom"], cat_cn.get(p["dom"], p["dom"]),
            p["cats"], p["county"], cc,
            p["score"], p["lv"], lv_cn.get(str(p["lv"]), ""),
            p["hs"], p["gi"],
        ))
    cur.executemany(INSERT, rows)
    cur.execute("CREATE INDEX IF NOT EXISTS mines_geom_gist ON mines USING GIST (geom);")
    conn.commit()

    cur.execute("SELECT count(*) FROM mines;")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"✅ 导入完成：mines 共 {n} 行（来自 {len(pts)} 个原始点）")


if __name__ == "__main__":
    main()
