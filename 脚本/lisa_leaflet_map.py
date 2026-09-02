# -*- coding: utf-8 -*-
"""
生成 LISA 聚类交互式矢量地图 (Leaflet)
输出: 莫兰指数图表/LISA聚类地图.html
"""

import os, json
import numpy as np
import shapefile
from shapely.geometry import Polygon, Point, mapping

BASE = r"E:\Data\赣州稀土"
LISA_SHP = os.path.join(BASE, "空间分布分析结果", "局域莫兰指数_LISA.shp")
COUNTY_SHP = os.path.join(BASE, "县级汇总结果", "county_stats.shp")
MINES_SHP = os.path.join(BASE, "空间分布分析结果", "裁剪后", "赣州矿场点_裁剪后.shp")
OUT_DIR = os.path.join(BASE, "莫兰指数图表")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 颜色方案 ──────────────────────────────────────────
CLUSTER_COLORS = {
    "高-高集聚 (HH)": "#d73027",
    "高-低集聚 (HL)": "#fc8d59",
    "低-高集聚 (LH)": "#91bfdb",
    "低-低集聚 (LL)": "#4575b4",
    "不显著 (NS)":   "#e8e8e8",
}
CLUSTER_OPACITY = {
    "高-高集聚 (HH)": 0.85,
    "高-低集聚 (HL)": 0.75,
    "低-高集聚 (LH)": 0.65,
    "低-低集聚 (LL)": 0.75,
    "不显著 (NS)":   0.35,
}

# 县级英文→中文名
COUNTY_NAMES = {
    "Anyuan": "安远县", "Chongyi": "崇义县", "Dayu": "大余县",
    "Dingnan": "定南县", "Ganxian": "赣县区", "Huichang": "会昌县",
    "Longnan": "龙南市", "Nankang": "南康区", "Ningdu": "宁都县",
    "Quannan": "全南县", "Ruijin": "瑞金市", "Shangyou": "上犹县",
    "Shicheng": "石城县", "Xinfeng": "信丰县", "Xunwu": "寻乌县",
    "Xingguo": "兴国县", "Yudu": "于都县", "Zhanggong": "章贡区",
}

# ── 加载 LISA 数据 ────────────────────────────────────
print("加载 LISA 网格数据...")
sf_lisa = shapefile.Reader(LISA_SHP, encoding="gbk")
lisa_fields = [f[0] for f in sf_lisa.fields[1:]]
lisa_recs = sf_lisa.records()
lisa_shapes = sf_lisa.shapes()
print(f"  LISA 网格: {len(lisa_shapes)} 个")

field_idx = {f: i for i, f in enumerate(lisa_fields)}

# 按聚类类型分组 GeoJSON features (简化几何以减少文件大小)
tolerance = 0.003  # ~300m at this latitude
lisa_features_by_cluster = {k: [] for k in CLUSTER_COLORS}
for shp, rec in zip(lisa_shapes, lisa_recs):
    cluster_label = rec[field_idx["cluster"]].strip()
    if cluster_label not in lisa_features_by_cluster:
        # 尝试模糊匹配
        matched = False
        for k in lisa_features_by_cluster:
            if k.split("(")[0].strip() in cluster_label:
                cluster_label = k
                matched = True
                break
        if not matched:
            cluster_label = "不显著 (NS)"

    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    rings = []
    for i in range(len(parts) - 1):
        ring = pts[parts[i]:parts[i+1]]
        if len(ring) >= 3 and ring[0] == ring[-1]:
            rings.append(ring)

    if not rings:
        continue

    geom = {"type": "Polygon", "coordinates": [rings[0]]}
    if len(rings) > 1:
        geom["coordinates"].extend(rings[1:])

    prop = {
        "row": rec[field_idx["cell_row"]],
        "col": rec[field_idx["cell_col"]],
        "count": rec[field_idx["count"]],
        "local_I": round(rec[field_idx["local_I"]], 4),
        "p_value": round(rec[field_idx["p_value"]], 4),
        "cluster": cluster_label,
    }
    lisa_features_by_cluster[cluster_label].append({
        "type": "Feature", "properties": prop, "geometry": geom
    })

sf_lisa.close()

# ── 统计 ──────────────────────────────────────────────
cluster_counts = {}
for k, feats in lisa_features_by_cluster.items():
    cluster_counts[k] = len(feats)

# ── 加载县级边界 ──────────────────────────────────────
print("加载县级边界...")
sf_county = shapefile.Reader(COUNTY_SHP, encoding="utf-8", encodingErrors="replace")
county_fields = [f[0] for f in sf_county.fields[1:]]
county_recs = sf_county.records()
county_shapes = sf_county.shapes()
eng_idx = county_fields.index("eng_name")

county_features = []
for shp, rec in zip(county_shapes, county_recs):
    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    for i in range(len(parts) - 1):
        ring = pts[parts[i]:parts[i+1]]
        if len(ring) >= 3:
            eng = str(rec[eng_idx])
            county_features.append({
                "type": "Feature",
                "properties": {"name": COUNTY_NAMES.get(eng, eng), "eng_name": eng},
                "geometry": {"type": "Polygon", "coordinates": [ring]}
            })
            break
