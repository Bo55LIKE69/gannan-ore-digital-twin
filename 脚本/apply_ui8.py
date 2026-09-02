# -*- coding: utf-8 -*-
"""UI8: 工艺卡精准导航到矿点 + 工艺画廊可收起。
大文件用字面量精确替换，每处断言恰好替换 1 次。"""
import io, sys

F = "赣南矿脉_数字孪生大屏.html"
raw = open(F, encoding="utf-8").read()
orig = raw

def rep(old, new, raw, label):
    c = raw.count(old)
    if c != 1:
        raise SystemExit("[FAIL] %s 匹配次数=%d (期望1)" % (label, c))
    return raw.replace(old, new, 1)

# ---- 1. CSS: 工艺画廊可收起样式 (插在 .proc-go 之后) ----
raw = rep(
    ".proc-go{color:var(--gold);font-weight:600}\n",
    ("  .proc-go{color:var(--gold);font-weight:600}\n"
     "\n"
     "/* 工艺画廊可收起 */\n"
     "  .sec-t{cursor:pointer;user-select:none}\n"
     "  .collapse-arrow{margin-left:auto;font-size:12px;color:var(--dim);\n"
     "    transition:transform .25s;display:inline-block;padding-left:8px}\n"
     "  .sec.collapsed .collapse-arrow{transform:rotate(-90deg)}\n"
     "  .sec.collapsed #procList{display:none;margin:0}\n"),
    raw, "css-collapse")

# ---- 2. HTML: sec-t 加折叠箭头 ----
raw = rep(
    '    <div class="sec-t">稀土开采工艺 <span class="sub">点击飞行 · 四代演进</span></div>',
    ('    <div class="sec-t" id="procSecT">稀土开采工艺 '
     '<span class="sub">点击飞行 · 四代演进</span>'
     '<span class="collapse-arrow">▾</span></div>'),
    raw, "html-arrow")

# ---- 3. 删除 PROC_CAM 死变量 ----
raw = rep(
    "var PROC_CAM = [114.98, 24.92, 42000, -44, 8];   // 定南—龙南稀土矿区概览\n\n",
    "",
    raw, "del-proccam")

# ---- 4. 新增 PROC_LL 坐标表 (在 buildProcGallery 定义前) ----
PROC_LL = (
    "// 四代工艺代表性稀土矿区坐标（取自真实稀土矿点：龙南/寻乌/安远/兴国）\n"
    "var PROC_LL = { 1:[114.7048, 24.9722], 2:[115.6672, 25.0110],\n"
    "                3:[115.5006, 25.2902], 4:[115.4506, 26.6334] };\n\n"
)
raw = rep(
    "function buildProcGallery(){",
    PROC_LL + "function buildProcGallery(){",
    raw, "add-procll")

# ---- 5. 改 buildProcGallery 点击逻辑 ----
raw = rep(
    ("  var rows = document.querySelectorAll('#procList .proccard');\n"
     "  for (var i = 0; i < rows.length; i++){\n"
     "    rows[i].addEventListener('click', function(){\n"
     "      var g = parseInt(this.getAttribute('data-g'), 10);\n"
     "      var cs = (D.cases || []).filter(function(x){ return x.gen === g; });\n"
     "      if (cs.length) flyToCase((D.cases || []).indexOf(cs[0]));\n"
     "      else flyTo(PROC_CAM[0], PROC_CAM[1], PROC_CAM[2], PROC_CAM[3], PROC_CAM[4], 2.6);\n"
     "    });\n"
     "  }\n"
     "}\n"),
    ("  var rows = document.querySelectorAll('#procList .proccard');\n"
     "  for (var i = 0; i < rows.length; i++){\n"
     "    rows[i].addEventListener('click', function(){\n"
     "      var g = parseInt(this.getAttribute('data-g'), 10);\n"
     "      var p = PROCS.filter(function(x){ return x.g === g; })[0];\n"
     "      if (p) flyToProc(p);\n"
     "    });\n"
     "  }\n"
     "}\n"
     "\n"
     "/* 工艺卡精准导航：直接飞到该代代表性稀土矿点，不再回退概览 */\n"
     "function flyToProc(p){\n"
     "  var ll = PROC_LL[p.g];\n"
     "  if (!ll) return;\n"
     "  flyTo(ll[0], ll[1], 12000, -30, 0, 2.2);\n"
     "  setTimeout(function(){ showProcPopup(p); }, 1500);\n"
     "}\n"
     "function showProcPopup(p){\n"
     "  $('ppTitle').textContent = p.n + '（第' + p.g + '代）';\n"
     "  $('ppTag').textContent = p.y + ' · 回收率 ' + p.r;\n"
     "  $('ppDesc').textContent = p.d + ' 代表性矿区：' + p.lon0(ll) + '。';\n"
     "  var pp = $('popup');\n"
     "  pp.style.left = (window.innerWidth / 2 - 170) + 'px';\n"
     "  pp.style.top  = (window.innerHeight / 2 - 110) + 'px';\n"
     "  pp.classList.add('show');\n"
     "}\n"),
    raw, "rewrite-click")

# 修正 showProcPopup 里的坐标文本（上面误用了 p.lon0(ll)，改为真实 ll）
raw = rep(
    "  $('ppDesc').textContent = p.d + ' 代表性矿区：' + p.lon0(ll) + '。';\n",
    "  $('ppDesc').textContent = p.d + ' 代表性矿区：' + ll[0].toFixed(3) + '°E, ' + ll[1].toFixed(3) + '°N。';\n",
    raw, "fix-popup-coord")

# ---- 6. bindUI: 折叠绑定 (keydown 块之后) ----
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
     "  // 工艺画廊折叠\n"
     "  var pst = document.getElementById('procSecT');\n"
     "  if (pst) pst.addEventListener('click', function(){\n"
     "    document.getElementById('procSec').classList.toggle('collapsed');\n"
     "  });\n"),
    raw, "bind-collapse")

assert raw != orig, "没有任何改动？"
open(F, "w", encoding="utf-8").write(raw)
print("UI8 替换完成，文件大小 %d -> %d 字节" % (len(orig.encode('utf-8')), len(raw.encode('utf-8'))))
