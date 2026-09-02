# -*- coding: utf-8 -*-
"""UI9: 矿点光标贴地 + 弹窗导航时消失。
问题①: point 图形与光柱 entity 共用 position(base+h/2≈base+1200) → 悬空。
         改为独立贴地 entity(markerEnts, base+6, 穿透可见)。
问题②: 弹窗 #popup 导航/点空白时不消失 → 新增 hidePopup, 在 flyToProc/camera.moveStart/点空白时调用。
大文件用字面量精确替换, 每处断言恰好替换 1 次。"""
import io

F = "赣南矿脉_数字孪生大屏.html"
raw = open(F, encoding="utf-8").read()
orig = raw

def rep(old, new, raw, label):
    c = raw.count(old)
    if c != 1:
        raise SystemExit("[FAIL] %s 匹配次数=%d (期望1)" % (label, c))
    return raw.replace(old, new, 1)

# ---- A. 声明 markerEnts ----
raw = rep(
    "var pointEnts = [], elevEnts = [], labelEnts = [];",
    "var pointEnts = [], elevEnts = [], labelEnts = [], markerEnts = [];",
    raw, "declare-marker")

# ---- B. 光柱 entity 去掉 point 属性 ----
raw = rep(
    ("      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + h / 2 - SINK),\n"
     "      cylinder: {\n"
     "        length: h, topRadius: 0, bottomRadius: st.r,\n"
     "        material: col.withAlpha(st.a), outline: true,\n"
     "        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.85),\n"
     "        outlineWidth: 2\n"
     "      },\n"
     "      point: {\n"
     "        pixelSize: 11,\n"
     "        color: col.withAlpha(0.95),\n"
     "        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.9),\n"
     "        outlineWidth: 2,\n"
     "        scaleByDistance: new Cesium.NearFarScalar(5000, 1.7, 900000, 0.55),\n"
     "        translucencyByDistance: new Cesium.NearFarScalar(1200000, 1.0, 2400000, 0.25)\n"
     "      }\n"
     "    });"),
    ("      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + h / 2 - SINK),\n"
     "      cylinder: {\n"
     "        length: h, topRadius: 0, bottomRadius: st.r,\n"
     "        material: col.withAlpha(st.a), outline: true,\n"
     "        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.85),\n"
     "        outlineWidth: 2\n"
     "      }\n"
     "    });"),
    raw, "strip-point")

# ---- C. label 高度 base+200 -> base+30, 并新增独立贴地点标 ----
raw = rep(
    ("      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + 200),\n"
     "      label: {"),
    ("      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + 30),\n"
     "      label: {"),
    raw, "label-lower")

raw = rep(
    ("    lb._lon = p.lon; lb._lat = p.lat; lb._h = 200;\n"
     "    labelEnts.push(lb);\n"),
    ("    lb._lon = p.lon; lb._lat = p.lat; lb._h = 30;\n"
     "    labelEnts.push(lb);\n"
     "\n"
     "    // 屏幕空间点标：独立贴地 entity, 避免悬在光柱中部; 穿透遮挡保证全览可见\n"
     "    var pe = viewer.entities.add({\n"
     "      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + 6),\n"
     "      point: {\n"
     "        pixelSize: 11,\n"
     "        color: col.withAlpha(0.95),\n"
     "        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.9),\n"
     "        outlineWidth: 2,\n"
     "        scaleByDistance: new Cesium.NearFarScalar(5000, 1.7, 900000, 0.55),\n"
     "        translucencyByDistance: new Cesium.NearFarScalar(1200000, 1.0, 2400000, 0.25),\n"
     "        disableDepthTestDistance: Number.POSITIVE_INFINITY\n"
     "      }\n"
     "    });\n"
     "    pe._idx = i; pe._lon = p.lon; pe._lat = p.lat; pe._cat = p.dom; pe._h = 6;\n"
     "    markerEnts.push(pe);\n"),
    raw, "add-marker")

