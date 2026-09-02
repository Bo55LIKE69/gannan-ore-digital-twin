# -*- coding: utf-8 -*-
"""本轮 UI4 改造（精确到唯一片段替换）"""
P = '赣南矿脉_数字孪生大屏.html'
s = open(P, encoding='utf-8').read()

def rep(old, new, desc):
    n = s.count(old)
    assert n == 1, '[%s] 期望唯一匹配，实际 %d 处' % (desc, n)
    globals()['s'] = s.replace(old, new)
    print('OK  ', desc)

# 1) 多套配色方案 + seqRamp 改造
rep("""// 连续配色：冷蓝 -> 黄 -> 红（密度/强度低->高）
function seqRamp(t){
  t = Math.max(0, Math.min(1, t));
  var stops = [[0.0,[59,111,226]],[0.5,[255,210,63]],[1.0,[226,59,59]]];
  var a = (t > 0.5) ? stops[1] : stops[0];
  var b = (t > 0.5) ? stops[2] : stops[1];
  var k = (t > 0.5) ? (t - 0.5) / 0.5 : t / 0.5;
  var c = [0,1,2].map(function(i){ return Math.round(a[1][i] + (b[1][i] - a[1][i]) * k); });
  return Cesium.Color.fromBytes(c[0], c[1], c[2], 255);
}""",
"""// 多套连续配色方案（用户可切换）；分类层（lisa / Gi* 网格）不受影响
window.PALETTES = {
  'blue-red': { label:'蓝—黄—红', stops:[[0.0,[59,111,226]],[0.5,[255,210,63]],[1.0,[226,59,59]]] },
  'green':    { label:'红—黄—绿（植被）', stops:[[0.0,[150,40,40]],[0.5,[240,200,60]],[1.0,[34,139,34]]] },
  'thermal':  { label:'墨—紫—橙—黄', stops:[[0.0,[18,18,38]],[0.4,[120,40,160]],[0.7,[230,90,40]],[1.0,[255,220,90]]] },
  'ice':      { label:'白—青—蓝', stops:[[0.0,[235,245,255]],[0.5,[90,180,210]],[1.0,[20,70,160]]] }
};
var curPal = 'blue-red';
function seqRamp(t){
  t = Math.max(0, Math.min(1, t));
  var stops = (window.PALETTES[curPal] || window.PALETTES['blue-red']).stops;
  var c = [0,0,0];
  for (var si = 0; si < stops.length - 1; si++){
    var a = stops[si], b = stops[si + 1];
    if (t >= a[0] && t <= b[0]){
      var k = (b[0] > a[0]) ? (t - a[0]) / (b[0] - a[0]) : 0;
      c = [0,1,2].map(function(i){ return Math.round(a[1][i] + (b[1][i] - a[1][i]) * k); });
      break;
    }
  }
  return Cesium.Color.fromBytes(c[0], c[1], c[2], 255);
}""",
"PALETTES + seqRamp")

# 2) 核密度/连续层 低值拉伸 + 提高不透明度
rep("""  var v = parseFloat(props[cf]);
  if (!isFinite(v)) return Cesium.Color.fromCssColorString('rgba(204,204,204,0.25)');
  if (v <= 0) return new Cesium.Color(0, 0, 0, 0);   // 密度0 / 无值：透明
  var rg = alRange[cf] || { mn: 0, mx: 1 };
  var t = (rg.mx > rg.mn) ? (v - rg.mn) / (rg.mx - rg.mn) : 0;
  // 低密度更透，高密度才显，避免整层盖住地形
  return seqRamp(t).withAlpha(0.08 + 0.28 * t);""",
"""  var v = parseFloat(props[cf]);
  if (!isFinite(v)) return Cesium.Color.fromCssColorString('rgba(204,204,204,0.25)');
  if (v <= 0) return new Cesium.Color(0, 0, 0, 0);   // 密度0 / 无值：透明
  var rg = alRange[cf] || { mn: 0, mx: 1 };
  var t = (rg.mx > rg.mn) ? (v - rg.mn) / (rg.mx - rg.mn) : 0;
  t = Math.pow(t, 0.5);   // 低值拉伸：让稀疏矿点区 / 低 NDVI 也清晰可见
  return seqRamp(t).withAlpha(0.20 + 0.42 * t);""",
"alColor gamma + alpha")

