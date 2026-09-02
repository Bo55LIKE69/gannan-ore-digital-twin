# -*- coding: utf-8 -*-
import re, sys

F = r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html"
raw = open(F, encoding="utf-8").read()
orig = raw

def must(cond, msg):
    if not cond:
        print("FAIL:", msg); sys.exit(1)

def rep(old, new, n=1, flags=0):
    global raw
    cnt = raw.count(old) if flags == 0 else len(re.findall(old, raw, flags))
    must(cnt == n, "期望出现 %d 次，实际 %d 次: %s" % (n, cnt, old[:50]))
    raw = raw.replace(old, new, 1) if flags == 0 else re.sub(old, new, raw, count=n, flags=flags)

# 1) 顶部 hint 文案去掉“1–6 切换章节”
rep('<div class="hint" id="hint">1–6 切换章节 · H 隐藏面板 · 点击矿点查看详情</div>',
    '<div class="hint" id="hint">H 隐藏面板 · 点击矿点查看详情</div>')

# 2) 县域开关默认关（匹配序章原状态）
rep('    <div class="sw-row"><span>县域面 / 边界</span><div class="sw on" id="swCounty"></div></div>',
    '    <div class="sw-row"><span>县域面 / 边界</span><div class="sw" id="swCounty"></div></div>')

# 3) 右面板：章节标签 + 叙述卡 + genSec 列表 -> 工艺画廊
rep('''<!-- 右面板 -->
<div class="panel" id="rightPanel">
  <div class="chtabs" id="chTabs"></div>
  <div class="chapter">
    <div class="idx" id="chIdx">CHAPTER 00</div>
    <div class="ttl" id="chTtl">—</div>
    <div class="body" id="chBody">—</div>
    <div class="kv" id="chKv"></div>
  </div>

  <div class="sec" id="genSec" style="display:none">
    <div class="sec-t">稀土工艺代际 <span class="sub">点击定位</span></div>
    <div id="genList"></div>
  </div>

  <div class="sec">
    <div class="sec-t">县级矿点排行 <span class="sub">点击飞行</span></div>
    <div id="rankList"></div>
  </div>

  <div class="sec" id="ctyDetail" style="display:none">
    <div class="sec-t">县域详情</div>
    <div id="detailContent"></div>
  </div>

</div>''',
'''<!-- 右面板 -->
<div class="panel" id="rightPanel">
  <div class="sec" id="procSec">
    <div class="sec-t">稀土开采工艺 <span class="sub">点击飞行 · 四代演进</span></div>
    <div id="procList"></div>
  </div>

  <div class="sec">
    <div class="sec-t">县级矿点排行 <span class="sub">点击飞行</span></div>
    <div id="rankList"></div>
  </div>

  <div class="sec" id="ctyDetail" style="display:none">
    <div class="sec-t">县域详情</div>
    <div id="detailContent"></div>
  </div>

</div>''')

# 4) CSS：章节叙述卡 + 章节标签 -> 工艺画廊样式
rep('''/* 章节叙述卡 */
.chapter{background:linear-gradient(160deg,rgba(201,148,74,.09),rgba(201,148,74,.02));
  border:1px solid rgba(201,148,74,.24);border-radius:9px;padding:14px 15px;margin-bottom:14px;
  position:relative;overflow:hidden}
.chapter .idx{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--gold);letter-spacing:.24em}
.chapter .ttl{font-size:17px;font-weight:700;color:#f0e0c0;margin:5px 0 7px;letter-spacing:.03em}
.chapter .body{font-size:11.5px;color:#9aa4b2;line-height:1.85;letter-spacing:.02em}
.chapter .kv{display:flex;gap:16px;margin-top:11px;padding-top:10px;border-top:1px solid rgba(255,255,255,.06)}
.chapter .kv .i .v{font-family:'JetBrains Mono',monospace;font-size:16px;color:var(--gold);font-weight:600}
.chapter .kv .i .l{font-size:9.5px;color:var(--dim2);letter-spacing:.1em;margin-top:1px}

/* ===== 章节标签（右面板顶部，替代底部故事条） ===== */
.chtabs{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:13px}
.chtab{display:flex;align-items:center;gap:5px;padding:4px 9px;border-radius:14px;cursor:pointer;
  border:1px solid var(--border);background:var(--panel-2);
  transition:all .22s;opacity:.6;white-space:nowrap}
.chtab:hover{opacity:1;border-color:rgba(201,148,74,.5)}
.chtab .cn{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--dim2);
  padding:0 4px;border-radius:6px;background:rgba(255,255,255,.06)}
.chtab .nm{font-size:10.5px;color:var(--dim)}
.chtab:hover .nm{color:var(--text)}
.chtab.on{opacity:1;background:rgba(201,148,74,.16);border-color:var(--gold);
  box-shadow:0 0 12px rgba(201,148,74,.22)}
.chtab.on .cn{background:var(--gold);color:#1a1206;font-weight:600}
.chtab.on .nm{color:#f0d9a8;font-weight:600}''',
'''/* 稀土开采工艺画廊 */
.proccard{display:flex;gap:11px;align-items:stretch;padding:9px;border-radius:9px;cursor:pointer;
  border:1px solid rgba(201,148,74,.18);background:var(--panel-2);margin-bottom:11px;
  transition:all .22s;overflow:hidden}
.proccard:hover{border-color:var(--gold);background:rgba(201,148,74,.1);
  box-shadow:0 0 14px rgba(201,148,74,.2)}
.procimg{width:104px;height:78px;object-fit:cover;border-radius:6px;flex:0 0 auto;
  border:1px solid rgba(255,255,255,.08);background:#1a1d24}
.procmeta{display:flex;flex-direction:column;justify-content:space-between;min-width:0;flex:1}
.proc-h{display:flex;align-items:center;gap:7px}
.proc-gen{font-size:9px;font-weight:700;color:#1a1206;padding:1px 6px;border-radius:10px;white-space:nowrap}
.proc-name{font-size:13px;font-weight:600;color:#f0e0c0}
.proc-yr{font-size:9.5px;color:var(--dim2);margin-left:auto;font-family:'JetBrains Mono',monospace}
.proc-d{font-size:10.5px;color:var(--dim);line-height:1.5;margin:4px 0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.proc-foot{display:flex;justify-content:space-between;align-items:center;
  font-size:10px;color:var(--dim2)}
.proc-go{color:var(--gold);font-weight:600}''')