sf_county.close()

# ── 加载矿点 ──────────────────────────────────────────
print("加载矿点...")
sf_mines = shapefile.Reader(MINES_SHP, encoding="gbk")
mine_fields = [f[0] for f in sf_mines.fields[1:]]
mine_recs = sf_mines.records()
mine_shapes = sf_mines.shapes()

# 找关键字段
mc_idx = mine_fields.index("mc") if "mc" in mine_fields else None
kz_idx = mine_fields.index("kz") if "kz" in mine_fields else None

mine_features = []
for shp, rec in zip(mine_shapes, mine_recs):
    x, y = shp.points[0]
    props = {"lon": round(x, 4), "lat": round(y, 4)}
    if mc_idx is not None:
        props["name"] = str(rec[mc_idx])
    if kz_idx is not None:
        props["mineral"] = str(rec[kz_idx])
    mine_features.append({
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [x, y]}
    })
sf_mines.close()
print(f"  矿点: {len(mine_features)} 个")

# ── 生成 HTML ─────────────────────────────────────────
print("生成交互式矢量地图...")

# 将 GeoJSON 嵌入页面
lisa_geojson = {}
for k, v in lisa_features_by_cluster.items():
    short_key = k.split("(")[1].rstrip(")") if "(" in k else k[:4]
    lisa_geojson[short_key] = json.dumps({"type": "FeatureCollection", "features": v}, ensure_ascii=False)

county_geojson_str = json.dumps({"type": "FeatureCollection", "features": county_features}, ensure_ascii=False)
mine_geojson_str = json.dumps({"type": "FeatureCollection", "features": mine_features}, ensure_ascii=False)

