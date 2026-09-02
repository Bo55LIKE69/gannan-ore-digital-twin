# 移除"矿点贴地 / 整体离地抬升"控件（点已吸附 DEM，该控件无用）
import io, sys

PATH = r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html"
raw = io.open(PATH, encoding="utf-8").read()

def rep(old, new, n=1):
    global raw
    cnt = raw.count(old)
    if cnt != n:
        raise SystemExit(f"[FAIL] 期望命中 {n} 次，实际 {cnt} 次\n--- needle ---\n{old}")
    raw = raw.replace(old, new)

# 1) 左侧"矿点贴地"整段 section
rep(
'''  <div class="sec">
    <div class="sec-t">矿点贴地 <span class="sub">吸附 DEM 表面</span></div>
    <div class="ctl">
      <div class="ctl-h"><span>整体离地抬升</span><span class="cv" id="vLift">0 m</span></div>
      <input type="range" id="sLift" min="0" max="12000" step="250" value="0">
    </div>
  </div>
''', '')

# 2) bindUI 里 sLift 绑定块
rep(
'''  // 矿点整体离地抬升：只抬光柱，锚点留在 DEM 表面
  var liftRaf = null;
  rng($('sLift'), function(v){
    LIFT = v;
    $('vLift').textContent = v >= 1000 ? (v / 1000).toFixed(2) + ' km' : v.toFixed(0) + ' m';
    if (liftRaf) cancelAnimationFrame(liftRaf);
    liftRaf = requestAnimationFrame(function(){ liftRaf = null; applyLift(); });
  });

  function sw(id, key){''',
'''  function sw(id, key){''')

# 3) 死变量 LIFT
rep('var LIFT = 0;                 // 矿点整体离地抬升（m），只作用于矿点/案例，锚点留地\n', '')

# 4) applyLift 里的 LIFT 抬升项（保留函数，垂直夸张变化时仍需按 surfaceH 重贴地）
rep('    z = surfaceH(e._lon, e._lat, e._h) + (e._useLift ? LIFT : 0);',
    '    z = surfaceH(e._lon, e._lat, e._h);')

# 5) _useLift 赋值（已无意义）
rep('    e._county = p.county; e._hs = p.hs; e._gi = p.gi; e._useLift = true;',
    '    e._county = p.county; e._hs = p.hs; e._gi = p.gi;')
rep('    lb._lon = p.lon; lb._lat = p.lat; lb._h = 200; lb._useLift = false;',
    '    lb._lon = p.lon; lb._lat = p.lat; lb._h = 200;')

io.open(PATH, "w", encoding="utf-8").write(raw)
print("OK 全部替换完成")