# 3) 连续图例改用当前配色方案
rep("""  } else {
    var rg = alRange[meta.colorBy] || { mn: 0, mx: 1 };
    el.innerHTML = '<div class="hl" style="width:100%;display:flex;align-items:center">' +
      '<span style="color:#9fb4d8">低</span>' +
      '<i style="flex:1;height:8px;margin:0 6px;border-radius:4px;background:linear-gradient(90deg,rgb(59,111,226),rgb(255,210,63),rgb(226,59,59))"></i>' +
      '<span style="color:#f0a05a">高</span>' +
      '<span style="margin-left:6px;color:#7e8794">(' + rg.mn.toFixed(1) + '–' + rg.mx.toFixed(1) + ')</span></div>';""",
"""  } else {
    var rg = alRange[meta.colorBy] || { mn: 0, mx: 1 };
    var pstops = (window.PALETTES[curPal] || window.PALETTES['blue-red']).stops;
    var grad = pstops.map(function(st){ return 'rgb(' + st[1][0] + ',' + st[1][1] + ',' + st[1][2] + ') ' + Math.round(st[0] * 100) + '%'; }).join(',');
    el.innerHTML = '<div class="hl" style="width:100%;display:flex;align-items:center">' +
      '<span style="color:#9fb4d8">低</span>' +
      '<i style="flex:1;height:8px;margin:0 6px;border-radius:4px;background:linear-gradient(90deg,' + grad + ')"></i>' +
      '<span style="color:#f0a05a">高</span>' +
      '<span style="margin-left:6px;color:#7e8794">(' + rg.mn.toFixed(2) + '–' + rg.mx.toFixed(2) + ')</span></div>';""",
"alLegend 连续分支")

# 4) 县域标注加强（全览常显 + 全部县底衬 + 描边 + 字体加大）
rep("""function addCountyLabels(){
  var counties = D.counties || [];
  for (var i = 0; i < counties.length; i++){
    var c = counties[i];
    var ring = ringOf(c.geometry);
    if (!ring) continue;
    var ctr = geoCenter(ring);
    var sty = HOT_STYLE[c.cls] || HOT_STYLE['不显著'];
    var lb = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(ctr[0], ctr[1], surfaceH(ctr[0], ctr[1], 3200)),
      label: {
        text: c.name + '  ' + c.n,
        font: (c.cls === '热点' ? '600 14px "Noto Serif SC"' : '300 12.5px "Noto Serif SC"'),
        fillColor: Cesium.Color.fromCssColorString(sty.t),
        showBackground: c.cls === '热点',
        backgroundColor: Cesium.Color.fromCssColorString('rgba(28,10,8,.6)'),
        backgroundPadding: new Cesium.Cartesian2(6, 3),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(20000, 420000),
        scaleByDistance: new Cesium.NearFarScalar(60000, 1.0, 420000, 0.7)
      }
    });
    lb._lon = ctr[0]; lb._lat = ctr[1]; lb._h = 3200;
    elevEnts.push(lb); labelEnts.push(lb);
  }
}""",
"""function addCountyLabels(){
  var counties = D.counties || [];
  for (var i = 0; i < counties.length; i++){
    var c = counties[i];
    var ring = ringOf(c.geometry);
    if (!ring) continue;
    var ctr = geoCenter(ring);
    var isHot = (c.cls === '热点');
    var lb = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(ctr[0], ctr[1], surfaceH(ctr[0], ctr[1], 180) + 600),
      label: {
        text: c.name + (c.n ? '  ' + c.n : ''),
        font: (isHot ? '600 15px "Noto Serif SC"' : '500 13px "Noto Serif SC"'),
        fillColor: Cesium.Color.fromCssColorString(isHot ? '#ffd9a0' : '#f3ead6'),
        showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString(isHot ? 'rgba(120,30,20,.72)' : 'rgba(22,26,34,.66)'),
        backgroundPadding: new Cesium.Cartesian2(7, 4),
        outlineColor: Cesium.Color.fromCssColorString(isHot ? 'rgba(255,120,90,.95)' : 'rgba(200,210,225,.55)'),
        outlineWidth: isHot ? 2.5 : 1.2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        // 上限放大到 1.3M：全览（相机高度约 80–120 万米）也常显县名
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(12000, 1300000),
        scaleByDistance: new Cesium.NearFarScalar(80000, 1.05, 1300000, 0.72)
      }
    });
    lb._lon = ctr[0]; lb._lat = ctr[1]; lb._h = 600;
    elevEnts.push(lb); labelEnts.push(lb);
  }
}""",
"addCountyLabels 加强")

