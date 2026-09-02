# -*- coding: utf-8 -*-
"""
赣州矿场点 Getis-Ord Gi* 冷热点分析
基于渔网格网密度，计算每个网格的热点显著性
"""

import os, sys
import shapefile
import numpy as np
from scipy import stats

BASE = r"E:\Data\赣州稀土"
GRID_SHP = os.path.join(BASE, "空间分布分析结果", "渔网格网_矿点密度.shp")
NATL_SHP = os.path.join(BASE, r"【250610】全国矿产地分布数据\原始数据", "全国矿产地分布数据.shp")
OUTPUT = os.path.join(BASE, "冷热点分析结果")
os.makedirs(OUTPUT, exist_ok=True)

print("=" * 60)
print("赣州矿场点 Getis-Ord Gi* 冷热点分析")
print("=" * 60)

# ============================================
# 1. 加载渔网格网数据
# ============================================
print("\n[1] 加载渔网格网...")
grid_sf = shapefile.Reader(GRID_SHP, encoding='utf-8')
grid_fields = [f[0] for f in grid_sf.fields[1:]]
print(f"  字段: {grid_fields}")
print(f"  网格数: {len(grid_sf.records())}")

# Build grid data
cell_data = {}  # (row, col) -> index in records
records_list = []
shapes_list = []
counts_list = []

for idx in range(len(grid_sf.records())):
    rec = grid_sf.record(idx)
    shp = grid_sf.shape(idx)
    cell_row = rec[grid_fields.index('cell_row')]
    cell_col = rec[grid_fields.index('cell_col')]
    cnt = rec[grid_fields.index('count')]
    cell_data[(cell_row, cell_col)] = idx
    records_list.append(rec)
    shapes_list.append(shp)
    counts_list.append(cnt)

counts = np.array(counts_list, dtype=np.float64)
n = len(counts)
print(f"  有效网格: {n}")
print(f"  矿点密度: mean={np.mean(counts):.4f}, std={np.std(counts):.4f}, max={np.max(counts)}")
print(f"  非零网格: {np.sum(counts > 0)}")

# ============================================
# 2. 构建 Queen 空间权重矩阵
# ============================================
print("\n[2] 构建 Queen 空间权重矩阵...")

# Queen contiguity: 8 neighbors + self (for Gi*)
w_neighbors = {}  # idx -> list of (neighbor_idx, weight)
w_sum = np.zeros(n)
w_sq_sum = np.zeros(n)

for (row, col), idx in cell_data.items():
    neighbors = []
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            n_key = (row + dr, col + dc)
            if n_key in cell_data:
                neighbors.append(cell_data[n_key])

    w_neighbors[idx] = neighbors
    w_sum[idx] = len(neighbors)
    w_sq_sum[idx] = len(neighbors)

print(f"  平均邻居数: {np.mean(w_sum):.1f}")
print(f"  孤立网格: {np.sum(w_sum == 1)}")

# ============================================
# 3. 计算 Getis-Ord Gi* 统计量
# ============================================
print("\n[3] 计算 Getis-Ord Gi* ...")

x_mean = np.mean(counts)
x_std = np.std(counts)
n_eff = n

# Gi* for each cell
gi_z = np.zeros(n)
gi_p = np.ones(n)

for i in range(n):
    neighbors = w_neighbors[i]
    wi_star = len(neighbors)
    if wi_star <= 1:
        gi_z[i] = 0.0
        gi_p[i] = 1.0
        continue

    # Weighted sum of neighbor values
    sum_wx = sum(counts[j] for j in neighbors)

    # Gi* numerator
    numerator = sum_wx - wi_star * x_mean

    # Gi* denominator
    S1i = wi_star  # for binary weights, w² = w
    denominator = x_std * np.sqrt((n_eff * S1i - wi_star * wi_star) / (n_eff - 1))

    if abs(denominator) < 1e-10:
        gi_z[i] = 0.0
        gi_p[i] = 1.0
    else:
        gi_z[i] = numerator / denominator
        gi_p[i] = 2.0 * stats.norm.sf(abs(gi_z[i]))  # two-tailed p-value

# ============================================
# 4. 分类热点级别 (5级)
# ============================================
hotspot_class = np.full(n, '不显著', dtype=object)

for i in range(n):
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

print(f"\n[4] 冷热点统计:")
for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    cnt = np.sum(hotspot_class == cls)
    if cnt > 0:
        print(f"  {cls}: {cnt} 个网格 ({cnt/n*100:.1f}%)")

