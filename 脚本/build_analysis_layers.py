# -*- coding: utf-8 -*-
"""把分析结果 shapefile(GeoJSON) 打包成 analysis_layers.js (window.AL)
- 坐标保留 4 位小数压缩体积
- 仅保留配色/标注所需属性
- 按矿种大类 6 个文件合并为一个 FeatureCollection
"""
import json, os, glob, subprocess, io

ROOT = "E:/Data/赣州稀土"
BLD = os.path.join(ROOT, ".build")
OUT = os.path.join(ROOT, "analysis_layers.js")
OGR = "E:/adaconda/Library/bin/ogr2ogr.exe"


def round_coords(g, nd=4):
    if isinstance(g, (int, float)):
        return round(g, nd)
    if isinstance(g, list):
        return [round_coords(x, nd) for x in g]
    return g


def load(path, keep=None):
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    feats = []
    for ft in d.get("features", []):
        geom = ft.get("geometry")
        if not geom or geom.get("type") is None:
            continue
        geom["coordinates"] = round_coords(geom["coordinates"], 4)
        props = ft.get("properties", {}) or {}
        if keep:
            props = {k: props.get(k) for k in keep if k in props}
        # 清掉 None
        props = {k: v for k, v in props.items() if v is not None}
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return feats


def dump_geojson(feats):
    return {"type": "FeatureCollection", "features": feats}


# 1) 单文件层（已转好）
single = {
    "density":      ("渔网格网_矿点密度.json",       ["count", "ratio"]),
    "lisa":         ("局域莫兰指数_LISA.json",        ["cluster", "local_I", "z_std"]),
    "voronoi":      ("泰森多边形.json",                ["density", "area_km2"]),
    "nn":           ("矿场点_最近邻分析.json",          ["nearest_d"]),
    "gistar_grid":  ("渔网格网_冷热点分析_GiStar.json", ["hotspot_cl", "Gi_ZScore"]),
    "gistar_point": ("矿点_冷热点分析_GiStar.json",     ["hotspot_cl", "Gi_ZScore"]),
    "county":       ("county_stats.json",             ["name_cn", "mine_cnt", "density", "top_minerl"]),
}

AL = {}
for key, (fn, keep) in single.items():
    feats = load(os.path.join(BLD, fn), keep)
    AL[key] = dump_geojson(feats)
    print("  %-12s %5d features  %8d bytes" % (key, len(feats), len(json.dumps(AL[key], ensure_ascii=False))))

# 2) 按矿种大类：6 个文件合并，统一加 大类 字段
cat_dir = os.path.join(ROOT, "结果输出/矿区分类/按矿种大类")
allfeats = []
for shp in sorted(glob.glob(os.path.join(cat_dir, "*.shp"))):
    base = os.path.splitext(os.path.basename(shp))[0]
    tmp = os.path.join(BLD, "cat_" + base + ".json")
    subprocess.run([OGR, "-f", "GeoJSON", tmp, shp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    feats = load(tmp, ["大类", "mc", "kz"])
    # 兜底：若大类字段缺失，用文件名
    for ft in feats:
        p = ft["properties"]
        if not p.get("大类"):
            p["大类"] = base
    allfeats += feats
    print("  cat %-10s %5d" % (base, len(feats)))
AL["bycat"] = dump_geojson(allfeats)
print("  %-12s %5d features  %8d bytes" % ("bycat", len(allfeats), len(json.dumps(AL["bycat"], ensure_ascii=False))))

# 3) 写出 analysis_layers.js
meta = {
    "density":      {"name": "矿点核密度(渔网格)", "kind": "poly", "colorBy": "count",   "ramp": "seq"},
    "lisa":         {"name": "LISA 空间自相关",   "kind": "poly", "colorBy": "cluster", "ramp": "cat"},
    "voronoi":      {"name": "泰森多边形",         "kind": "poly", "colorBy": "density", "ramp": "seq"},
    "nn":           {"name": "最近邻分析",         "kind": "point", "colorBy": "nearest_d", "ramp": "seq"},
    "gistar_grid":  {"name": "Gi* 冷热点(网格)",  "kind": "poly", "colorBy": "hotspot_cl", "ramp": "cat"},
    "gistar_point": {"name": "Gi* 冷热点(矿点)",  "kind": "point", "colorBy": "hotspot_cl", "ramp": "cat"},
    "bycat":        {"name": "按矿种大类",         "kind": "point", "colorBy": "大类", "ramp": "cat"},
    "county":       {"name": "县级矿山统计",       "kind": "poly", "colorBy": "mine_cnt", "ramp": "seq", "label": "name_cn"},
}
out = ["// 自动生成 by 脚本/build_analysis_layers.py —— 分析结果图层包",
       "// 坐标系 WGS84(EPSG:4326)，坐标 4 位小数",
       "window.AL_META = " + json.dumps(meta, ensure_ascii=False) + ";",
       "window.AL = {",
       "  density: " + json.dumps(AL["density"], ensure_ascii=False) + ",",
       "  lisa: " + json.dumps(AL["lisa"], ensure_ascii=False) + ",",
       "  voronoi: " + json.dumps(AL["voronoi"], ensure_ascii=False) + ",",
       "  nn: " + json.dumps(AL["nn"], ensure_ascii=False) + ",",
       "  gistar_grid: " + json.dumps(AL["gistar_grid"], ensure_ascii=False) + ",",
       "  gistar_point: " + json.dumps(AL["gistar_point"], ensure_ascii=False) + ",",
       "  bycat: " + json.dumps(AL["bycat"], ensure_ascii=False) + ",",
       "  county: " + json.dumps(AL["county"], ensure_ascii=False),
       "};"]
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("written:", OUT, os.path.getsize(OUT), "bytes")
