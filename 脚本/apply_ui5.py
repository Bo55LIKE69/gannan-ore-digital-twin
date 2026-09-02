# -*- coding: utf-8 -*-
"""UI5 修正：DEM 多配色方案（替换被误解的分析图层配色），并移除 NDVI 与地表锚点（穿透遮挡）。"""
import io, re, sys

PATH = r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html"
raw = io.open(PATH, "r", encoding="utf-8").read()

reps = []  # (kind, old, new, n)

def R(old, new, n=1):
    reps.append(("str", old, new, n))

def Rg(old, new, n=1):
    reps.append(("re", old, new, n))

# ---------- 1. 移除 NDVI 脚本引用 ----------
R('  <script src="ndvi_data.js"></script>\n', "")

# ---------- 2. 地形区：新增 DEM 配色下拉（palSel 移到这里） ----------
R('    <div class="ramp"></div>',
'''    <div class="ctl">
      <div class="ctl-h"><span>地形配色</span></div>
      <select id="palSel" class="pal-sel">
        <option value="terrain">地形（棕黄）</option>
        <option value="elev">高程彩虹</option>
        <option value="gray">灰度</option>
        <option value="green">植被绿阶</option>
      </select>
    </div>
    <div class="ramp"></div>''')

# ---------- 3. 分析区：移除原配色方案下拉（已挪到地形区） ----------
R('''    <div class="sw-row pal-row"><span>配色方案</span>
      <select id="palSel" class="pal-sel">
        <option value="blue-red">蓝—黄—红</option>
        <option value="green">红—黄—绿（植被）</option>
        <option value="thermal">墨—紫—橙—黄</option>
        <option value="ice">白—青—蓝</option>
      </select>
    </div>
''', "")

# ---------- 4. 移除地表锚点 UI 行 ----------
R('''    <div class="sw-row"><span>地表锚点（穿透遮挡）</span><div class="sw on" id="swPin"></div></div>
    <div class="note">锚点始终贴在 DEM 表面并关闭深度测试，山体挡不住；抬升滑杆只抬光柱，锚点留地并以引线相连。</div>
''', "")

# ---------- 5. 移除 pinEnts/tetherEnts 声明 ----------
R("var pinEnts = [], tetherEnts = [];   // 地表锚点 / 锚点引线\n", "")

# ---------- 6. addPoints 内移除 pin + tether 创建块 ----------
R('''    // 地表锚点：关闭深度测试，永远压在地形之上，任何视角都可见 —— 即每个矿区的标识
    var pin = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base + 60),
      point: {
        pixelSize: 8,
        color: col.withAlpha(0.98),
        outlineColor: Cesium.Color.fromCssColorString('#070a11').withAlpha(0.9),
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 750000)
      }
    });
    pin._cat = p.dom; pin._lon = p.lon; pin._lat = p.lat; pin._h = 60;
    pin._idx = i; pin._pin = true; pin._useLift = false;
    pinEnts.push(pin);
    elevEnts.push(pin);

    // 锚点引线：抬升滑杆拉起光柱后，用它把光柱和地表锚点连起来
    var th = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base),
      polyline: {
        positions: [
          Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base),
          Cesium.Cartesian3.fromDegrees(p.lon, p.lat, base)
        ],
        width: 1.1,
        material: col.withAlpha(0.42),
        show: false
      }
    });
    th._cat = p.dom; th._lon = p.lon; th._lat = p.lat; th._tether = true;
    tetherEnts.push(th);
''', "")

# ---------- 7. applyLift：改注释 + 移除引线循环 ----------
R("/* 矿点贴地：光柱/标签按 LIFT 抬升，锚点始终留在 DEM 表面，引线连接两者 */",
  "/* 矿点贴地：光柱/标签按 LIFT 抬升 */")
R('''  for (i = 0; i < tetherEnts.length; i++){
    e = tetherEnts[i];
    var g = surfaceH(e._lon, e._lat, 0);
    e.polyline.positions = [
      Cesium.Cartesian3.fromDegrees(e._lon, e._lat, g),
      Cesium.Cartesian3.fromDegrees(e._lon, e._lat, g + LIFT)
    ];
    e.show = LIFT > 1 && LAYER.points && LAYER.pin;
  }
''', "")

# ---------- 8. LAYER 去掉 pin ----------
R('''var LAYER = { county: false, points: true, labels: true,
              contour: true, hotspot: true, pin: true };''',
'''var LAYER = { county: false, points: true, labels: true,
              contour: true, hotspot: true };''')

# ---------- 9. syncSwitches 去掉 swPin ----------
R("  $('swPin').classList.toggle('on', LAYER.pin);\n", "")

# ---------- 10. applyLayerVis 去掉 pin/tether 循环 ----------
R('''  for (i = 0; i < pinEnts.length; i++) pinEnts[i].show = LAYER.pin && LAYER.points && activeCats[pinEnts[i]._cat] !== false;
  for (i = 0; i < tetherEnts.length; i++) tetherEnts[i].show = LAYER.pin && LAYER.points && LIFT > 1 && activeCats[tetherEnts[i]._cat] !== false;
''', "")