# ============================================
# 5. 导出 shapefile
# ============================================
print("\n[5] 导出冷热点分析结果...")

out_shp = os.path.join(OUTPUT, "渔网格网_冷热点分析_GiStar.shp")
w = shapefile.Writer(out_shp, shapeType=5, encoding='utf-8')  # Polygon

# Fields
for f in grid_fields:
    w.field(f, 'C', 254)
w.field('Gi_ZScore', 'N', 20, 10)
w.field('Gi_PValue', 'N', 20, 10)
w.field('hotspot_cl', 'C', 50)

for i in range(n):
    rec = records_list[i]
    shp = shapes_list[i]
    w.record(
        *[str(v) for v in rec],
        float(gi_z[i]),
        float(gi_p[i]),
        str(hotspot_class[i])
    )
    # poly() expects: list of polygons, each a list of rings, each a list of [x,y]
    pts = shp.points
    parts = list(shp.parts)
    if len(parts) == 1:
        # Simple polygon
        w.poly([pts])
    else:
        # Multi-part polygon - split by part indices
        rings = []
        for pi in range(len(parts)):
            start = parts[pi]
            end = parts[pi + 1] if pi + 1 < len(parts) else len(pts)
            rings.append(pts[start:end])
        w.poly([rings])

w.close()

# Copy prj
import shutil
prj_src = GRID_SHP.replace('.shp', '.prj')
prj_dst = out_shp.replace('.shp', '.prj')
if os.path.exists(prj_src):
    shutil.copy(prj_src, prj_dst)

print(f"  已保存: {out_shp}")

# ============================================
# 6. 导出矿点级别冷热点 (基于最近网格的 Gi*)
# ============================================
print("\n[6] 导出矿点级别冷热点...")
from shapely.geometry import Point as ShapelyPoint

# Load split mining points
points_shp = os.path.join(BASE, "矿区标准化分类结果", "赣州矿场点_拆分后.shp")
pts_sf = shapefile.Reader(points_shp, encoding='utf-8')
pts_fields = [f[0] for f in pts_sf.fields[1:]]
print(f"  矿点数: {len(pts_sf.records())}")

# Build grid polygons for point-in-polygon lookup
from shapely.geometry import Polygon as ShapelyPolygon
grid_polys = []
for i in range(n):
    shp = shapes_list[i]
    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    exterior = pts[parts[0]:parts[1]]
    if len(exterior) >= 3:
        grid_polys.append(ShapelyPolygon(exterior))
    else:
        grid_polys.append(None)

# Assign Gi* values to points based on which grid cell they fall in
kz_idx = pts_fields.index('kz')
mc_idx = pts_fields.index('mc')

pts_output = os.path.join(OUTPUT, "矿点_冷热点分析_GiStar.shp")
w2 = shapefile.Writer(pts_output, shapeType=1, encoding='utf-8')
for f in pts_fields:
    w2.field(f, 'C', 254)
w2.field('Gi_ZScore', 'N', 20, 10)
w2.field('Gi_PValue', 'N', 20, 10)
w2.field('hotspot_cl', 'C', 50)

points_gi = []
for idx in range(len(pts_sf.records())):
    rec = pts_sf.record(idx)
    pt_geom = pts_sf.shape(idx).points[0]
    pt = ShapelyPoint(pt_geom)

    # Find containing grid cell
    best_gi_z = 0.0
    best_gi_p = 1.0
    best_cls = '不显著'

    for gi in range(len(grid_polys)):
        if grid_polys[gi] is not None and grid_polys[gi].contains(pt):
            best_gi_z = gi_z[gi]
            best_gi_p = gi_p[gi]
            best_cls = hotspot_class[gi]
            break

    points_gi.append((best_gi_z, best_gi_p, best_cls))
    w2.record(
        *[str(v) for v in rec],
        float(best_gi_z),
        float(best_gi_p),
        str(best_cls)
    )
    w2.point(*pt_geom)

w2.close()
prj_src2 = points_shp.replace('.shp', '.prj')
prj_dst2 = pts_output.replace('.shp', '.prj')
if os.path.exists(prj_src2):
    shutil.copy(prj_src2, prj_dst2)

# Point-level stats
point_gi_z = np.array([p[0] for p in points_gi])
point_cls = [p[2] for p in points_gi]
print(f"  已保存: {pts_output}")
print(f"\n  矿点 Gi* 统计:")
for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    cnt = sum(1 for c in point_cls if c == cls)
    if cnt > 0:
        print(f"    {cls}: {cnt} 个矿点 ({cnt/len(point_cls)*100:.1f}%)")

