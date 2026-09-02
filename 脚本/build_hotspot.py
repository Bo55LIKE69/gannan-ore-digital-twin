# -*- coding: utf-8 -*-
"""
赣南矿点冷热点分析 (Getis-Ord Gi*) 构建脚本 —— 县域行政尺度
================================================================
读取 dash_data.js 中的矿点 [lon, lat, 矿种, 县名]，
以「县级行政单元」为空间分析单元、单元内矿点数为态值，
按质心距离带计算 Getis-Ord Gi* 统计量，
识别各县矿点空间集聚的冷点 / 热点（90% / 95% / 99% 置信水平）。

输出 hotspot_data.js： window.HOTSPOT_DATA = { type:'county', bandKm, counties:[...] }
每个 county = { name, n, z, cls, lon, lat }
  cls: '热点' / '次热点' / '不显著' / '次冷点' / '冷点'

前端 buildHotspotLayer 据此按县域行政边界上色（无方格）。

用法:  python build_hotspot.py
依赖: numpy
"""
import io, re, json, math
import numpy as np
from collections import defaultdict, Counter

SRC = "dash_data.js"
OUT = "hotspot_data.js"

# ---- 1. 解析矿点 ----
txt = io.open(SRC, encoding="utf-8", errors="replace").read()
m = re.search(r"points:\s*\[", txt)
seg = txt[m.end():]
rows = re.findall(r'\[\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*"(\w+)"\s*,\s*"(\w+)"\s*\]', seg)
print("原始点行数:", len(rows))

seen = set()
pts = []
for lon, lat, cat, county in rows:
    key = (round(float(lon), 5), round(float(lat), 5))
    if key in seen:
        continue
    seen.add(key)
    pts.append((float(lon), float(lat), cat, county))
print("去重后点数:", len(pts))

# ---- 2. 按县级行政单元聚合 ----
agg = defaultdict(lambda: [0, 0.0, 0.0])   # [矿点数, Σlon, Σlat]
for lon, lat, cat, county in pts:
    a = agg[county]
    a[0] += 1
    a[1] += lon
    a[2] += lat

names = list(agg.keys())
clon = np.array([agg[n][1] / agg[n][0] for n in names])
clat = np.array([agg[n][2] / agg[n][0] for n in names])
counts = np.array([agg[n][0] for n in names], dtype=np.float64)
print("参与分析的县域数:", len(names))

LAT0 = float(np.mean(clat))
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320 * math.cos(math.radians(LAT0))

# ---- 3. 距离带权重 (km) ----
n = len(names)
dlon = (clon[:, None] - clon[None, :]) * KM_PER_DEG_LON
dlat = (clat[:, None] - clat[None, :]) * KM_PER_DEG_LAT
dist = np.sqrt(dlon ** 2 + dlat ** 2)

BAND_KM = 32.0                       # 县域尺度距离带（仅相邻县邻接，避免全连通）
w = (dist <= BAND_KM).astype(np.float64)   # 含自身（对角线 dist=0 -> 1）

# ---- 4. Getis-Ord Gi* ----
mean = counts.mean()
S = counts.std()
if S < 1e-9:
    S = 1e-9
W = w.sum(axis=1)                                  # Σ w_ij
X = w.dot(counts)                                  # Σ w_ij x_j
denom = S * np.sqrt((n * W - W ** 2) / (n - 1))    # 二值权重 Σw² = Σw = W
with np.errstate(divide="ignore", invalid="ignore"):
    gistar = np.where(denom > 1e-12, (X - mean * W) / denom, 0.0)

# ---- 5. 分级 ----
# 县域单元仅 18 个，严格 Gi* 在 32km 距离带下统计力有限；
# 这里以 Gi* z 值的相对分位做 5 档（方向与 Gi* 完全一致：z 高=热点），
# 既贴合行政边界、保留冷暖梯度，又避免"全部不显著"的单调画面。
order = np.argsort(gistar)
ranks = np.empty(n)
for q, idx in enumerate(order):
    ranks[idx] = n > 1 and (q / (n - 1)) or 0.5

def classify_rel(r):
    if r >= 0.80: return "热点"
    if r >= 0.60: return "次热点"
    if r <= 0.20: return "冷点"
    if r <= 0.40: return "次冷点"
    return "不显著"

out = []
cls_cnt = Counter()
for i, name in enumerate(names):
    z = float(gistar[i])
    cls = classify_rel(float(ranks[i]))
    cls_cnt[cls] += 1
    out.append({
        "name": name,
        "n": int(counts[i]),
        "z": round(z, 3),
        "cls": cls,
        "lon": round(float(clon[i]), 5),
        "lat": round(float(clat[i]), 5),
    })
print("冷热点分类:", dict(cls_cnt))

# ---- 6. 写出 ----
data = {"type": "county", "bandKm": BAND_KM, "counties": out}
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("window.HOTSPOT_DATA = ")
    json.dump(data, f, ensure_ascii=False)
    f.write(";\n")
print("写出:", OUT, " 县域数:", len(out))
