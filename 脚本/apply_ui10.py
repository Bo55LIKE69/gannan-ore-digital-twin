# -*- coding: utf-8 -*-
"""UI10: 矿点真正贴地(复刻地形顶面高度) + 弹窗导航稳定切换"""
import io, sys

P = "E:/Data/赣州稀土/赣南矿脉_数字孪生大屏.html"
raw = io.open(P, encoding="utf-8").read()

def rep(old, new, n=1):
    global raw
    c = raw.count(old)
    if c != n:
        raise SystemExit("ASSERT count=%d (want %d)\n--- old ---\n%s" % (c, n, old[:300]))
    raw = raw.replace(old, new, 1) if n == 1 else raw.replace(old, new)

# ---- 1. 新增 terrainTopH 复刻地形真实顶面高度 (插在 surfCart 之后) ----
rep(
    "function surfCart(lon, lat, extra){\n  return Cesium.Cartesian3.fromDegrees(lon, lat, surfaceH(lon, lat, extra || 0));\n}\n",
    "function surfCart(lon, lat, extra){\n  return Cesium.Cartesian3.fromDegrees(lon, lat, surfaceH(lon, lat, extra || 0));\n}\n"
    "// 地形真实顶面椭球高：几何 height=surfaceH(...,AL_LIFT)，顶点着色器再抬 (H-DM.minH)*(EXAG-1)\n"
    "function terrainTopH(lon, lat){\n"
    "  var H = surfaceH(lon, lat, AL_LIFT);\n"
    "  return H + (H - DM.minH) * (EXAG - 1.0);\n"
    "}\n"
)

# ---- 2. 标签 position: base+30 -> terrainTopH+28 ----
rep(
    "      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + 30),\n",
    "      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, terrainTopH(p.lon, p.lat) + 28),\n"
)
# 标签 _h 偏移由 30 改为 28（与 terrainTopH 偏移一致）
rep(
    "    lb._lon = p.lon; lb._lat = p.lat; lb._h = 30;\n",
    "    lb._lon = p.lon; lb._lat = p.lat; lb._h = 28;\n"
)

# ---- 3. marker 块重写：贴地形顶面 + 移除穿透 ----
rep(
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
    "    markerEnts.push(pe);\n",
    "    // 屏幕空间点标：真正附着在 DEM 顶面(与地形着色器/AL_LIFT 一致)；开启 depth-test 随山体遮挡 = 贴地\n"
    "    var pe = viewer.entities.add({\n"
    "      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, terrainTopH(p.lon, p.lat) + 4),\n"
    "      point: {\n"
    "        pixelSize: 11,\n"
    "        color: col.withAlpha(0.95),\n"
    "        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.9),\n"
    "        outlineWidth: 2,\n"
    "        scaleByDistance: new Cesium.NearFarScalar(5000, 1.7, 900000, 0.55),\n"
    "        translucencyByDistance: new Cesium.NearFarScalar(1200000, 1.0, 2400000, 0.25)\n"
    "      }\n"
    "    });\n"
    "    pe._idx = i; pe._lon = p.lon; pe._lat = p.lat; pe._cat = p.dom; pe._h = 4;\n"
    "    markerEnts.push(pe);\n"
)

# ---- 4. applyLift 扩展：随 EXAG 重算 marker/label 贴地高度 ----
rep(
    "/* 矿点贴地：光柱/标签随垂直夸张按 surfaceH 重算 */\n"
    "function applyLift(){\n"
    "  var i, e, z;\n"
    "  for (i = 0; i < elevEnts.length; i++){\n"
    "    e = elevEnts[i];\n"
    "    z = surfaceH(e._lon, e._lat, e._h);\n"
    "    e.position = Cesium.Cartesian3.fromDegrees(e._lon, e._lat, z);\n"
    "  }\n"
    "}\n",
    "/* 矿点贴地：光柱/标签/点标随垂直夸张与地形顶面重算 */\n"
    "function applyLift(){\n"
    "  var i, e, z;\n"
    "  for (i = 0; i < elevEnts.length; i++){\n"
    "    e = elevEnts[i];\n"
    "    z = surfaceH(e._lon, e._lat, e._h);\n"
    "    e.position = Cesium.Cartesian3.fromDegrees(e._lon, e._lat, z);\n"
    "  }\n"
    "  for (i = 0; i < markerEnts.length; i++){\n"
    "    e = markerEnts[i];\n"
    "    z = terrainTopH(e._lon, e._lat) + (e._h || 4);\n"
    "    e.position = Cesium.Cartesian3.fromDegrees(e._lon, e._lat, z);\n"
    "  }\n"
    "  for (i = 0; i < labelEnts.length; i++){\n"
    "    e = labelEnts[i];\n"
    "    z = terrainTopH(e._lon, e._lat) + (e._h || 28);\n"
    "    e.position = Cesium.Cartesian3.fromDegrees(e._lon, e._lat, z);\n"
    "  }\n"
    "}\n"
)

# ---- 5. flyToProc 改用 complete 回调 + 令牌，避免 setTimeout 竞态 ----
rep(
    "function flyToProc(p){\n"
    "  hidePopup();\n"
    "  var ll = PROC_LL[p.g];\n"
    "  if (!ll) return;\n"
    "  flyTo(ll[0], ll[1], 12000, -30, 0, 2.2);\n"
    "  setTimeout(function(){ showProcPopup(p); }, 1500);\n"
    "}\n",
    "var _procToken = 0;\n"
    "function flyToProc(p){\n"
    "  hidePopup();\n"
    "  var ll = PROC_LL[p.g];\n"
    "  if (!ll) return;\n"
    "  var myTok = ++_procToken;\n"
    "  viewer.camera.flyToBoundingSphere(\n"
    "    new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(ll[0], ll[1], 0), 1),\n"
    "    { duration: 2.2,\n"
    "      offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-30), 12000),\n"
    "      complete: function(){ if (myTok === _procToken) showProcPopup(p); } });\n"
    "}\n"
)

io.open(P, "w", encoding="utf-8").write(raw)
print("OK ui10 applied")