# 5) 删除 buildGenList 函数（由工艺画廊取代）
rep('''function buildGenList(){
  var gens = [
    { g: 1, n: '池浸', y: '1970s', r: '30~38%', c: '#e2544a' },
    { g: 2, n: '堆浸', y: '1980s末', r: '45~55%', c: '#c0703a' },
    { g: 3, n: '原地浸矿', y: '1990s', r: '70~78%', c: '#c9944a' },
    { g: 4, n: '无铵绿色', y: '近年', r: '82~88%', c: '#5aa06a' }
  ];
  var html = '';
  gens.forEach(function(x){
    var cases = (D.cases || []).filter(function(c){ return c.gen === x.g; });
    html += '<div class="rank" data-g="' + x.g + '">' +
      '<span class="dot" style="width:8px;height:8px;border-radius:50%;background:' + x.c + ';box-shadow:0 0 7px ' + x.c + '"></span>' +
      '<span class="nm">' + x.n + '<span style="color:#5c6574;font-size:10px"> · ' + x.y + '</span></span>' +
      '<span class="c" style="width:auto;font-size:10px;color:#828b9a">' + x.r + '</span></div>';
  });
  $('genList').innerHTML = html;
  var rows = document.querySelectorAll('#genList .rank');
  for (var i = 0; i < rows.length; i++){
    rows[i].addEventListener('click', function(){
      var g = parseInt(this.getAttribute('data-g'), 10);
      var c = (D.cases || []).filter(function(x){ return x.gen === g; })[0];
      if (c) flyToCase((D.cases || []).indexOf(c));
    });
  }
}''',
'/* 工艺代际列表函数已移除：由稀土开采工艺画廊（buildProcGallery）取代 */')

# 6) CHAPTERS 数组 -> PROCS 数组（正则，避免特殊字符）
raw, k = re.subn(r"var CHAPTERS = \[.*?\n\];",
    "var PROCS = [\n"
    "  { g:1, img:'工艺图/池浸.png',            n:'池浸',     y:'1970s',  r:'30~38%', c:'#e2544a',\n"
    "    d:'全坡面剥离表土、筑池浸矿，植被损毁最大，是第一代工艺。' },\n"
    "  { g:2, img:'工艺图/堆浸.png',            n:'堆浸',     y:'1980s末', r:'45~55%', c:'#c0703a',\n"
    "    d:'原矿就地筑堆、喷淋浸出，处理规模与效率显著提升。' },\n"
    "  { g:3, img:'工艺图/原地浸矿.png',         n:'原地浸矿', y:'1990s',  r:'70~78%', c:'#c9944a',\n"
    "    d:'打注液井原地浸出，不搬动矿石，地表扰动大幅减小。' },\n"
    "  { g:4, img:'工艺图/无铵绿色原地浸矿.png', n:'无铵绿色', y:'近年',   r:'82~88%', c:'#5aa06a',\n"
    "    d:'无铵浸矿剂 + 废液闭环回收，绿色工艺、外排水达Ⅲ类。' }\n"
    "];\n"
    "var PROC_CAM = [114.98, 24.92, 42000, -44, 8];   // 定南—龙南稀土矿区概览",
    raw, count=1, flags=re.DOTALL)
must(k == 1, "CHAPTERS 数组替换失败")

# 7) 删除 var curCh = -1;
rep("var curCh = -1;\n", "")

