# -*- coding: utf-8 -*-
"""
为第二章典型案例生成交互式矢量地图 (Leaflet + SVG divIcon)
正确渲染圆点/方块/三角符号
"""

import os, json
import shapefile

BASE = r"E:\Data\赣州稀土"
GEOJSON_PATH = os.path.join(BASE, "第二章案例矢量数据", "第二章典型案例.geojson")
COUNTY_SHP = os.path.join(BASE, "县级汇总结果", "county_stats.shp")
OUT_HTML = os.path.join(BASE, "第二章案例矢量数据", "第二章典型案例_地图.html")

COUNTY_NAMES = {
    "Anyuan": "安远县", "Chongyi": "崇义县", "Dayu": "大余县",
    "Dingnan": "定南县", "Ganxian": "赣县区", "Huichang": "会昌县",
    "Longnan": "龙南市", "Nankang": "南康区", "Ningdu": "宁都县",
    "Quannan": "全南县", "Ruijin": "瑞金市", "Shangyou": "上犹县",
    "Shicheng": "石城县", "Xinfeng": "信丰县", "Xunwu": "寻乌县",
    "Xingguo": "兴国县", "Yudu": "于都县", "Zhanggong": "章贡区",
}

SYMBOLS_JS = json.dumps({
    "blue_circle":     {"shape": "circle",   "color": "#2c7fb8", "size": 14, "label": "钨矿（井下开采）"},
    "yellow_square":   {"shape": "square",   "color": "#e09020", "size": 16, "label": "非金属露天矿"},
    "red_triangle":    {"shape": "triangle", "color": "#d73027", "size": 18, "label": "稀土池浸/堆浸"},
    "orange_triangle": {"shape": "triangle", "color": "#fc8d59", "size": 18, "label": "传统原地浸矿"},
    "green_triangle":  {"shape": "triangle", "color": "#1a9850", "size": 18, "label": "无铵绿色稀土"},
})

# ── 加载县级边界 ──────────────────────────────────────
print("加载县级边界...")
sf = shapefile.Reader(COUNTY_SHP, encoding="utf-8", encodingErrors="replace")
fields = [f[0] for f in sf.fields[1:]]
recs = sf.records()
shapes = sf.shapes()
eng_idx = fields.index("eng_name")

county_features = []
for shp, rec in zip(shapes, recs):
    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    for i in range(len(parts) - 1):
        ring = pts[parts[i]:parts[i+1]]
        if len(ring) >= 3:
            eng = str(rec[eng_idx])
            county_features.append({
                "type": "Feature",
                "properties": {"name": COUNTY_NAMES.get(eng, eng)},
                "geometry": {"type": "Polygon", "coordinates": [ring]}
            })
            break
sf.close()

COUNTY_GJ = json.dumps({"type": "FeatureCollection", "features": county_features}, ensure_ascii=False)

# ── 读取案例 GeoJSON ──────────────────────────────────
with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
    CASES_GJ = json.dumps(json.load(f), ensure_ascii=False)

# ── 生成 HTML ─────────────────────────────────────────
print("生成交互式矢量地图...")