# ---- D. applyLayerVis: points 分支同步控制 markerEnts ----
raw = rep(
    ("  for (i = 0; i < pointEnts.length; i++) pointEnts[i].show = LAYER.points && activeCats[pointEnts[i]._cat] !== false;\n"
     "  for (i = 0; i < labelEnts.length; i++) labelEnts[i].show = LAYER.labels;\n"),
    ("  for (i = 0; i < pointEnts.length; i++) pointEnts[i].show = LAYER.points && activeCats[pointEnts[i]._cat] !== false;\n"
     "  for (i = 0; i < markerEnts.length; i++) markerEnts[i].show = LAYER.points && activeCats[markerEnts[i]._cat] !== false;\n"
     "  for (i = 0; i < labelEnts.length; i++) labelEnts[i].show = LAYER.labels;\n"),
    raw, "vis-marker")

# ---- E. 新增 hidePopup 函数 (放在 PROC_LL 之前) ----
raw = rep(
    "// 四代工艺代表性稀土矿区坐标（取自真实稀土矿点：龙南/寻乌/安远/兴国）",
    ("function hidePopup(){ var pp = $('popup'); if (pp) pp.classList.remove('show'); }\n"
     "\n"
     "// 四代工艺代表性稀土矿区坐标（取自真实稀土矿点：龙南/寻乌/安远/兴国）"),
    raw, "add-hidepopup")

# ---- F. flyToProc 开头隐藏 popup ----
raw = rep(
    ("function flyToProc(p){\n"
     "  var ll = PROC_LL[p.g];\n"),
    ("function flyToProc(p){\n"
     "  hidePopup();\n"
     "  var ll = PROC_LL[p.g];\n"),
    raw, "flyto-hide")

# ---- G. click handler: 点空白处收起 popup ----
raw = rep(
    ("    var cart = viewer.camera.pickEllipsoid(click.position, sc.globe.ellipsoid);\n"
     "    if (cart){\n"
     "      var cg = Cesium.Cartographic.fromCartesian(cart);\n"
     "      checkCountyClick(Cesium.Math.toDegrees(cg.longitude), Cesium.Math.toDegrees(cg.latitude));\n"
     "    }\n"),
    ("    hidePopup();   // 点空白处收起矿点/工艺窗格\n"
     "    var cart = viewer.camera.pickEllipsoid(click.position, sc.globe.ellipsoid);\n"
     "    if (cart){\n"
     "      var cg = Cesium.Cartographic.fromCartesian(cart);\n"
     "      checkCountyClick(Cesium.Math.toDegrees(cg.longitude), Cesium.Math.toDegrees(cg.latitude));\n"
     "    }\n"),
    raw, "click-hide")

# ---- H. camera.moveStart 收起 popup (bindUI keydown 之后) ----
raw = rep(
    ("  window.addEventListener('keydown', function(e){\n"
     "    if (e.key === 'h' || e.key === 'H'){\n"
     "      $('leftPanel').classList.toggle('hidden');\n"
     "      $('rightPanel').classList.toggle('hidden');\n"
     "    }\n"
     "  });\n"),
    ("  window.addEventListener('keydown', function(e){\n"
     "    if (e.key === 'h' || e.key === 'H'){\n"
     "      $('leftPanel').classList.toggle('hidden');\n"
     "      $('rightPanel').classList.toggle('hidden');\n"
     "    }\n"
     "  });\n"
     "\n"
     "  // 相机开始飞行即收起弹窗, 避免导航后窗格残留\n"
     "  viewer.camera.moveStart.addEventListener(function(){ hidePopup(); });\n"),
    raw, "move-hide")

assert raw != orig, "没有任何改动？"
open(F, "w", encoding="utf-8").write(raw)
print("UI9 替换完成，文件大小 %d -> %d 字节" % (len(orig.encode('utf-8')), len(raw.encode('utf-8'))))