# ============================================
# 7. 生成分析报告
# ============================================
print("\n[7] 生成分析报告...")

report = f"""============================================================
赣州矿场点 Getis-Ord Gi* 冷热点分析报告
============================================================

数据来源: 赣州矿场点拆分后数据 (511条) + 渔网格网 (3000m × 3000m)
分析方法: Getis-Ord Gi* (空间热点分析)
分析日期: 2026-07-23

------------------------------------------------------------
方法说明
------------------------------------------------------------
Getis-Ord Gi* 统计量用于识别空间数据中的"热点"(高值集聚)
和"冷点"(低值集聚)。与局部莫兰指数(LISA)不同,Gi* 直接
判断一个位置及其周边是否显著高于或低于全局均值。

Gi* > 0 且显著: 该位置为热点,周围矿点密度显著偏高
Gi* < 0 且显著: 该位置为冷点,周围矿点密度显著偏低
Gi* ≈ 0: 无显著空间集聚特征

空间权重: Queen 邻接 (8邻域,含自相关)
显著性分级:
  热点 (Z ≥ 1.96, p ≤ 0.05): 高值显著集聚
  次热点 (Z ≥ 1.65, p ≤ 0.10): 高值较显著集聚
  不显著 (|Z| < 1.65): 无显著空间集聚
  次冷点 (Z ≤ -1.65, p ≤ 0.10): 低值较显著集聚
  冷点 (Z ≤ -1.96, p ≤ 0.05): 低值显著集聚

------------------------------------------------------------
网格级分析结果 (n={n})
------------------------------------------------------------
网格总数: {n}
矿点密度均值: {np.mean(counts):.4f}
矿点密度标准差: {np.std(counts):.4f}
非零网格: {np.sum(counts > 0)}

冷热点分布:
"""
for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    cnt = np.sum(hotspot_class == cls)
    if cnt > 0:
        pct = cnt / n * 100
        report += f"  {cls}: {cnt} 网格 ({pct:.1f}%)\n"

report += f"""
------------------------------------------------------------
矿点级分析结果 (n={len(points_gi)})
------------------------------------------------------------
"""
for cls in ['热点', '次热点', '不显著', '次冷点', '冷点']:
    cnt = sum(1 for c in point_cls if c == cls)
    if cnt > 0:
        pct = cnt / len(point_cls) * 100
        report += f"  {cls}: {cnt} 矿点 ({pct:.1f}%)\n"

report += f"""
------------------------------------------------------------
结果解读
------------------------------------------------------------
Gi* 热点区域对应矿产地高度集聚区,通常与区域性成矿带、
大型矿田的空间范围吻合。赣州作为世界级钨矿产区,热点
应主要分布在大余-于都-崇义钨锡成矿带上。

与局域莫兰指数对比:
- LISA 识别 HH/HL/LH/LL 四种空间关联类型
- Gi* 直接给出热/冷点的统计显著性等级
- 两者互为补充: LISA 看关联模式, Gi* 看集聚强度

------------------------------------------------------------
ArcGIS Pro 可视化建议
------------------------------------------------------------
1. 加载 渔网格网_冷热点分析_GiStar.shp (网格面)
2. 按 hotspot_cl 字段分级设色 (5级):
   - 热点 (Z≥1.96): 深红
   - 次热点 (Z≥1.65): 浅红
   - 不显著: 浅灰
   - 次冷点 (Z≤-1.65): 浅蓝
   - 冷点 (Z≤-1.96): 深蓝
3. 叠加地质图/成矿带图,分析热点的构造控制

------------------------------------------------------------
输出文件清单
------------------------------------------------------------
  渔网格网_冷热点分析_GiStar.shp  -- 网格面 (含 Gi* 结果)
  矿点_冷热点分析_GiStar.shp    -- 矿点 (含对应网格 Gi*)
  冷热点分析报告.txt
"""

report_path = os.path.join(OUTPUT, "冷热点分析报告.txt")
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)
print(f"  报告已保存: {report_path}")

# ============================================
# 汇总
# ============================================
print(f"\n{'='*60}")
print("输出文件清单")
print(f"{'='*60}")
for fname in sorted(os.listdir(OUTPUT)):
    fpath = os.path.join(OUTPUT, fname)
    size = os.path.getsize(fpath)
    if size > 1024 * 1024:
        print(f"  {fname} ({size/1024/1024:.1f} MB)")
    else:
        print(f"  {fname} ({size:,} bytes)")

print(f"\n完毕! 在 ArcGIS Pro 中按 hotspot_cl 字段分级设色可视化。")