# ---------- 11. bindUI 去掉 sw('swPin') ----------
R("  sw('swPin', 'pin');\n", "")

# ---------- 12. bindUI 配色下拉改控 DEM ----------
R('''  // 配色方案切换：重建所有已开分析层 + 同步图例
  var ps = document.getElementById('palSel');
  if (ps) ps.addEventListener('change', function(){
    curPal = ps.value;
    rebuildAlLayers();
    for (var k in alOn){ if (alOn[k]){ buildAlLegend(k, true); break; } }
  });''',
'''  // 地形配色切换：改 DEM 着色器 palette uniform + 同步图例色带
  var ps = document.getElementById('palSel');
  if (ps) ps.addEventListener('change', function(){
    DEM_PAL = ps.value;
    if (terrainUniforms) terrainUniforms.u_demPal = DEM_PAL_IDX[DEM_PAL];
    buildDemLegend();
  });''')

# ---------- 13. startApp 去掉 NDVI 注册 ----------
R('''  // NDVI 栅格图层注册（Sentinel-2 L2A 反演，最大值合成 MVC）
  if (window.NDVI_DATA){
    window.AL_META.ndvi = { name:'植被指数 NDVI', kind:'grid', colorBy:'ndvi', ramp:'seq', label:'NDVI' };
    window.AL.ndvi = window.NDVI_DATA;
  }
''', "")

# ---------- 14. 移除 buildAlGrid 函数（正则定位到下一个函数） ----------
Rg(r"/\* NDVI 栅格：.*?\n\}\n\nfunction buildAlLayer",
   "\n\nfunction buildAlLayer", 1)

# ---------- 15. buildAlLayer 去掉 grid 分支 ----------
R('''  var obj = (meta.kind === 'poly') ? buildAlPoly(key, gj, meta)
          : (meta.kind === 'grid') ? buildAlGrid(key, meta)
          : buildAlPoint(key, gj, meta);''',
'''  var obj = (meta.kind === 'poly') ? buildAlPoly(key, gj, meta)
          : buildAlPoint(key, gj, meta);''')

# ---------- 16. TERRAIN_FS uniform 增加 u_demPal ----------
R("  'uniform float u_hmin, u_hmax, u_hs, u_contour, u_px, u_alpha;',",
  "  'uniform float u_hmin, u_hmax, u_hs, u_contour, u_px, u_alpha, u_demPal;',")

# ---------- 17. ramp 函数改为多套 ----------
R('''  'vec3 ramp(float t) {',
  '    vec3 c0 = vec3(0.122, 0.059, 0.043);',
  '    vec3 c1 = vec3(0.227, 0.116, 0.069);',
  '    vec3 c2 = vec3(0.384, 0.213, 0.117);',
  '    vec3 c3 = vec3(0.557, 0.354, 0.176);',
  '    vec3 c4 = vec3(0.725, 0.545, 0.318);',
  '    vec3 c5 = vec3(0.855, 0.702, 0.470);',
  '    vec3 c6 = vec3(0.953, 0.902, 0.775);',
  '    vec3 c = mix(c0, c1, smoothstep(0.00, 0.16, t));',
  '    c = mix(c, c2, smoothstep(0.16, 0.34, t));',
  '    c = mix(c, c3, smoothstep(0.34, 0.54, t));',
  '    c = mix(c, c4, smoothstep(0.54, 0.72, t));',
  '    c = mix(c, c5, smoothstep(0.72, 0.87, t));',
  '    c = mix(c, c6, smoothstep(0.87, 1.00, t));',
  '    return c;',
  '}',
''',
'''  'vec3 rampTerrain(float t) {',
  '    vec3 c0 = vec3(0.122, 0.059, 0.043);',
  '    vec3 c1 = vec3(0.227, 0.116, 0.069);',
  '    vec3 c2 = vec3(0.384, 0.213, 0.117);',
  '    vec3 c3 = vec3(0.557, 0.354, 0.176);',
  '    vec3 c4 = vec3(0.725, 0.545, 0.318);',
  '    vec3 c5 = vec3(0.855, 0.702, 0.470);',
  '    vec3 c6 = vec3(0.953, 0.902, 0.775);',
  '    vec3 c = mix(c0, c1, smoothstep(0.00, 0.16, t));',
  '    c = mix(c, c2, smoothstep(0.16, 0.34, t));',
  '    c = mix(c, c3, smoothstep(0.34, 0.54, t));',
  '    c = mix(c, c4, smoothstep(0.54, 0.72, t));',
  '    c = mix(c, c5, smoothstep(0.72, 0.87, t));',
  '    c = mix(c, c6, smoothstep(0.87, 1.00, t));',
  '    return c;',
  '}',
  'vec3 rampElev(float t) {',
  '    vec3 c0 = vec3(0.10, 0.20, 0.55);',
  '    vec3 c1 = vec3(0.00, 0.55, 0.75);',
  '    vec3 c2 = vec3(0.15, 0.70, 0.35);',
  '    vec3 c3 = vec3(0.95, 0.85, 0.20);',
  '    vec3 c4 = vec3(0.90, 0.30, 0.18);',
  '    vec3 c = mix(c0, c1, smoothstep(0.00, 0.25, t));',
  '    c = mix(c, c2, smoothstep(0.25, 0.50, t));',
  '    c = mix(c, c3, smoothstep(0.50, 0.72, t));',
  '    c = mix(c, c4, smoothstep(0.72, 1.00, t));',
  '    return c;',
  '}',
  'vec3 rampGray(float t) {',
  '    vec3 c0 = vec3(0.13, 0.13, 0.15);',
  '    vec3 c1 = vec3(0.55, 0.55, 0.58);',
  '    vec3 c2 = vec3(0.93, 0.93, 0.95);',
  '    vec3 c = mix(c0, c1, smoothstep(0.00, 0.50, t));',
  '    c = mix(c, c2, smoothstep(0.50, 1.00, t));',
  '    return c;',
  '}',
  'vec3 rampGreen(float t) {',
  '    vec3 c0 = vec3(0.10, 0.22, 0.12);',
  '    vec3 c1 = vec3(0.30, 0.55, 0.22);',
  '    vec3 c2 = vec3(0.70, 0.80, 0.30);',
  '    vec3 c3 = vec3(0.78, 0.66, 0.40);',
  '    vec3 c = mix(c0, c1, smoothstep(0.00, 0.40, t));',
  '    c = mix(c, c2, smoothstep(0.40, 0.70, t));',
  '    c = mix(c, c3, smoothstep(0.70, 1.00, t));',
  '    return c;',
  '}',
''')

