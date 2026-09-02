# 给矿点光柱加一个屏幕空间点标，解决全览/中景看不见矿点的问题
import io

PATH = r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html"
raw = io.open(PATH, encoding="utf-8").read()

old = '''    var e = viewer.entities.add({
      id: 'pt' + i,
      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + h / 2 - SINK),
      cylinder: {
        length: h, topRadius: 0, bottomRadius: st.r,
        material: col.withAlpha(st.a), outline: false
      }
    });'''

new = '''    var e = viewer.entities.add({
      id: 'pt' + i,
      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + h / 2 - SINK),
      cylinder: {
        length: h, topRadius: 0, bottomRadius: st.r,
        material: col.withAlpha(st.a), outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.85),
        outlineWidth: 2
      },
      point: {
        pixelSize: 11,
        color: col.withAlpha(0.95),
        outlineColor: Cesium.Color.fromCssColorString('#ffe6bc').withAlpha(0.9),
        outlineWidth: 2,
        scaleByDistance: new Cesium.NearFarScalar(5000, 1.7, 900000, 0.55),
        translucencyByDistance: new Cesium.NearFarScalar(1200000, 1.0, 2400000, 0.25)
      }
    });'''

if raw.count(old) != 1:
    raise SystemExit(f"命中 {raw.count(old)} 次，期望值 1")
raw = raw.replace(old, new)

io.open(PATH, "w", encoding="utf-8").write(raw)
print("OK")
