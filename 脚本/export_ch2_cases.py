# -*- coding: utf-8 -*-
"""
解析 第二章例子汇总.txt, 生成矢量点数据 (Shapefile + GeoJSON + CSV)
"""

import os, csv, json
import shapefile
from shapely.geometry import Point

BASE = r"E:\Data\赣州稀土"
SRC_TXT = os.path.join(BASE, "第二章例子汇总.txt")
OUT_DIR = os.path.join(BASE, "第二章案例矢量数据")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 硬解析表格数据 ────────────────────────────────────
# 根据补充说明中的符号分类
records = [
    # 2.1 石英脉型黑钨矿 → 蓝色圆点, time=1 (传统井下开采)
    {"name": "盘古山钨矿",    "county": "于都县", "lon": 115.4350, "lat": 25.6570,
     "method": "地下巷道开采", "desc": "大型石英脉黑钨铋矿床，百年老矿，扰动集中于废石堆场",
     "category": "钨矿", "symbol": "blue_circle", "reliability": 3, "time": 1},
    {"name": "漂塘钨矿",      "county": "大余县", "lon": 114.4000, "lat": 25.5170,
     "method": "地下巷道开采", "desc": "崇义-大余钨矿核心成矿带，西华山矿田东侧",
     "category": "钨矿", "symbol": "blue_circle", "reliability": 4, "time": 1},
    {"name": "黄沙钨矿（铁山垅）", "county": "于都县", "lon": 115.3000, "lat": 25.7330,
     "method": "地下巷道开采", "desc": "配套标准化排土场，地表人为扰动可控",
     "category": "钨矿", "symbol": "blue_circle", "reliability": 4, "time": 1},

    # 2.2 非金属建材矿产 → 黄色方块, time=2 (露天开采)
    {"name": "石古前石灰岩矿",  "county": "信丰县", "lon": 114.8900, "lat": 25.4630,
     "method": "露天台阶开采", "desc": "大型水泥原料矿山，年产260万吨，大面积植被剥离",
     "category": "非金属露天矿", "symbol": "yellow_square", "reliability": 4, "time": 2},
    {"name": "富家地硅石矿",    "county": "兴国县", "lon": 115.7614, "lat": 26.5408,
     "method": "露天开采", "desc": "坡面开挖，水土流失风险较高",
     "category": "非金属露天矿", "symbol": "yellow_square", "reliability": 4, "time": 2},
    {"name": "武当小河背石英矿", "county": "龙南市", "lon": 114.6760, "lat": 24.5620,
     "method": "露天开采", "desc": "脉石英矿，山体表层直接开挖",
     "category": "非金属露天矿", "symbol": "yellow_square", "reliability": 3, "time": 2},
    {"name": "隆坪萤石矿",      "county": "兴国县", "lon": 115.2540, "lat": 26.3778,
     "method": "露天开采", "desc": "萤石开采，存在氟化物水土污染隐患",
     "category": "非金属露天矿", "symbol": "yellow_square", "reliability": 4, "time": 2},
    {"name": "水尾山萤石矿",    "county": "全南县", "lon": 114.4400, "lat": 24.7920,
     "method": "露天开采", "desc": "保有资源量161.5万吨，连片露天采坑",
     "category": "非金属露天矿", "symbol": "yellow_square", "reliability": 4, "time": 2},

    # 2.3 离子吸附型稀土矿, time=3 (稀土浸矿工艺)
    # 池浸/堆浸 → 红色三角
    {"name": "足洞重稀土矿(701矿)", "county": "龙南市", "lon": 114.9050, "lat": 24.8210,
     "method": "池浸", "desc": "全坡面铲山，风化壳彻底剥离，植被毁灭性破坏",
     "category": "稀土池浸/堆浸", "symbol": "red_triangle", "reliability": 4, "time": 3},
    {"name": "甲子背稀土矿",    "county": "定南县", "lon": 115.0380, "lat": 24.9470,
     "method": "堆浸", "desc": "大面积表土剥离，筑堆浸矿，地表破坏严重",
     "category": "稀土池浸/堆浸", "symbol": "red_triangle", "reliability": 4, "time": 3},

    # 传统原地浸矿 → 橙色三角
    {"name": "三丘田稀土矿",    "county": "定南县", "lon": 115.0760, "lat": 24.9070,
     "method": "传统原地浸矿", "desc": "保留地表植被，铵盐药剂易造成地下水污染",
     "category": "传统原地浸矿", "symbol": "orange_triangle", "reliability": 4, "time": 3},
    {"name": "长坑尾稀土矿",    "county": "定南县", "lon": 115.0580, "lat": 24.9320,
     "method": "传统原地浸矿", "desc": "注液井浸取，土壤氨氮长期胁迫植被生长",
     "category": "传统原地浸矿", "symbol": "orange_triangle", "reliability": 4, "time": 3},
    {"name": "内头坑稀土矿",    "county": "定南县", "lon": 115.1020, "lat": 24.9620,
     "method": "传统原地浸矿", "desc": "山地原地浸矿，生态修复周期较长",
     "category": "传统原地浸矿", "symbol": "orange_triangle", "reliability": 4, "time": 3},

    # 无铵绿色原地浸矿 → 绿色三角
    {"name": "木子山稀土矿（上下营）", "county": "定南县", "lon": 115.0020, "lat": 24.9496,
     "method": "无铵绿色原地浸矿", "desc": "无需铲山、无铵盐污染，原生植被基本保留",
     "category": "无铵绿色稀土", "symbol": "green_triangle", "reliability": 4, "time": 3},
]