# ---------- 18. main 内改用多套 ramp ----------
R("  '    vec3 col = ramp(t);',",
'''  '    vec3 col;',
  '    if (u_demPal < 0.5) col = rampTerrain(t);',
  '    else if (u_demPal < 1.5) col = rampElev(t);',
  '    else if (u_demPal < 2.5) col = rampGray(t);',
  '    else col = rampGreen(t);',
''')

# ---------- 19. terrainUniforms 增加 u_demPal ----------
R("    u_alpha: 1.0,",
  "    u_alpha: 1.0,\n    u_demPal: 0.0,")

# ---------- 20. 插入 DEM_PALS / buildDemLegend（在 buildLegend 前） ----------
R("function buildLegend(){",
'''// DEM 地形配色方案（多套，客户端可切换）；与着色器 u_demPal 一一对应
var DEM_PAL = 'terrain';
var DEM_PAL_IDX = { terrain: 0.0, elev: 1.0, gray: 2.0, green: 3.0 };
var DEM_PALS = {
  terrain: { stops:['rgb(31,15,11)','rgb(58,30,18)','rgb(98,54,30)','rgb(142,90,45)','rgb(185,139,81)','rgb(218,179,120)','rgb(243,230,198)'], pos:[0,16,34,54,72,87,100] },
  elev:    { stops:['rgb(26,51,140)','rgb(0,140,191)','rgb(38,179,89)','rgb(242,217,51)','rgb(230,77,46)'], pos:[0,25,50,72,100] },
  gray:    { stops:['rgb(33,33,38)','rgb(140,140,148)','rgb(237,237,242)'], pos:[0,50,100] },
  green:   { stops:['rgb(26,56,31)','rgb(77,140,56)','rgb(179,204,77)','rgb(199,168,102)'], pos:[0,40,70,100] }
};
function buildDemLegend(){
  var el = document.querySelector('.ramp'); if (!el) return;
  var p = DEM_PALS[DEM_PAL] || DEM_PALS.terrain;
  var grad = p.stops.map(function(c, i){ return c + ' ' + p.pos[i] + '%'; }).join(',');
  el.style.background = 'linear-gradient(90deg,' + grad + ')';
  var r0 = document.getElementById('rl0'), r1 = document.getElementById('rl1');
  if (r0 && DM) r0.textContent = (DM.minH | 0) + ' m';
  if (r1 && DM) r1.textContent = (DM.maxH | 0) + ' m';
}

function buildLegend(){''')

# ---------- 21. startApp 加 buildDemLegend() 调用 ----------
R("  addTerrain();\n", "  addTerrain();\n  buildDemLegend();\n")

# ---------- 22. 顺手修正注释里的 NDVI ----------
R("  t = Math.pow(t, 0.5);   // 低值拉伸：让稀疏矿点区 / 低 NDVI 也清晰可见",
  "  t = Math.pow(t, 0.5);   // 低值拉伸：让稀疏矿点区也清晰可见")

# ===== 应用 =====
for kind, old, new, n in reps:
    if kind == "str":
        c = raw.count(old)
        if c != n:
            print("STR FAIL (count=%d, want=%d):\n%r" % (c, n, old[:120]))
            sys.exit(1)
        raw = raw.replace(old, new)
    else:
        raw, newc = re.subn(old, new, raw, flags=re.DOTALL)
        if newc != n:
            print("RE FAIL (count=%d, want=%d):\n%r" % (newc, n, old[:120]))
            sys.exit(1)

io.open(PATH, "w", encoding="utf-8").write(raw)
print("OK: applied", len(reps), "replacements")
