# -*- coding: utf-8 -*-
"""
赣州县级矿场点 Getis-Ord Gi* 冷热点分析
以县级行政区为分析单元，计算各县级单元的矿点密度热点
"""

import os, sys
import shapefile
import numpy as np
from scipy import stats
from shapely.geometry import Point as ShapelyPoint, Polygon as ShapelyPolygon
from shapely.ops import unary_union

BASE = r"E:\Data\赣州稀土"
COUNTY_SHP = os.path.join(BASE, r"赣州市_360700_批量下载\县级", "县级边界_360700.shp")
POINTS_SHP = os.path.join(BASE, "空间分布分析结果", "裁剪后", "赣州矿场点_裁剪后.shp")
OUTPUT = os.path.join(BASE, "冷热点分析结果_县级")
os.makedirs(OUTPUT, exist_ok=True)

print("=" * 60)
print("赣州县级矿场点 Getis-Ord Gi* 冷热点分析")
print("=" * 60)

# ============================================
# 1. 加载县级边界
# ============================================
print("\n[1] 加载县级边界...")
sf_county = shapefile.Reader(COUNTY_SHP, encoding='gbk')
flds = [f[0] for f in sf_county.fields[1:]]
print(f"  字段数: {len(flds)}")

county_names = []
county_codes = []
county_geoms = []

for i in range(len(sf_county.records())):
    r = sf_county.record(i)
    s = sf_county.shape(i)
    name = r[2]       # 县名
    code = r[3]       # 代码
    county_names.append(name)
    county_codes.append(code)

    pts = s.points
    parts = list(s.parts)
    rings = []
    for pi in range(len(parts)):
        start = parts[pi]
        end = parts[pi + 1] if pi + 1 < len(parts) else len(pts)
        ring = pts[start:end]
        if len(ring) >= 3:
            rings.append(ring)

    if len(rings) == 1:
        geom = ShapelyPolygon(rings[0])
    elif len(rings) > 1:
        from shapely.geometry import MultiPolygon
        polys = []
        for ring in rings:
            polys.append(ShapelyPolygon(ring))
        geom = MultiPolygon(polys)
    else:
        geom = None
    county_geoms.append(geom)

n_counties = len(county_names)
print(f"  县级单元: {n_counties}")
for i in range(n_counties):
    print(f"    {county_names[i]} ({county_codes[i]})")

# ============================================
# 2. 空间连接：统计各县矿点数
# ============================================
print("\n[2] 统计各县矿点数...")
sf_pts = shapefile.Reader(POINTS_SHP, encoding='gbk')
pts_flds = [f[0] for f in sf_pts.fields[1:]]
kz_idx = pts_flds.index('kz')
mc_idx = pts_flds.index('mc')

county_counts = np.zeros(n_counties, dtype=np.int32)
county_minerals = {}  # county_idx -> {mineral: count}

for ci in range(n_counties):
    county_minerals[ci] = {}

n_unmatched = 0
for pi in range(len(sf_pts.records())):
    rec = sf_pts.record(pi)
    pt_geom = sf_pts.shape(pi).points[0]
    pt = ShapelyPoint(pt_geom)
    kz = rec[kz_idx]

    matched = False
    for ci in range(n_counties):
        if county_geoms[ci] is not None and (county_geoms[ci].contains(pt) or county_geoms[ci].touches(pt)):
            county_counts[ci] += 1
            county_minerals[ci][kz] = county_minerals[ci].get(kz, 0) + 1
            matched = True
            break

    if not matched:
        n_unmatched += 1

print(f"  未匹配矿点: {n_unmatched}")
for i in range(n_counties):
    top3 = sorted(county_minerals[i].items(), key=lambda x: -x[1])[:3]
    top_str = ', '.join([f'{m}({c})' for m, c in top3]) if top3 else '无'
    print(f"  {county_names[i]}: {county_counts[i]} 矿点 [{top_str}]")

# ============================================
# 3. 构建县级 Queen 空间权重矩阵
# ============================================
print("\n[3] 构建 Queen 空间权重矩阵...")

w_matrix = np.zeros((n_counties, n_counties), dtype=np.int32)
for i in range(n_counties):
    for j in range(n_counties):
        if i == j:
            w_matrix[i, j] = 1  # Gi* includes self
        elif county_geoms[i] is not None and county_geoms[j] is not None:
            # Queen contiguity: shared boundary or vertex
            try:
                if county_geoms[i].touches(county_geoms[j]):
                    w_matrix[i, j] = 1
                elif county_geoms[i].intersects(county_geoms[j]):
                    intersection = county_geoms[i].intersection(county_geoms[j])
                    if intersection is not None and not intersection.is_empty:
                        if intersection.geom_type in ['LineString', 'MultiLineString', 'Point', 'MultiPoint']:
                            w_matrix[i, j] = 1
            except Exception:
                pass