# ── 符号配置 ──────────────────────────────────────────
SYMBOL_CFG = {
    "blue_circle":      {"type": "circle", "color": "#2c7fb8", "size": 8, "label": "钨矿（井下开采）"},
    "yellow_square":    {"type": "square", "color": "#f0a030", "size": 10, "label": "非金属露天矿"},
    "red_triangle":     {"type": "triangle", "color": "#d73027", "size": 10, "label": "稀土池浸/堆浸"},
    "orange_triangle":  {"type": "triangle", "color": "#fc8d59", "size": 10, "label": "传统原地浸矿"},
    "green_triangle":   {"type": "triangle", "color": "#1a9850", "size": 10, "label": "无铵绿色稀土"},
}

# ── 三大类分组 ────────────────────────────────────────
CATEGORIES = {
    "钨矿": {
        "filter": lambda r: r["category"] == "钨矿",
        "label": "钨矿（井下开采）",
    },
    "非金属矿": {
        "filter": lambda r: r["category"] == "非金属露天矿",
        "label": "非金属建材矿产（露天开采）",
    },
    "离子型稀土矿": {
        "filter": lambda r: r["category"] in ("稀土池浸/堆浸", "传统原地浸矿", "无铵绿色稀土"),
        "label": "离子吸附型稀土矿（四代工艺）",
    },
}

def write_sidecar(dirpath: str, basename: str) -> None:
    """写入 .prj / .cpg，并修复 DBF codepage 为 UTF-8"""
    prj = 'GEOGCS["GCS_CGCS_2000",DATUM["D_CGCS_2000",SPHEROID["CGCS_2000",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
    with open(os.path.join(dirpath, basename + ".prj"), "w", encoding="ascii") as f:
        f.write(prj)
    with open(os.path.join(dirpath, basename + ".cpg"), "w", encoding="ascii") as f:
        f.write("UTF-8")
    # 修复 DBF 头部 codepage 字节: 0x75 = UTF-8
    dbf_path = os.path.join(dirpath, basename + ".dbf")
    with open(dbf_path, "r+b") as f:
        f.seek(29)
        f.write(b'\x75')