# 统计表行
stats_rows = ""
for lbl in ["高-高集聚 (HH)", "高-低集聚 (HL)", "低-高集聚 (LH)", "低-低集聚 (LL)", "不显著 (NS)"]:
    cnt = cluster_counts.get(lbl, 0)
    short = lbl.split("(")[0].strip()
    pct = cnt / len(lisa_shapes) * 100
    color = CLUSTER_COLORS[lbl]
    stats_rows += f'<tr><td><span style="display:inline-block;width:14px;height:14px;background:{color};border-radius:2px;margin-right:6px;vertical-align:middle;"></span>{short}</td><td>{cnt}</td><td>{pct:.1f}%</td></tr>\n'

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>赣州市矿山 LISA 聚类地图</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; background: #f5f0e8; }}
#map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
.info-panel {{
  position: absolute; top: 16px; right: 16px; z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 16px 20px;
  min-width: 220px; font-size: 13px; line-height: 1.7;
}}
.info-panel h2 {{ font-size: 16px; margin-bottom: 8px; color: #3a2a18; }}
.info-panel h3 {{ font-size: 12px; color: #988b7a; font-weight: normal; margin-bottom: 10px; }}
.info-panel table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.info-panel td {{ padding: 2px 6px; }}
.info-panel tr.total {{ border-top: 1px solid #d0c8b8; font-weight: bold; }}
.legend-panel {{
  position: absolute; bottom: 30px; left: 16px; z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 12px 16px;
  font-size: 12px;
}}
.legend-item {{ display: flex; align-items: center; margin: 4px 0; }}
.legend-swatch {{ width: 20px; height: 14px; border-radius: 2px; margin-right: 8px; border: 1px solid rgba(0,0,0,0.15); }}
.layer-toggle {{
  position: absolute; top: 16px; left: 16px; z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 10px 14px;
  font-size: 12px;
}}
.layer-toggle label {{ display: block; margin: 2px 0; cursor: pointer; }}
.footer-info {{
  position: absolute; bottom: 10px; right: 16px; z-index: 1000;
  font-size: 10px; color: #988b7a;
  background: rgba(255,255,255,0.85); padding: 3px 10px; border-radius: 4px;
}}
</style>
</head>
<body>

<div id="map"></div>

<div class="layer-toggle">
  <strong>图层控制</strong>
  <label><input type="checkbox" id="toggleHH" checked onchange="toggleCluster('HH')"> 高-高集聚 (HH)</label>
  <label><input type="checkbox" id="toggleHL" checked onchange="toggleCluster('HL')"> 高-低集聚 (HL)</label>
  <label><input type="checkbox" id="toggleLH" checked onchange="toggleCluster('LH')"> 低-高集聚 (LH)</label>
  <label><input type="checkbox" id="toggleLL" checked onchange="toggleCluster('LL')"> 低-低集聚 (LL)</label>
  <label><input type="checkbox" id="toggleNS" onchange="toggleCluster('NS')"> 不显著 (NS)</label>
  <hr style="margin:4px 0;border-color:#e0d8c8;">
  <label><input type="checkbox" id="toggleMines" checked onchange="toggleLayer('mines')"> 矿点 (474个)</label>
  <label><input type="checkbox" id="toggleCounty" checked onchange="toggleLayer('county')"> 县级边界</label>
</div>

<div class="info-panel">
  <h2>赣州市矿山 LISA 聚类</h2>
  <h3>Local Moran's I · KNN k=8 · 999 permutations</h3>
  <table>
    {stats_rows}
    <tr class="total"><td>合计</td><td>{len(lisa_shapes)}</td><td>100%</td></tr>
  </table>
  <p style="font-size:10px;color:#988b7a;margin-top:8px;">Moran's I = 0.1424 &nbsp; p = 0.001</p>
  <p style="font-size:10px;color:#988b7a;">Z-score = 19.27</p>
</div>

<div class="footer-info">
  数据来源: 全国矿产地分布数据 (2025) · PySAL/esda · Leaflet
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ── 底图 ──────────────────────────────────────────
const map = L.map("map", {{ attributionControl: true }}).setView([25.85, 115.2], 9);

// 浅色底图
// 高德地图浅色底图 (国内访问快)
L.tileLayer("https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={{x}}&y={{y}}&z={{z}}", {{
  attribution: '&copy; <a href="https://www.amap.com/">高德地图</a>',
  subdomains: "1234",
  maxZoom: 18
}}).addTo(map);

// ── LISA 聚类图层 ──────────────────────────────────
const clusterColors = {json.dumps(CLUSTER_COLORS, ensure_ascii=False)};
const clusterOpacity = {json.dumps(CLUSTER_OPACITY)};

const lisaLayers = {{}};
const lisaData = {{}};
'''

# 嵌入各聚类类型 GeoJSON
for short_key, geojson_str in lisa_geojson.items():
    html += f'''
lisaData["{short_key}"] = {geojson_str};
'''

html += '''
for (const [key, geojson] of Object.entries(lisaData)) {
  const color = clusterColors[Object.keys(clusterColors).find(k => k.includes(key))] || "#cccccc";
  const opacity = clusterOpacity[Object.keys(clusterOpacity).find(k => k.includes(key))] || 0.5;
  lisaLayers[key] = L.geoJSON(geojson, {
    style: { color: color, weight: 0, fillColor: color, fillOpacity: opacity },
    onEachFeature: function(feature, layer) {
      const p = feature.properties;
      layer.bindPopup(
        `<b>${p.cluster}</b><br>` +
        `网格 (${p.row}, ${p.col})<br>` +
        `矿点数: ${p.count}<br>` +
        `Local I: ${p.local_I}<br>` +
        `p-value: ${p.p_value}`
      );
    }
  }).addTo(map);
}

// ── 县级边界 ──────────────────────────────────────
const countyGeojson = ''' + county_geojson_str + ''';
const countyLayer = L.geoJSON(countyGeojson, {
  style: { color: "#5c4a3a", weight: 1.2, fill: false, dashArray: "4 2" },
  onEachFeature: function(feature, layer) {
    layer.bindPopup(`<b>${feature.properties.name}</b>`);
  }
}).addTo(map);

// ── 矿点 ──────────────────────────────────────────
const mineGeojson = ''' + mine_geojson_str + ''';
const mineLayer = L.geoJSON(mineGeojson, {
  pointToLayer: function(feature, latlng) {
    return L.circleMarker(latlng, {
      radius: 3.5, fillColor: "#1a1a1a", color: "#fff", weight: 0.5,
      fillOpacity: 0.85
    });
  },
  onEachFeature: function(feature, layer) {
    const p = feature.properties;
    layer.bindPopup(`<b>${p.name || "矿点"}</b><br>矿种: ${p.mineral || "未知"}<br>坐标: ${p.lon}, ${p.lat}`);
  }
}).addTo(map);

// ── 图层切换 ──────────────────────────────────────
function toggleCluster(key) {{
  const checkbox = document.getElementById("toggle" + key);
  if (checkbox.checked) {{
    if (!map.hasLayer(lisaLayers[key])) lisaLayers[key].addTo(map);
  }} else {{
    if (map.hasLayer(lisaLayers[key])) map.removeLayer(lisaLayers[key]);
  }}
}}

function toggleLayer(name) {{
  const checkbox = document.getElementById("toggle" + name.charAt(0).toUpperCase() + name.slice(1));
  if (name === "mines") {{
    if (checkbox.checked) mineLayer.addTo(map);
    else map.removeLayer(mineLayer);
  }} else if (name === "county") {{
    if (checkbox.checked) countyLayer.addTo(map);
    else map.removeLayer(countyLayer);
  }}
}}
</script>

</body>
</html>
'''

out_html = os.path.join(OUT_DIR, "LISA聚类地图.html")
with open(out_html, 'w', encoding='utf-8') as f:
    f.write(html)

file_size_kb = os.path.getsize(out_html) / 1024
print(f"  -> {out_html} ({file_size_kb:.1f} KB)")
print("完毕!")