for i in range(n_counties):
    neighbors = [county_names[j] for j in range(n_counties) if w_matrix[i, j] == 1 and j != i]
    print(f"  {county_names[i]}: {len(neighbors)+1} neighbors (incl. self)")

# ============================================
# 4. 计算 Getis-Ord Gi*
# ============================================
print("\n[4] 计算 Getis-Ord Gi* ...")

counts = county_counts.astype(np.float64)
x_mean = np.mean(counts)
x_std = np.std(counts, ddof=1)
if x_std < 1e-10:
    x_std = 1.0

gi_z = np.zeros(n_counties)
gi_p = np.ones(n_counties)

for i in range(n_counties):
    wi_star = np.sum(w_matrix[i])
    if wi_star <= 1:
        gi_z[i] = 0.0
        gi_p[i] = 1.0
        continue

    sum_wx = np.sum(w_matrix[i] * counts)

    numerator = sum_wx - wi_star * x_mean
    S1i = wi_star
    denom = x_std * np.sqrt((n_counties * S1i - wi_star * wi_star) / (n_counties - 1))

    if abs(denom) < 1e-10:
        gi_z[i] = 0.0
        gi_p[i] = 1.0
    else:
        gi_z[i] = numerator / denom
        gi_p[i] = 2.0 * stats.norm.sf(abs(gi_z[i]))

# ============================================
# 5. 冷热点分类
# ============================================
hotspot_class = np.full(n_counties, '', dtype=object)

for i in range(n_counties):
    z = gi_z[i]
    p = gi_p[i]
    if z >= 1.96 and p <= 0.05:
        hotspot_class[i] = '热点'
    elif z >= 1.65 and p <= 0.10:
        hotspot_class[i] = '次热点'
    elif z <= -1.96 and p <= 0.05:
        hotspot_class[i] = '冷点'
    elif z <= -1.65 and p <= 0.10:
        hotspot_class[i] = '次冷点'
    else:
        hotspot_class[i] = '不显著'

print(f"\n  冷热点统计:")
for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    idxs = [i for i in range(n_counties) if hotspot_class[i] == cls]
    if idxs:
        names = ', '.join([county_names[i] for i in idxs])
        print(f"    {cls}: {len(idxs)} 县 ({names})")

# ============================================
# 6. 导出结果
# ============================================
print("\n[5] 导出县级冷热点 shapefile...")

out_shp = os.path.join(OUTPUT, "县级_冷热点分析_GiStar.shp")
w = shapefile.Writer(out_shp, shapeType=5, encoding='utf-8')

for f in flds:
    w.field(f, 'C', 254)
w.field('point_cnt', 'N', 10, 0)
w.field('Gi_ZScore', 'N', 20, 10)
w.field('Gi_PValue', 'N', 20, 10)
w.field('hotspot_cl', 'C', 50)

import shutil

for i in range(n_counties):
    rec = sf_county.record(i)
    shp = sf_county.shape(i)
    w.record(
        *[str(v) for v in rec],
        int(county_counts[i]),
        float(gi_z[i]),
        float(gi_p[i]),
        str(hotspot_class[i])
    )
    # Write polygon
    pts = shp.points
    parts = list(shp.parts)
    if len(parts) == 1:
        w.poly([pts])
    else:
        rings = []
        for pi in range(len(parts)):
            start = parts[pi]
            end = parts[pi + 1] if pi + 1 < len(parts) else len(pts)
            rings.append(pts[start:end])
        w.poly([rings])

w.close()

prj_src = COUNTY_SHP.replace('.shp', '.prj')
prj_dst = out_shp.replace('.shp', '.prj')
if os.path.exists(prj_src):
    shutil.copy(prj_src, prj_dst)

print(f"  已保存: {out_shp}")

# ============================================
# 7. 导出县级矿点 (带热点标签)
# ============================================
print("\n[6] 导出矿点(含县级热点标签)...")

# Build county lookup for fast point-in-polygon
from shapely.prepared import prep
prepared_counties = []
for ci in range(n_counties):
    if county_geoms[ci] is not None:
        prepared_counties.append((ci, prep(county_geoms[ci])))
    else:
        prepared_counties.append((ci, None))

pts_out = os.path.join(OUTPUT, "矿点_县级冷热点_GiStar.shp")
w2 = shapefile.Writer(pts_out, shapeType=1, encoding='utf-8')
for f in pts_flds:
    w2.field(f, 'C', 254)