# 5) 县界描边加强（更亮更粗）
rep("""            positions: pts, width: 1.6, arcType: Cesium.ArcType.NONE,
            vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT
          }),
          attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString('rgba(226,210,178,0.55)')) }""",
"""            positions: pts, width: 2.6, arcType: Cesium.ArcType.NONE,
            vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT
          }),
          attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString('rgba(242,226,190,0.9)')) }""",
"county 边界加强")

# 6) NDVI 开关 HTML
rep("""    <div class="sw-row"><span>县级矿山统计</span><div class="sw" id="swAl_county"></div></div>""",
"""    <div class="sw-row"><span>县级矿山统计</span><div class="sw" id="swAl_county"></div></div>
    <div class="sw-row"><span>植被指数 NDVI</span><div class="sw" id="swAl_ndvi"></div></div>""",
"NDVI 开关")

# 7) 配色方案下拉 UI（空间分析图层面板底部）
rep("""    <div id="alLegend" class="hot-legend"></div>
  </div>""",
"""    <div class="sw-row pal-row"><span>配色方案</span>
      <select id="palSel" class="pal-sel">
        <option value="blue-red">蓝—黄—红</option>
        <option value="green">红—黄—绿（植被）</option>
        <option value="thermal">墨—紫—橙—黄</option>
        <option value="ice">白—青—蓝</option>
      </select>
    </div>
    <div id="alLegend" class="hot-legend"></div>
  </div>""",
"配色 UI")

# 8) startApp 注册 NDVI
rep("""  buildCountyPrims();
  addPoints();
  addCountyLabels();""",
"""  buildCountyPrims();
  addPoints();
  // NDVI 栅格图层注册（Sentinel-2 L2A 反演，最大值合成 MVC）
  if (window.NDVI_DATA){
    window.AL_META.ndvi = { name:'植被指数 NDVI', kind:'grid', colorBy:'ndvi', ramp:'seq', label:'NDVI' };
    window.AL.ndvi = window.NDVI_DATA;
  }
  addCountyLabels();""",
"startApp 注册 ndvi")

