#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性应用本轮 UI 调整：
1) 删 "案例矿区" 那一列（左侧开关 + 右侧"典型矿区案例"区块 + cases 实体/逻辑）
2) 把 swHotspot（矿点冷热点 Gi*）从"显示图层"组移到"空间分析图层"组
3) 隐藏不明显的空间分析图层：voronoi / nn / gistar_point / bycat
"""
from pathlib import Path
p = Path(r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html")
s = p.read_text(encoding="utf-8")
orig = s

def must_replace(needle, replacement, label):
    global s
    if needle not in s:
        raise SystemExit(f"[未找到] {label}\n>>>  {needle[:140]}")
    if s.count(needle) != 1:
        raise SystemExit(f"[多处] {label} 出现 {s.count(needle)} 次，请人工处理")
    s = s.replace(needle, replacement, 1)
    print(f"[OK] {label}")

# 1) 删 "案例矿区" 开关
must_replace(
    '    <div class="sw-row"><span>案例矿区</span><div class="sw on" id="swCases"></div></div>\n',
    '',
    "删 swCases 开关"
)

# 2) 删 swHotspot 行（原"显示图层"组内）
must_replace(
    '    <div class="sw-row"><span>矿点冷热点 (Gi*)</span><div class="sw on" id="swHotspot"></div></div>\n',
    '',
    "删 swHotspot 行（显示图层组）"
)

# 3) 把 swHotspot 插到"空间分析图层"组 alNote 上方
old_alnote = '    <div class="hot-note" id="alNote">点击叠加到地形；默认仅显示核密度。</div>\n'
new_alnote = (
    '    <div class="sw-row"><span>矿点冷热点 (Gi*)</span><div class="sw on" id="swHotspot"></div></div>\n'
    '    <div class="hot-note" id="alNote">点击叠加到地形；默认仅显示核密度；冷热点按县域上色。</div>\n'
)
must_replace(old_alnote, new_alnote, "swHotspot 移到空间分析图层组 + alNote 文案")

# 4) 删右侧"典型矿区案例"区块
must_replace(
    '  <div class="sec">\n'
    '    <div class="sec-t">典型矿区案例</div>\n'
    '    <div id="caseList"></div>\n'
    '  </div>\n',
    '',
    "删右侧'典型矿区案例'区块"
)

# 5) 变量声明删 caseEnts
must_replace(
    'var pointEnts = [], caseEnts = [], elevEnts = [], labelEnts = [];\n',
    'var pointEnts = [], elevEnts = [], labelEnts = [];\n',
    "变量声明删 caseEnts"
)

# 6) 删 addCases() 函数（line 1044-1090 整段）
addcases_block = (
    'function addCases(){\n'
    '  var cases = D.cases || [];\n'
    '  caseEnts = [];\n'
    '  for (var i = 0; i < cases.length; i++){\n'
    '    var c = cases[i];\n'
    '    var col = Cesium.Color.fromCssColorString(CAT_COLORS[c.cat] || CAT_COLORS.other);\n'
    '    var h = c.gen ? (6000 + c.gen * 2200) : 9000;\n'
    '    var base = surfaceH(c.lon, c.lat, 0);\n'
    '    var e = viewer.entities.add({\n'
    "      id: 'case' + i,\n"
    '      position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, base + h / 2),\n'
    '      cylinder: {\n'
    '        length: h, topRadius: 0, bottomRadius: 480,\n'
    '        material: col.withAlpha(0.82), outline: false\n'
    '      }\n'
    '    });\n'
    '    e._lon = c.lon; e._lat = c.lat; e._h = h / 2; e._caseIdx = i; e._useLift = true;\n'
    '    caseEnts.push(e);\n'
    '    elevEnts.push(e);\n'
    '\n'
    '    var lb = viewer.entities.add({\n'
    "      position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, base + h + 600),\n"
    '      label: {\n'
    "        text: c.name, font: '600 13px \"Noto Serif SC\"',\n"
    "        fillColor: Cesium.Color.fromCssColorString('#ffe6bc'),\n"
    '        showBackground: true,\n'
    "        backgroundColor: Cesium.Color.fromCssColorString('rgba(8,12,20,.72)'),\n"
    '        backgroundPadding: new Cesium.Cartesian2(6, 3),\n'
    '        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,\n'
    '        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 260000),\n'
    '        scaleByDistance: new Cesium.NearFarScalar(30000, 1.0, 260000, 0.62)\n'
    '      }\n'
    '    });\n'
    '    lb._lon = c.lon; lb._lat = c.lat; lb._h = h + 600; lb._useLift = true;\n'
    '    elevEnts.push(lb); labelEnts.push(lb);\n'
    '\n'
    '    var dot = viewer.entities.add({\n'
    "      position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, base + 120),\n"
    '      point: {\n'
    '        pixelSize: 9, color: col, outlineColor: Cesium.Color.WHITE, outlineWidth: 2,\n'
    '        disableDepthTestDistance: Number.POSITIVE_INFINITY\n'
    '      }\n'
    '    });\n'
    '    dot._lon = c.lon; dot._lat = c.lat; dot._h = 120; dot._useLift = true;\n'
    '    elevEnts.push(dot);\n'
    '  }\n'
    '}\n'
    '\n'
)
must_replace(addcases_block, '', "删 addCases() 函数体")

# 7) 删 addCases() 调用
must_replace(
    '  addCases();\n  addCountyLabels();\n',
    '  addCountyLabels();\n',
    "删 addCases() 调用"
)

# 8) 删 buildCaseList() 调用
must_replace(
    '  buildCaseList();\n  buildGenList();\n',
    '  buildGenList();\n',
    "删 buildCaseList() 调用"
)

# 9) LAYER 删 cases
must_replace(
    "var LAYER = { county: false, points: true, cases: true, labels: true,\n              contour: true, hotspot: true, pin: true };\n",
    "var LAYER = { county: false, points: true, labels: true,\n              contour: true, hotspot: true, pin: true };\n",
    "LAYER 删 cases"
)

# 10) syncSwitches 删 swCases 行
must_replace(
    "  $('swCases').classList.toggle('on', LAYER.cases);\n",
    '',
    "syncSwitches 删 swCases"
)

# 11) applyLayerVis 删 caseEnts 行
must_replace(
    "  for (i = 0; i < caseEnts.length; i++) caseEnts[i].show = LAYER.cases;\n",
    '',
    "applyLayerVis 删 caseEnts 行"
)

# 12) sw() 绑定删 swCases
must_replace(
    "  sw('swPoints', 'points');   sw('swCases', 'cases');\n",
    "  sw('swPoints', 'points');\n",
    "sw() 绑定删 swCases"
)

# 13) gotoChapter 删 LAYER.cases 行
must_replace(
    "  LAYER.cases  = !!c.vis.cases;\n",
    '',
    "gotoChapter 删 LAYER.cases"
)

# 14) 6 个章节里 vis.cases 字段删除
for old in [
    "    vis: { points: 1, cases: 0, county: 0 }\n",
    "    vis: { points: 1, cases: 0, county: 1 }\n",
    "    vis: { points: 1, cases: 1, county: 1 }\n",
]:
    new = old.replace(", cases: 0", "").replace(", cases: 1", "")
    cnt = s.count(old)
    if cnt == 0:
        raise SystemExit(f"[未找到] 章节 vis 字段: {old.strip()}")
    s = s.replace(old, new)
    print(f"[OK] 章节 vis 字段替换 {cnt} 处: {old.strip()} -> {new.strip()}")

# 15) 隐藏 4 个不明显图层（过滤 AL_KEYS）
must_replace(
    "  var AL_KEYS = (window.AL_META) ? Object.keys(window.AL_META) : [];\n",
    "  // 隐藏效果不明显的图层（最近邻 / 泰森 / Gi*矿点 / 按矿种大类）——\n"
    "  // 它们的色块或单点会被矿点光柱完全遮住，留着只会让面板臃肿\n"
    "  var AL_HIDDEN = { voronoi: 1, nn: 1, gistar_point: 1, bycat: 1 };\n"
    "  var AL_KEYS = (window.AL_META)\n"
    "    ? Object.keys(window.AL_META).filter(function(k){ return !AL_HIDDEN[k]; })\n"
    "    : [];\n",
    "过滤 AL_KEYS 隐藏不明显图层"
)

# 16) 默认关闭 swHotspot 关闭态？保持开启；只需确保其他不明显的不会默认开。
# 默认 alShow('density') 不变。

# 17) 更新 alNote 文案已合并到修改 3

p.write_text(s, encoding="utf-8")
print(f"\n[完成] 文件已写入，原 {len(orig):,} 字符 -> 现 {len(s):,} 字符")