# 双层花括号: Python {{ → HTML {
html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>第二章典型案例 — 赣州典型矿区分布</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei","SimHei",sans-serif; background: #f5f0e8; }
#map { position: absolute; top: 0; bottom: 0; width: 100%; }
.title-bar {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%); z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 12px 28px;
  text-align: center; white-space: nowrap;
}
.title-bar h1 { font-size: 18px; color: #3a2a18; margin: 0; }
.title-bar p { font-size: 11px; color: #988b7a; margin: 2px 0 0; }
.legend-panel {
  position: absolute; bottom: 30px; left: 16px; z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 14px 18px;
  font-size: 12px; line-height: 2.0;
}
.legend-item { display: flex; align-items: center; }
.legend-icon { margin-right: 8px; width: 20px; display: flex; align-items: center; justify-content: center; }
.layer-toggle {
  position: absolute; top: 130px; left: 16px; z-index: 1000;
  background: rgba(255,255,255,0.94); border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15); padding: 10px 14px;
  font-size: 12px;
}
.layer-toggle label { display: block; margin: 2px 0; cursor: pointer; }
.footer-info {
  position: absolute; bottom: 10px; right: 16px; z-index: 1000;
  font-size: 10px; color: #988b7a;
  background: rgba(255,255,255,0.85); padding: 3px 10px; border-radius: 4px;
}
</style>
</head>
<body>

<div id="map"></div>

<div class="title-bar">
  <h1>赣州市典型矿区案例分布（第二章）</h1>
  <p>14个典型矿区 · 覆盖钨矿/非金属露天矿/稀土三种开采扰动梯度</p>
</div>

<div class="layer-toggle">
  <strong>图层控制</strong>
  <label><input type="checkbox" id="tW" checked onchange="toggle('钨矿')"> 钨矿（井下）</label>
  <label><input type="checkbox" id="tNM" checked onchange="toggle('非金属露天矿')"> 非金属露天矿</label>
  <label><input type="checkbox" id="tR1" checked onchange="toggle('稀土池浸/堆浸')"> 稀土池浸/堆浸</label>
  <label><input type="checkbox" id="tR2" checked onchange="toggle('传统原地浸矿')"> 传统原地浸矿</label>
  <label><input type="checkbox" id="tR3" checked onchange="toggle('无铵绿色稀土')"> 无铵绿色稀土</label>
  <hr style="margin:4px 0;border-color:#e0d8c8;">
  <label><input type="checkbox" id="tC" checked onchange="toggleCounty()"> 县级边界</label>
</div>

<div class="legend-panel" id="legendPanel"></div>

<div class="footer-info">
  数据来源: 全国矿产地分布数据 (2025) · 坐标系: CGCS2000
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map("map").setView([25.35, 115.15], 10);

L.tileLayer("https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", {
  attribution: '&copy; 高德地图',
  subdomains: "1234",
  maxZoom: 18
}).addTo(map);

// ── 县级边界 ──────────────────────────────────────
var COUNTY = '''
html += COUNTY_GJ
html += r''';
var countyLayer = L.geoJSON(COUNTY, {
  style: { color: "#8c7c6a", weight: 1.2, fill: false, dashArray: "6 3" },
  onEachFeature: function(f,l) { l.bindPopup(f.properties.name); }
}).addTo(map);

// ── SVG 符号工厂 ──────────────────────────────────
function makeIconSVG(shape, color, sz) {
  var s = sz, h = sz / 2;
  var svg;
  if (shape === "circle") {
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+s+'" height="'+s+'" viewBox="0 0 '+s+' '+s+'"><circle cx="'+h+'" cy="'+h+'" r="'+(h-1.5)+'" fill="'+color+'" stroke="white" stroke-width="1.5"/></svg>';
  } else if (shape === "square") {
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+s+'" height="'+s+'" viewBox="0 0 '+s+' '+s+'"><rect x="1.5" y="1.5" width="'+(s-3)+'" height="'+(s-3)+'" fill="'+color+'" stroke="white" stroke-width="1.5"/></svg>';
  } else {
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+s+'" height="'+s+'" viewBox="0 0 '+s+' '+s+'"><polygon points="'+h+',1.5 '+(s-1.5)+','+(s-1.5)+' 1.5,'+(s-1.5)+'" fill="'+color+'" stroke="white" stroke-width="1.5"/></svg>';
  }
  return L.divIcon({ html: svg, className: "", iconSize: [s, s], iconAnchor: [h, h], popupAnchor: [0, -h] });
}

// ── 符号配置 ──────────────────────────────────────
var SYMBOLS = '''
html += SYMBOLS_JS
html += r''';

// ── 生成图例 ──────────────────────────────────────
var legendHTML = "<strong>图例</strong>";
Object.values(SYMBOLS).forEach(function(cfg) {
  legendHTML += '<div class="legend-item"><span class="legend-icon">';
  if (cfg.shape === "circle") {
    legendHTML += '<svg width="14" height="14"><circle cx="7" cy="7" r="5.5" fill="'+cfg.color+'" stroke="white" stroke-width="1"/></svg>';
  } else if (cfg.shape === "square") {
    legendHTML += '<svg width="14" height="14"><rect x="1.5" y="1.5" width="11" height="11" fill="'+cfg.color+'" stroke="white" stroke-width="1"/></svg>';
  } else {
    legendHTML += '<svg width="16" height="14"><polygon points="8,1 15,13 1,13" fill="'+cfg.color+'" stroke="white" stroke-width="1"/></svg>';
  }
  legendHTML += '</span>'+cfg.label+'</div>';
});
document.getElementById("legendPanel").innerHTML = legendHTML;

// ── 加载案例点 ────────────────────────────────────
var casesData = '''
html += CASES_GJ
html += r''';

var catLayers = {};
// 按分类分组
casesData.features.forEach(function(f) {
  var cat = f.properties.category;
  if (!catLayers[cat]) catLayers[cat] = [];
  catLayers[cat].push(f);
});

var leafletLayers = {};
Object.entries(catLayers).forEach(function(e) {
  var cat = e[0], feats = e[1];
  var symKey = feats[0].properties.symbol;
  var cfg = SYMBOLS[symKey];
  var fc = { type: "FeatureCollection", features: feats };

  leafletLayers[cat] = L.geoJSON(fc, {
    pointToLayer: function(feature, latlng) {
      return L.marker(latlng, {
        icon: makeIconSVG(cfg.shape, cfg.color, cfg.size),
        interactive: true
      });
    },
    onEachFeature: function(feature, layer) {
      var p = feature.properties;
      layer.bindPopup(
        "<b>" + p.name + "</b><br>" +
        "县域: " + p.county + "<br>" +
        "开采: " + p.method + "<br>" +
        "特征: " + p.desc + "<br>" +
        "分类: " + p.category
      );
    }
  }).addTo(map);
});

// ── 图层切换 ──────────────────────────────────────
var catIds = { "钨矿":"tW", "非金属露天矿":"tNM", "稀土池浸/堆浸":"tR1", "传统原地浸矿":"tR2", "无铵绿色稀土":"tR3" };

function toggle(cat) {
  var cb = document.getElementById(catIds[cat]);
  if (cb.checked) { leafletLayers[cat].addTo(map); }
  else { map.removeLayer(leafletLayers[cat]); }
}

function toggleCounty() {
  var cb = document.getElementById("tC");
  if (cb.checked) countyLayer.addTo(map);
  else map.removeLayer(countyLayer);
}
</script>
</body>
</html>
'''

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(OUT_HTML) / 1024
print(f"  -> {OUT_HTML} ({size_kb:.1f} KB)")
print("完毕!")