# 9) buildAlGrid 函数 + buildAlLayer 分支
rep("""  return coll;
}

function buildAlLayer(key){""",
"""  return coll;
}

/* NDVI 栅格：自定义 DEM 非 terrainProvider，GroundPrimitive 贴椭球面会被山体埋掉。
   改为规则经纬网格（降采样 lod 顶点），逐顶点按 DEM 抬升 + 逐像元值着色。 */
function buildAlGrid(key, meta){
  var ND = window.NDVI_DATA; if (!ND) return null;
  var W = ND.width, H = ND.height;
  var b = atob(ND.data), raw = new Uint8Array(b.length);
  for (var zi = 0; zi < b.length; zi++) raw[zi] = b.charCodeAt(zi);
  function ndAt(i, j){ var v = raw[j * W + i]; if (v === 0) return NaN; return -1 + (v - 1) / 254 * 2; }
  var lod = 220, nx = lod, ny = lod, gx = nx + 1, gy = ny + 1;
  var rg = { mn: 1e18, mx: -1e18 };
  var vals = new Float32Array(gx * gy), hs = new Float64Array(gx * gy);
  for (var j = 0; j < gy; j++){
    var lat = ND.south + (ND.north - ND.south) * j / ny;
    for (var i = 0; i < gx; i++){
      var lon = ND.west + (ND.east - ND.west) * i / nx;
      var fi = Math.round((lon - ND.west) / (ND.east - ND.west) * (W - 1));
      var fj = Math.round((ND.north - lat) / (ND.north - ND.south) * (H - 1));
      fi = Math.max(0, Math.min(W - 1, fi)); fj = Math.max(0, Math.min(H - 1, fj));
      var v = ndAt(fi, fj);
      vals[j * gx + i] = isNaN(v) ? NaN : v;
      if (!isNaN(v)){ if (v < rg.mn) rg.mn = v; if (v > rg.mx) rg.mx = v; }
      hs[j * gx + i] = surfaceH(lon, lat, AL_LIFT);
    }
  }
  alRange['ndvi'] = rg;
  var VP = [], VC = [], IDX = [];
  for (var j = 0; j < ny; j++){
    for (var i = 0; i < nx; i++){
      var i00 = j * gx + i;
      if (isNaN(vals[i00]) || isNaN(vals[i00 + 1]) || isNaN(vals[i00 + gx]) || isNaN(vals[i00 + gx + 1])) continue;
      var a0 = rg.mx > rg.mn ? Math.pow((vals[i00] - rg.mn) / (rg.mx - rg.mn), 0.5) : 0;
      var a1 = rg.mx > rg.mn ? Math.pow((vals[i00 + 1] - rg.mn) / (rg.mx - rg.mn), 0.5) : 0;
      var a2 = rg.mx > rg.mn ? Math.pow((vals[i00 + gx] - rg.mn) / (rg.mx - rg.mn), 0.5) : 0;
      var a3 = rg.mx > rg.mn ? Math.pow((vals[i00 + gx + 1] - rg.mn) / (rg.mx - rg.mn), 0.5) : 0;
      var c00 = seqRamp(a0).withAlpha(0.20 + 0.45 * a0);
      var c10 = seqRamp(a1).withAlpha(0.20 + 0.45 * a1);
      var c01 = seqRamp(a2).withAlpha(0.20 + 0.45 * a2);
      var c11 = seqRamp(a3).withAlpha(0.20 + 0.45 * a3);
      var vb = VP.length / 3;
      alPushV(VP, VC, ND.west + (ND.east - ND.west) * i / nx,       ND.south + (ND.north - ND.south) * j / ny,       hs[i00], c00);
      alPushV(VP, VC, ND.west + (ND.east - ND.west) * (i + 1) / nx, ND.south + (ND.north - ND.south) * j / ny,       hs[i00 + 1], c10);
      alPushV(VP, VC, ND.west + (ND.east - ND.west) * (i + 1) / nx, ND.south + (ND.north - ND.south) * (j + 1) / ny, hs[i00 + gx + 1], c11);
      alPushV(VP, VC, ND.west + (ND.east - ND.west) * i / nx,       ND.south + (ND.north - ND.south) * (j + 1) / ny, hs[i00 + gx], c01);
      IDX.push(vb, vb + 1, vb + 2, vb, vb + 2, vb + 3);
    }
  }
  if (!IDX.length) return null;
  var posArr = new Float32Array(VP), colArr = new Float32Array(VC);
  var geo = new Cesium.Geometry({
    attributes: {
      position: new Cesium.GeometryAttribute({ componentDatatype: Cesium.ComponentDatatype.FLOAT, componentsPerAttribute: 3, values: posArr }),
      color: new Cesium.GeometryAttribute({ componentDatatype: Cesium.ComponentDatatype.FLOAT, componentsPerAttribute: 4, values: colArr }),
      batchId: new Cesium.GeometryAttribute({ componentDatatype: Cesium.ComponentDatatype.FLOAT, componentsPerAttribute: 1, values: new Float32Array(VP.length / 3) })
    },
    indices: new Uint32Array(IDX),
    primitiveType: Cesium.PrimitiveType.TRIANGLES,
    boundingSphere: Cesium.BoundingSphere.fromVertices(posArr)
  });
  var prim = new Cesium.Primitive({ geometryInstances: new Cesium.GeometryInstance({ geometry: geo }), appearance: alAppearance(), asynchronous: false, compressVertices: false, allowPicking: false });
  prim._alStat = alMeshStat(posArr);
  viewer.scene.primitives.add(prim);
  return prim;
}

function buildAlLayer(key){""",
"buildAlGrid + 注册")

# 10) buildAlLayer kind 分支
rep("""  var obj = (meta.kind === 'poly') ? buildAlPoly(key, gj, meta) : buildAlPoint(key, gj, meta);""",
"""  var obj = (meta.kind === 'poly') ? buildAlPoly(key, gj, meta)
          : (meta.kind === 'grid') ? buildAlGrid(key, meta)
          : buildAlPoint(key, gj, meta);""",
"buildAlLayer kind 分支")

# 11) bindUI 配色切换 onchange
rep("""  window.addEventListener('keydown', function(e){""",
"""  // 配色方案切换：重建所有已开分析层 + 同步图例
  var ps = document.getElementById('palSel');
  if (ps) ps.addEventListener('change', function(){
    curPal = ps.value;
    rebuildAlLayers();
    for (var k in alOn){ if (alOn[k]){ buildAlLegend(k, true); break; } }
  });

  window.addEventListener('keydown', function(e){""",
"bindUI 配色 onchange")

open(P, 'w', encoding='utf-8').write(s)
print('=== 全部替换完成，文件大小', len(s), '字符 ===')
