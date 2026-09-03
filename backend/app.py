"""赣南稀土矿脉 · 空间查询 API（FastAPI + PostGIS）。

启动：
    backend/.venv/Scripts/python.exe -m uvicorn app:app --port 8000 --reload

接口（返回 GeoJSON / JSON）：
    GET /health                  服务与 PostGIS 版本
    GET /mines                   矿点列表，支持过滤
        ?bbox=minx,miny,maxx,maxy   经纬度框选（WGS84）
        ?cat=tungsten               矿种（dom / categories 命中）
        ?level=2                     等级 0/1/2
        ?hotspot=热点                冷热点标签
        ?limit=200                   返回上限
    GET /mines/{id}              单个矿点
    GET /mines/near?lon=&lat=&km=  周边 km 内的矿点（geography 精确距离）
    GET /hotspots                所有热点/次热点矿点（按 Gi* 降序）
    GET /stats                   按县 / 矿种 / 等级 的统计

说明：
- 所有空间运算都在 PostGIS 里完成（ST_MakeEnvelope / ST_DWithin / GIST 索引），
  这是真实生产做法；408 个点虽小，但写法可直接扩展到百万级。
- /mines/near 用 geography 类型做米级精确距离，避免经纬度“度”近似误差。
"""
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2

from config import PG

app = FastAPI(title="赣南稀土矿脉空间 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发期允许前端大屏跨域；生产请改成具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)

COLUMNS = (
    "id, lon, lat, dom_cat, dom_cat_cn, categories, county, county_cn, "
    "score, level, level_cn, hotspot, gi, ST_AsGeoJSON(geom) AS geom"
)


def get_conn():
    return psycopg2.connect(**PG)


def to_geojson(cur):
    """把 SELECT ... ST_AsGeoJSON(geom) 的结果拼成 FeatureCollection。"""
    cols = [d[0] for d in cur.description]
    feats = []
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        geom_txt = d.pop("geom")
        geom = json.loads(geom_txt) if isinstance(geom_txt, str) else geom_txt
        feats.append({"type": "Feature", "geometry": geom, "properties": d})
    return {"type": "FeatureCollection", "features": feats}


@app.get("/health")
def health():
    c = get_conn()
    cur = c.cursor()
    cur.execute("SELECT PostGIS_Full_Version();")
    version = cur.fetchone()[0]
    cur.close()
    c.close()
    return {"status": "ok", "postgis": version}


@app.get("/mines")
def mines(
    bbox: Optional[str] = None,      # minx,miny,maxx,maxy
    cat: Optional[str] = None,       # 矿种 key，如 tungsten
    level: Optional[int] = None,
    hotspot: Optional[str] = None,   # 热点 / 次热点 / 不显著
    limit: int = Query(200, le=1000),
):
    where, params = [], []
    if bbox:
        minx, miny, maxx, maxy = map(float, bbox.split(","))
        where.append("geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params += [minx, miny, maxx, maxy]
    if cat:
        where.append("%s = ANY(categories)")
        params.append(cat)
    if level is not None:
        where.append("level = %s")
        params.append(level)
    if hotspot:
        where.append("hotspot = %s")
        params.append(hotspot)

    sql = f"SELECT {COLUMNS} FROM mines"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY score DESC LIMIT %d" % int(limit)

    c = get_conn()
    cur = c.cursor()
    cur.execute(sql, params)
    fc = to_geojson(cur)
    cur.close()
    c.close()
    return fc


@app.get("/mines/{mid}")
def mine(mid: int):
    c = get_conn()
    cur = c.cursor()
    cur.execute(f"SELECT {COLUMNS} FROM mines WHERE id = %s", (mid,))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    cur.close()
    c.close()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该矿点")
    d = dict(zip(cols, row))
    geom = json.loads(d.pop("geom")) if isinstance(d["geom"], str) else d["geom"]
    return {"type": "Feature", "geometry": geom, "properties": d}


@app.get("/mines/near")
def near(lon: float = Query(...), lat: float = Query(...), km: float = 10):
    """周边 km 内的矿点：用 geography 类型算米级精确距离。"""
    c = get_conn()
    cur = c.cursor()
    sql = f"""
        SELECT {COLUMNS},
               ST_Distance(geom::geography,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS dist_m
        FROM mines
        WHERE ST_DWithin(geom::geography,
                         ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
        ORDER BY dist_m
        LIMIT 50
    """
    cur.execute(sql, (lon, lat, lon, lat, km * 1000))
    fc = to_geojson(cur)
    cur.close()
    c.close()
    return fc


@app.get("/hotspots")
def hotspots():
    c = get_conn()
    cur = c.cursor()
    cur.execute(
        f"SELECT {COLUMNS} FROM mines "
        f"WHERE hotspot IN ('热点', '次热点') ORDER BY gi DESC"
    )
    fc = to_geojson(cur)
    cur.close()
    c.close()
    return fc


@app.get("/stats")
def stats():
    c = get_conn()
    cur = c.cursor()
    out = {}
    cur.execute("SELECT county_cn, count(*) FROM mines GROUP BY county_cn ORDER BY 2 DESC")
    out["by_county"] = [{"county_cn": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT dom_cat_cn, count(*) FROM mines GROUP BY dom_cat_cn ORDER BY 2 DESC")
    out["by_cat"] = [{"cat": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT level_cn, count(*) FROM mines GROUP BY level_cn ORDER BY level_cn")
    out["by_level"] = [{"level": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT count(*) FROM mines WHERE hotspot = '热点'")
    out["hotspot_count"] = cur.fetchone()[0]
    cur.close()
    c.close()
    return out
