# -*- coding: utf-8 -*-
"""
大余县行政边界获取与预处理
数据源：阿里云 DataV.GeoAtlas（https://geo.datav.aliyun.com/areas_v3/）
输出：dayu_boundary.geojson / dayu_boundary_wgs84.shp / dayu_extent.json
"""
import json
import os
import urllib.request

import geopandas as gpd
from shapely.geometry import shape

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "boundary")
os.makedirs(OUT, exist_ok=True)

PROXY = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("http_proxy")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch(url, binary=False):
    if PROXY:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", UA)]
    data = opener.open(url, timeout=90).read()
    return data if binary else data.decode("utf-8")


def main():
    # 1. 拉取赣州市 18 个区县
    url = "https://geo.datav.aliyun.com/areas_v3/bound/360700_full.json"
    gj = json.loads(fetch(url))
    print(f"[1] 赣州市要素数: {len(gj['features'])}")

    feat = None
    for f in gj["features"]:
        if f["properties"].get("name") == "大余县":
            feat = f
            break
    if feat is None:
        raise SystemExit("未找到大余县")

    adcode = feat["properties"]["adcode"]
    print(f"[2] 命中: {adcode} 大余县, center={feat['properties'].get('center')}")

    # 2. 保存原始 geojson（单要素）
    single = {"type": "FeatureCollection", "features": [feat]}
    geojson_path = os.path.join(OUT, "dayu_boundary.geojson")
    with open(geojson_path, "w", encoding="utf-8") as fp:
        json.dump(single, fp, ensure_ascii=False, indent=1)
    print(f"[3] 已保存 geojson -> {geojson_path}")

    # 3. 转 GeoDataFrame，重投影到 WGS84 / Albers，输出 shp
    gdf = gpd.GeoDataFrame(
        {"adcode": [adcode], "name": ["大余县"]},
        geometry=[shape(feat["geometry"])],
        crs="EPSG:4326",
    )

    # CLCD 使用的 Albers 等面积投影
    ALBERS = (
        "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    gdf_albers = gdf.to_crs(ALBERS)

    # 面积核算（用于与三调数据交叉验证）
    area_km2 = gdf_albers.geometry.area.iloc[0] / 1e6
    area_mu = area_km2 * 1500
    print(f"[4] 面积核算: {area_km2:.2f} km²  ({area_mu/1e4:.2f} 万亩)")
    print(f"    官方口径: 1343.63 km² -> 偏差 {area_km2 - 1343.63:+.2f} km²")

    shp_path = os.path.join(OUT, "dayu_boundary_albers.shp")
    gdf_albers.to_file(shp_path, encoding="utf-8")
    print(f"[5] 已保存 Albers shp -> {shp_path}")

    gdf.to_file(os.path.join(OUT, "dayu_boundary_wgs84.shp"), encoding="utf-8")
    print(f"[6] 已保存 WGS84 shp -> {os.path.join(OUT, 'dayu_boundary_wgs84.shp')}")

    # 4. 输出裁剪窗口（Albers 坐标 + 1km buffer，buffer 用于抵消 GCJ-02/WGS84 偏移）
    minx, miny, maxx, maxy = gdf_albers.total_bounds
    buf = 1000  # m
    extent = {
        "adcode": adcode,
        "crs_albers_proj4": ALBERS,
        "bbox_albers": [minx - buf, miny - buf, maxx + buf, maxy + buf],
        "bbox_wgs84": list(gdf.total_bounds),
        "buffer_m": buf,
        "note": "bbox_albers 已加 1km buffer，用于从 CLCD 裁剪；geojson/shp 为原始边界",
    }
    ext_path = os.path.join(OUT, "dayu_extent.json")
    with open(ext_path, "w", encoding="utf-8") as fp:
        json.dump(extent, fp, ensure_ascii=False, indent=1)
    print(f"[7] 已保存裁剪窗口 -> {ext_path}")
    print("    Albers bbox:", [round(v, 1) for v in extent["bbox_albers"]])
    print("    WGS84 bbox :", [round(v, 5) for v in extent["bbox_wgs84"]])

    # 5. 顺便抓取乡镇级边界（后续做乡镇差异化管控用）
    try:
        town_url = f"https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json"
        town = json.loads(fetch(town_url))
        tp = os.path.join(OUT, "dayu_towns.geojson")
        with open(tp, "w", encoding="utf-8") as fp:
            json.dump(town, fp, ensure_ascii=False, indent=1)
        names = [f["properties"].get("name") for f in town["features"]]
        print(f"[8] 已保存乡镇边界 -> {tp}  共 {len(names)} 个: {'、'.join(names)}")
    except Exception as exc:
        print(f"[8] 乡镇边界获取失败: {exc}")


if __name__ == "__main__":
    main()