w2.field('county', 'C', 50)
w2.field('county_pt', 'N', 10, 0)
w2.field('Gi_ZScore', 'N', 20, 10)
w2.field('Gi_PValue', 'N', 20, 10)
w2.field('hotspot_cl', 'C', 50)

for pi in range(len(sf_pts.records())):
    rec = sf_pts.record(pi)
    pt_geom = sf_pts.shape(pi).points[0]
    pt = ShapelyPoint(pt_geom)

    county_name = '未知'
    ci_val = -1
    for ci, prep_geom in prepared_counties:
        if prep_geom is not None and prep_geom.contains(pt):
            county_name = county_names[ci]
            ci_val = ci
            break

    if ci_val >= 0:
        w2.record(
            *[str(v) for v in rec],
            str(county_name),
            int(county_counts[ci_val]),
            float(gi_z[ci_val]),
            float(gi_p[ci_val]),
            str(hotspot_class[ci_val])
        )
    else:
        w2.record(
            *[str(v) for v in rec],
            '未知',
            0,
            0.0,
            1.0,
            '不显著'
        )
    w2.point(*pt_geom)

w2.close()
if os.path.exists(pts_out.replace('.shp', '.prj')):
    pass
else:
    prj_src2 = POINTS_SHP.replace('.shp', '.prj')
    prj_dst2 = pts_out.replace('.shp', '.prj')
    if os.path.exists(prj_src2):
        shutil.copy(prj_src2, prj_dst2)

print(f"  已保存: {pts_out}")

# ============================================
# 8. 生成报告
# ============================================
print("\n[7] 生成分析报告...")

report = """============================================================
赣州县级矿场点 Getis-Ord Gi* 冷热点分析报告
============================================================

数据来源: 赣州矿场点裁剪后数据 (474条) + 赣州县界
分析单元: 18 个县级行政区
分析方法: Getis-Ord Gi* (空间热点分析)
分析日期: 2026-07-23

------------------------------------------------------------
方法说明
------------------------------------------------------------
以县级行政区为分析单元，以各县矿点数量为分析变量，
基于 Queen 邻接建立空间权重矩阵，计算 Getis-Ord Gi*
统计量，识别县级尺度的矿产集聚热点与冷点。

与前期网格级分析的区别:
- 网格分析: 3000m规则网格,反映微观集聚格局
- 县级分析: 行政区单元,反映行政尺度空间格局

------------------------------------------------------------
县级矿点分布
------------------------------------------------------------
"""

for i in range(n_counties):
    top3 = sorted(county_minerals[i].items(), key=lambda x: -x[1])[:3]
    top_str = ', '.join([f'{m}({c})' for m, c in top3]) if top3 else '无'
    report += f"  {county_names[i]}: {county_counts[i]} 矿点 [{top_str}]\n"

report += f"""
均值: {x_mean:.1f} 矿点/县
标准差: {x_std:.1f}

------------------------------------------------------------
Gi* 冷热点分析结果（5级）
------------------------------------------------------------
"""

for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    idxs = [i for i in range(n_counties) if hotspot_class[i] == cls]
    if idxs:
        names = ', '.join([f'{county_names[i]}({county_counts[i]}点)' for i in idxs])
        report += f"  {cls}: {len(idxs)} 县 - {names}\n"

report += f"""
------------------------------------------------------------
ArcGIS Pro 可视化建议
------------------------------------------------------------
1. 加载 县级_冷热点分析_GiStar.shp
2. 按 hotspot_cl 字段分级设色（5级）:
   - 热点(Z>=1.96): 深红
   - 次热点(Z>=1.65): 浅红
   - 不显著: 浅灰
   - 次冷点(Z<=-1.65): 浅蓝
   - 冷点(Z<=-1.96): 深蓝
3. 叠加 point_cnt 字段标注各县矿点数量

------------------------------------------------------------
输出文件清单
------------------------------------------------------------
  县级_冷热点分析_GiStar.shp  -- 县级面 (含Gi*结果)
  矿点_县级冷热点_GiStar.shp  -- 矿点 (含对应县Gi*标签)
  县级冷热点分析报告.txt
"""

with open(os.path.join(OUTPUT, "县级冷热点分析报告.txt"), 'w', encoding='utf-8') as f:
    f.write(report)
print("  报告已保存")

# ============================================
# 汇总
# ============================================
print(f"\n{'='*60}")
print("输出文件")
print(f"{'='*60}")
for fname in sorted(os.listdir(OUTPUT)):
    fpath = os.path.join(OUTPUT, fname)
    size = os.path.getsize(fpath)
    if size > 1024*1024:
        print(f"  {fname} ({size/1024/1024:.1f} MB)")
    else:
        print(f"  {fname} ({size:,} bytes)")

print(f"\n完毕!")