# 8) buildSteps -> buildProcGallery
rep('''function buildSteps(){
  var html = '';
  CHAPTERS.forEach(function(c, i){
    var parts = c.t.split(' · ');
    var ord = parts[0] || ('第' + (i + 1) + '章');
    var nm = parts[1] || c.t;
    html += '<div class="chtab" data-i="' + i + '" title="' + (c.t + '：' + c.b.slice(0, 40) + '…') + '">' +
      '<span class="cn">' + ord + '</span>' +
      '<span class="nm">' + nm + '</span></div>';
  });
  $('chTabs').innerHTML = html;
  var els = document.querySelectorAll('.chtab');
  for (var i = 0; i < els.length; i++){
    els[i].addEventListener('click', function(){ gotoChapter(parseInt(this.getAttribute('data-i'), 10)); });
  }
}''',
'''function buildProcGallery(){
  var html = '';
  PROCS.forEach(function(p){
    html += '<div class="proccard" data-g="' + p.g + '">' +
      '<img class="procimg" src="' + p.img + '" alt="' + p.n + '" loading="lazy">' +
      '<div class="procmeta">' +
        '<div class="proc-h"><span class="proc-gen" style="background:' + p.c + '">第' + p.g + '代</span>' +
          '<span class="proc-name">' + p.n + '</span>' +
          '<span class="proc-yr">' + p.y + '</span></div>' +
        '<div class="proc-d">' + p.d + '</div>' +
        '<div class="proc-foot"><span>回收率 ' + p.r + '</span>' +
          '<span class="proc-go">点击飞行 ▸</span></div>' +
      '</div></div>';
  });
  $('procList').innerHTML = html;
  var rows = document.querySelectorAll('#procList .proccard');
  for (var i = 0; i < rows.length; i++){
    rows[i].addEventListener('click', function(){
      var g = parseInt(this.getAttribute('data-g'), 10);
      var cs = (D.cases || []).filter(function(x){ return x.gen === g; });
      if (cs.length) flyToCase((D.cases || []).indexOf(cs[0]));
      else flyTo(PROC_CAM[0], PROC_CAM[1], PROC_CAM[2], PROC_CAM[3], PROC_CAM[4], 2.6);
    });
  }
}''')

# 9) gotoChapter -> initView
rep('''function gotoChapter(i){
  if (i < 0 || i >= CHAPTERS.length) return;
  curCh = i;
  var c = CHAPTERS[i];
  var els = document.querySelectorAll('.chtab');
  for (var k = 0; k < els.length; k++) els[k].classList.toggle('on', k === i);

  $('chIdx').textContent = 'CHAPTER ' + (i < 10 ? '0' + i : i);
  $('chTtl').textContent = c.t;
  $('chBody').textContent = c.b;
  var kv = '';
  c.kv.forEach(function(x){ kv += '<div class="i"><div class="v">' + x[0] + '</div><div class="l">' + x[1] + '</div></div>'; });
  $('chKv').innerHTML = kv;
  $('genSec').style.display = c.gen ? 'block' : 'none';
  $('rightPanel').scrollTop = 0;

  flyTo(c.cam[0], c.cam[1], c.cam[2], c.cam[3], c.cam[4], 2.6);

  // 图层
  LAYER.points = !!c.vis.points;
  LAYER.county = !!c.vis.county;
  syncSwitches();
  applyLayerVis();
  if (i !== 4) $('popup').classList.remove('show');
}''',
'''function initView(){
  LAYER.points = 1; LAYER.county = 0;
  syncSwitches(); applyLayerVis();
  flyTo(115.05, 25.80, 265000, -52, -18, 2.6);
  $('rightPanel').scrollTop = 0;
}''')

# 10) 键盘：去掉 1-6 章节跳转，保留 H
rep('''  window.addEventListener('keydown', function(e){
    if (e.key >= '1' && e.key <= '6'){
      var n = parseInt(e.key, 10) - 1;
      if (n < CHAPTERS.length) gotoChapter(n);
    }
    else if (e.key === 'h' || e.key === 'H'){
      $('leftPanel').classList.toggle('hidden');
      $('rightPanel').classList.toggle('hidden');
    }
  });''',
'''  window.addEventListener('keydown', function(e){
    if (e.key === 'h' || e.key === 'H'){
      $('leftPanel').classList.toggle('hidden');
      $('rightPanel').classList.toggle('hidden');
    }
  });''')

# 11) 启动：buildGenList/buildSteps/gotoChapter(0) -> buildProcGallery/initView
rep('''  buildRank();
  buildGenList();
  buildSteps();
  fillStats();
  bindUI();
  syncSwitches();
  try { if (window.AL) alShow('density'); } catch (e) { console.warn('density 默认开启失败', e); }
  gotoChapter(0);''',
'''  buildRank();
  buildProcGallery();
  fillStats();
  bindUI();
  syncSwitches();
  try { if (window.AL) alShow('density'); } catch (e) { console.warn('density 默认开启失败', e); }
  initView();''')

# 校验：旧引用应全部消失
for bad in ['CHAPTERS', 'chTabs', 'chIdx', 'chTtl', 'chBody', 'chKv', 'genSec', 'genList',
            'buildGenList', 'buildSteps', 'gotoChapter', 'curCh', 'chtab']:
    must(bad not in raw, "残留引用: " + bad)

open(F, "w", encoding="utf-8").write(raw)
print("OK: 替换完成，文件大小", len(raw), "字节（原", len(orig), "）")