# ═══════════════════════════════════════════════════════
# 按分类导出 Shapefile + GeoJSON + CSV
# ═══════════════════════════════════════════════════════
for cat_key, cat_cfg in CATEGORIES.items():
    subset = [r for r in records if cat_cfg["filter"](r)]
    cat_dir = os.path.join(OUT_DIR, cat_key)
    os.makedirs(cat_dir, exist_ok=True)
    base_name = f"第二章_{cat_key}"

    # --- Shapefile ---
    print(f"生成 {cat_key} Shapefile ({len(subset)} 个点)...")
    shp_path = os.path.join(cat_dir, base_name + ".shp")
    w = shapefile.Writer(shp_path, shapeType=shapefile.POINT, encoding="utf-8")
    w.field("name", "C", 60)
    w.field("county", "C", 20)
    w.field("lon", "F", decimal=8)
    w.field("lat", "F", decimal=8)
    w.field("method", "C", 30)
    w.field("desc", "C", 120)
    w.field("symbol", "C", 20)
    w.field("reliab", "N", decimal=0)
    w.field("time", "N", decimal=0)
    for r in subset:
        w.point(r["lon"], r["lat"])
        w.record(r["name"], r["county"], r["lon"], r["lat"],
                 r["method"], r["desc"], r["symbol"], r["reliability"], r["time"])
    w.close()
    write_sidecar(cat_dir, base_name)

    # --- GeoJSON ---
    features = []
    for r in subset:
        features.append({
            "type": "Feature",
            "properties": {
                "name": r["name"],
                "county": r["county"],
                "method": r["method"],
                "desc": r["desc"],
                "category": r["category"],
                "symbol": r["symbol"],
                "symbol_type": SYMBOL_CFG[r["symbol"]]["type"],
                "symbol_color": SYMBOL_CFG[r["symbol"]]["color"],
                "reliability": r["reliability"],
                "time": r["time"],
            },
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}
        })
    gj_path = os.path.join(cat_dir, base_name + ".geojson")
    with open(gj_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)

    # --- CSV ---
    csv_path = os.path.join(cat_dir, base_name + ".csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["矿区名称", "所属县域", "经度(°E)", "纬度(°N)", "开采方式",
                          "核心特征", "矿种分类", "符号类型", "可信度", "time"])
        for r in subset:
            writer.writerow([r["name"], r["county"], r["lon"], r["lat"],
                             r["method"], r["desc"], r["category"],
                             SYMBOL_CFG[r["symbol"]]["label"], "★" * r["reliability"], r["time"]])
    print(f"  -> {cat_dir}/")

# ═══════════════════════════════════════════════════════
# 汇总文件 (全部 14 点)
# ═══════════════════════════════════════════════════════
print("生成汇总文件 (全部 14 点)...")
# Shapefile
shp_path = os.path.join(OUT_DIR, "第二章典型案例_全部.shp")
w = shapefile.Writer(shp_path, shapeType=shapefile.POINT, encoding="utf-8")
w.field("name", "C", 60)
w.field("county", "C", 20)
w.field("lon", "F", decimal=8)
w.field("lat", "F", decimal=8)
w.field("method", "C", 30)
w.field("desc", "C", 120)
w.field("category", "C", 20)
w.field("symbol", "C", 20)
w.field("reliab", "N", decimal=0)
w.field("time", "N", decimal=0)
for r in records:
    w.point(r["lon"], r["lat"])
    w.record(r["name"], r["county"], r["lon"], r["lat"],
             r["method"], r["desc"], r["category"], r["symbol"], r["reliability"], r["time"])
w.close()
write_sidecar(OUT_DIR, "第二章典型案例_全部")

# GeoJSON
features_all = []
for r in records:
    features_all.append({
        "type": "Feature",
        "properties": {
            "name": r["name"], "county": r["county"],
            "method": r["method"], "desc": r["desc"],
            "category": r["category"], "symbol": r["symbol"],
            "time": r["time"],
        },
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}
    })
gj_path = os.path.join(OUT_DIR, "第二章典型案例_全部.geojson")
with open(gj_path, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": features_all}, f, ensure_ascii=False, indent=2)

# CSV
csv_path = os.path.join(OUT_DIR, "第二章典型案例_全部.csv")
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["矿区名称", "所属县域", "经度(°E)", "纬度(°N)", "开采方式",
                      "核心特征", "矿种分类", "符号类型", "可信度", "time"])
    for r in records:
        writer.writerow([r["name"], r["county"], r["lon"], r["lat"],
                         r["method"], r["desc"], r["category"],
                         SYMBOL_CFG[r["symbol"]]["label"], "★" * r["reliability"], r["time"]])
print(f"  -> {shp_path}")

# ═══════════════════════════════════════════════════════
# 4. 统计汇总
# ═══════════════════════════════════════════════════════
print("\n=== 统计 ===")
cats = {}
for r in records:
    c = r["category"]
    cats[c] = cats.get(c, 0) + 1
for c, n in cats.items():
    print(f"  {c}: {n} 个")
print(f"  总计: {len(records)} 个典型矿区")

print(f"\n输出目录: {OUT_DIR}")
print("完毕!")
