# -*- coding: utf-8 -*-
"""
赣州稀土矿场空间分布类型分析
步骤：
  1. 从全国矿产地数据中裁剪赣州市范围内的矿点
  2. 计算最临近指数 (NNI)
  3. 计算泰森多边形面积变异系数 (CV)
  4. 计算地理集中指数 (G)
  5. 计算全局莫兰指数 (Global Moran's I)
  6. 计算局域莫兰指数 (Local Moran's I / LISA)

输出：全部结果 shapefile + 统计报告，打包到 空间分布分析结果/
"""

import os, sys, json
import numpy as np
import shapefile
from shapely.geometry import Point, Polygon, box, MultiPolygon
from shapely.ops import unary_union
from shapely.prepared import prep
from scipy.spatial import Voronoi
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 0. 路径与常量
# ============================================
BASE = r"E:\Data\赣州稀土"
CITY_SHP  = os.path.join(BASE, "市级", "赣州市_360700.shp")
NATL_SHP  = os.path.join(BASE, r"【250610】全国矿产地分布数据\原始数据", "全国矿产地分布数据.shp")
OUTPUT    = os.path.join(BASE, "空间分布分析结果")
os.makedirs(OUTPUT, exist_ok=True)

GEO_CRS   = "EPSG:4326"
PROJ_CRS  = "EPSG:4545"       # CGCS2000 3-degree Gauss-Kruger CM 114E
FALLBACK  = "EPSG:32650"      # WGS84 UTM 50N
GRID_SIZE = 3000              # 渔网网格 3km

# ============================================
# 1. 加载赣州边界
# ============================================
print("=" * 60)
print("赣州稀土矿场空间分布类型分析")
print("=" * 60)
print("\n[0] 加载赣州边界...")

city_sf = shapefile.Reader(CITY_SHP, encoding='gbk')
# 构建 shapely 几何
city_parts = []
for shp in city_sf.shapes():
    parts = list(shp.parts) + [len(shp.points)]
    for i in range(len(parts) - 1):
        ring = shp.points[parts[i]:parts[i+1]]
        if ring:
            city_parts.append(Polygon(ring))

city_geom = MultiPolygon(city_parts) if len(city_parts) > 1 else city_parts[0]
city_geom = city_geom.buffer(0)  # 修复无效几何

minx, miny, maxx, maxy = city_geom.bounds
print(f"  赣州边界范围: lon=[{minx:.4f}, {maxx:.4f}], lat=[{miny:.4f}, {maxy:.4f}]")
print(f"  几何类型: {city_geom.geom_type}")

# 预估面积 (WGS84球面简化)
city_area_deg = city_geom.area
print(f"  大约面积: ~{city_area_deg * 111 * 111 * np.cos(np.radians((miny+maxy)/2)):.0f} km2")

# ============================================
# 2. 从全国数据裁剪赣州矿点
# ============================================
print("\n[1] 从全国矿产地数据中筛选赣州矿点...")

import geopandas as gpd

natl_gdf = gpd.read_file(NATL_SHP, encoding='gbk')
total_natl = len(natl_gdf)
print(f"  全国矿产地总数: {total_natl}")

# 空间筛选：赣州范围内的点
natl_gdf = natl_gdf[natl_gdf.geometry.within(city_geom) | natl_gdf.geometry.intersects(city_geom)]
gz_gdf = natl_gdf.copy()
n_points = len(gz_gdf)
print(f"  赣州范围内矿点: {n_points} 个")

if n_points < 3:
    print(f"\n错误: 赣州范围内仅 {n_points} 个矿点，无法进行空间分布分析")
    sys.exit(1)

gz_records = gz_gdf.to_dict('records')
coords_lonlat = np.array([[g.x, g.y] for g in gz_gdf.geometry])
natl_fields = list(gz_gdf.columns)

# 保存裁剪后的矿点
print("  保存赣州矿场点 shapefile...")
import shutil
gz_gdf.to_file(os.path.join(OUTPUT, "赣州矿场点_裁剪后.shp"), encoding='gbk')

# 统计矿种类型
if 'kz' in gz_gdf.columns:
    mineral_counts = gz_gdf['kz'].value_counts()
else:
    mineral_counts = {}
print("  矿种类型分布 (前10):")
for mt, cnt in mineral_counts.head(10).items():
    print(f"    {mt}: {cnt}")

pass  # 矿种统计已在上面输出

# ============================================
# 3. 投影转换 (WGS84 → 投影坐标)
# ============================================
print("\n[2] 坐标投影转换...")

# 使用 pyproj 进行投影转换
try:
    from pyproj import Transformer
    transformer = Transformer.from_crs(GEO_CRS, PROJ_CRS, always_xy=True)
    coords_proj = np.array([transformer.transform(lon, lat) for lon, lat in coords_lonlat])

    # 投影边界
    bbox_corners = [
        transformer.transform(lon, lat)
        for lon, lat in [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    ]
    proj_crs_used = PROJ_CRS
    print(f"  使用 {PROJ_CRS} 投影")
except Exception as e:
    print(f"  {PROJ_CRS} 不可用: {e}")
    print(f"  回退到 {FALLBACK}")
    from pyproj import Transformer
    transformer = Transformer.from_crs(GEO_CRS, FALLBACK, always_xy=True)
    coords_proj = np.array([transformer.transform(lon, lat) for lon, lat in coords_lonlat])
    bbox_corners = [
        transformer.transform(lon, lat)
        for lon, lat in [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    ]
    proj_crs_used = FALLBACK

# 投影后的边界多边形
proj_xs = [c[0] for c in bbox_corners]
proj_ys = [c[1] for c in bbox_corners]
minx_p, miny_p = min(proj_xs), min(proj_ys)
maxx_p, maxy_p = max(proj_xs), max(proj_ys)

# 投影赣州边界（用更精细的采样点）
def project_polygon(geom, trans):
    """投影 shapely 几何对象"""
    if geom.geom_type == 'Polygon':
        ext_coords = [trans.transform(x, y) for x, y in geom.exterior.coords]
        int_rings = []
        for interior in geom.interiors:
            int_rings.append([trans.transform(x, y) for x, y in interior.coords])
        return Polygon(ext_coords, int_rings)
    elif geom.geom_type == 'MultiPolygon':
        return MultiPolygon([project_polygon(p, trans) for p in geom.geoms])
    return geom

city_geom_proj = project_polygon(city_geom, transformer)

# 计算投影面积
area_m2 = city_geom_proj.area
area_km2 = area_m2 / 1e6
print(f"  赣州面积: {area_km2:.2f} km2")
print(f"  矿场密度: {n_points / area_km2:.4f} 个/km2")

# ============================================
# 4. 最临近指数 (NNI)
# ============================================
print("\n[3] 最临近指数 (Nearest Neighbor Index)...")

from sklearn.neighbors import NearestNeighbors

n = len(coords_proj)
nn_model = NearestNeighbors(n_neighbors=2, metric='euclidean')
nn_model.fit(coords_proj)
distances, _ = nn_model.kneighbors(coords_proj)
nearest_dists = distances[:, 1]

d_obs = np.mean(nearest_dists)
d_exp = 1.0 / (2.0 * np.sqrt(n / area_m2))
NNI = d_obs / d_exp
SE = 0.26136 / np.sqrt(n * (n / area_m2))
Z_nni = (d_obs - d_exp) / SE
p_nni = 2 * stats.norm.sf(abs(Z_nni))

print(f"  d_obs = {d_obs:.2f} m")
print(f"  d_exp = {d_exp:.2f} m")
print(f"  R = {NNI:.6f}")
print(f"  Z = {Z_nni:.4f}, p = {p_nni:.6f}")
print(f"  类型: {'集聚' if NNI < 1 else '均匀' if NNI > 1 else '随机'}分布")

# 导出带最近邻距离的点
print("  导出最近邻分析结果...")
nn_gdf = gz_gdf.copy()
nn_gdf['nearest_d'] = nearest_dists
nn_gdf['NNI_R'] = NNI
nn_gdf.to_file(os.path.join(OUTPUT, "矿场点_最近邻分析.shp"), encoding='gbk')

# ============================================
# 5. 泰森多边形面积变异系数 (CV)
# ============================================
print("\n[4] 泰森多边形面积变异系数...")

# 扩展点集以避免边界Voronoi多边形无限大
pad = (maxx_p - minx_p + maxy_p - miny_p) * 0.5
boundary_coords = np.array([
    [minx_p - pad, miny_p - pad],
    [maxx_p + pad, miny_p - pad],
    [maxx_p + pad, maxy_p + pad],
    [minx_p - pad, maxy_p + pad],
    [minx_p - pad, miny_p - pad],
])

# 添加角点和边界中点作为虚拟点
buffer_pts = [
    (minx_p - pad, miny_p - pad), (maxx_p + pad, miny_p - pad),
    (maxx_p + pad, maxy_p + pad), (minx_p - pad, maxy_p + pad),
    (minx_p + (maxx_p - minx_p) / 2, miny_p - pad * 0.7),
    (minx_p + (maxx_p - minx_p) / 2, maxy_p + pad * 0.7),
    (minx_p - pad * 0.7, miny_p + (maxy_p - miny_p) / 2),
    (maxx_p + pad * 0.7, miny_p + (maxy_p - miny_p) / 2),
]

extended_coords = np.vstack([coords_proj, buffer_pts])

vor = Voronoi(extended_coords)
boundary_poly = city_geom_proj

valid_polys = []
valid_areas = []
for region_idx in vor.regions:
    if not region_idx or -1 in region_idx:
        continue
    poly_coords = [vor.vertices[i] for i in region_idx]
    try:
        poly = Polygon(poly_coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        clipped = poly.intersection(boundary_poly)
        if not clipped.is_empty and clipped.area > 100:  # 过滤极小碎片
            valid_polys.append(clipped)
            valid_areas.append(clipped.area)
    except Exception:
        continue

areas = np.array(valid_areas)
mean_area = np.mean(areas)
std_area = np.std(areas, ddof=1)
CV = (std_area / mean_area) * 100

print(f"  有效泰森多边形: {len(valid_polys)} 个")
print(f"  平均面积: {mean_area/1e6:.4f} km2")
print(f"  标准差: {std_area/1e6:.4f} km2")
print(f"  CV = {CV:.2f}%")
print(f"  类型: {'集聚' if CV > 64 else '随机' if CV > 33 else '均匀'}分布")

# 导出泰森多边形
print("  导出泰森多边形...")

# 转回地理坐标
inv_transformer = Transformer.from_crs(proj_crs_used, GEO_CRS, always_xy=True)

def project_shapely(geom, trans):
    """将投影后几何转回WGS84"""
    if geom.geom_type == 'Polygon':
        ext = [trans.transform(x, y) for x, y in geom.exterior.coords]
        ints = [[trans.transform(x, y) for x, y in r.coords] for r in geom.interiors]
        return Polygon(ext, ints)
    elif geom.geom_type == 'MultiPolygon':
        return MultiPolygon([project_shapely(p, trans) for p in geom.geoms])
    else:
        return geom

thiessen_geog = [project_shapely(p, inv_transformer) for p in valid_polys]

thiessen_gdf = gpd.GeoDataFrame({
    'area_km2': areas / 1e6,
    'CV_perc': CV
}, geometry=thiessen_geog, crs=GEO_CRS)
thiessen_gdf.to_file(os.path.join(OUTPUT, "泰森多边形.shp"), encoding='gbk')

# ============================================
# 6. 地理集中指数 (G)
# ============================================
print("\n[5] 地理集中指数 (Geographic Concentration Index)...")

# 创建渔网网格
cols = int(np.ceil((maxx_p - minx_p) / GRID_SIZE))
rows = int(np.ceil((maxy_p - miny_p) / GRID_SIZE))
width = (maxx_p - minx_p) / cols
height = (maxy_p - miny_p) / rows

# 网格计数
cell_counts = {}
for x, y in coords_proj:
    col = int((x - minx_p) / width)
    row = int((y - miny_p) / height)
    col = min(col, cols - 1)
    row = min(row, rows - 1)
    key = (row, col)
    cell_counts[key] = cell_counts.get(key, 0) + 1

# 构建网格（只保留与边界相交的）
grid_cells = []
for row in range(rows):
    for col in range(cols):
        x0 = minx_p + col * width
        y0 = miny_p + row * height
        cell_box = box(x0, y0, x0 + width, y0 + height)
        if cell_box.intersects(city_geom_proj):
            cnt = cell_counts.get((row, col), 0)
            grid_cells.append({
                'row': row, 'col': col, 'count': cnt,
                'geometry': cell_box
            })

# 计算 G 指数
counts = np.array([c['count'] for c in grid_cells])
X = counts.sum()
if X > 0:
    G = 100 * np.sqrt(np.sum((counts / X) ** 2))
    G_uniform = 100 * np.sqrt(1.0 / len(grid_cells))
else:
    G = G_uniform = 0

print(f"  有效网格数: {len(grid_cells)}")
print(f"  最大网格内矿点数: {counts.max()}")
print(f"  G = {G:.4f}")
print(f"  G_uniform = {G_uniform:.4f}")
print(f"  判断: {'集中分布' if G > G_uniform else '接近均匀分布'}")

# 导出渔网
print("  导出渔网密度图...")
inv_trans = Transformer.from_crs(proj_crs_used, GEO_CRS, always_xy=True)

grid_geoms_wgs84 = []
grid_rows, grid_cols, grid_ratios = [], [], []
for cell in grid_cells:
    ext = [inv_trans.transform(x, y) for x, y in cell['geometry'].exterior.coords]
    grid_geoms_wgs84.append(Polygon(ext))
    grid_rows.append(cell['row'])
    grid_cols.append(cell['col'])
    grid_ratios.append(cell['count'] / X if X > 0 else 0)

grid_gdf = gpd.GeoDataFrame({
    'cell_row': grid_rows,
    'cell_col': grid_cols,
    'count': counts,
    'ratio': grid_ratios
}, geometry=grid_geoms_wgs84, crs=GEO_CRS)
grid_gdf.to_file(os.path.join(OUTPUT, "渔网格网_矿点密度.shp"), encoding='gbk')

# 构建网格值数组用于莫兰指数
vals = counts.astype(float)
grid_ids = list(range(len(grid_cells)))

# 网格地理坐标（质心）用于空间权重
grid_centroids = np.array([(c['geometry'].centroid.x, c['geometry'].centroid.y) for c in grid_cells])

# 初始化变量
moran_EI = 0.0
moran_I_val = 0.0
moran_z_val = 0.0
moran_p_val = 1.0
w_for_lisa = None

# ============================================
# 7. 全局莫兰指数 (Global Moran's I)
# ============================================
print("\n[6] 全局莫兰指数 (Global Moran's I)...")

from esda.moran import Moran
import libpysal
from libpysal.weights import Queen, KNN, DistanceBand

# 尝试构建空间权重矩阵
# 先用网格质心构建 KNN 权重
n_grids = len(grid_cells)
try:
    pts_data = libpysal.io.geopandas_to_pd(None)
except Exception:
    pass

# 直接用坐标构建 KNN 权重
k = min(8, n_grids - 1)
if k < 1:
    k = 1

grid_pts = [tuple(c) for c in grid_centroids]
try:
    w_knn = KNN.from_array(grid_centroids, k=k)
    print(f"  使用 KNN (k={k}) 空间权重矩阵")
except Exception as e:
    print(f"  KNN 权重构建失败: {e}")
    w_knn = None

if w_knn is not None and n_grids > 1:
    moran = Moran(vals, w_knn, permutations=999)
    print(f"  Moran's I = {moran.I:.6f}")
    moran_EI = moran.EI
    print(f"  E[I] = {moran_EI:.6f}")
    print(f"  Z-score = {moran.z_sim:.4f}")
    print(f"  p-value = {moran.p_sim:.6f}")
    print(f"  判断: {'显著集聚' if moran.p_sim < 0.05 and moran.I > moran.EI else '显著分散' if moran.p_sim < 0.05 else '不显著(随机)'}")

    moran_I_val = moran.I
    moran_z_val = moran.z_sim
    moran_p_val = moran.p_sim
    w_for_lisa = w_knn
else:
    print("  无法计算全局莫兰指数")
    moran_I_val = moran_z_val = moran_p_val = 0
    w_for_lisa = None

# ============================================
# 8. 局域莫兰指数 (LISA)
# ============================================
print("\n[7] 局域莫兰指数 (Local Moran's I / LISA)...")

if w_for_lisa is not None and n_grids > 2:
    from esda.moran import Moran_Local

    lisa = Moran_Local(vals, w_for_lisa, permutations=999)

    # LISA 分类
    vals_std = (vals - vals.mean()) / vals.std() if vals.std() > 0 else np.zeros_like(vals)
    # 计算空间滞后（加权平均）
    w_sparse = w_for_lisa.sparse
    lag_vals = np.array([
        w_sparse[i].dot(vals)[0] / w_sparse[i].sum() if w_sparse[i].sum() > 0 else 0
        for i in range(n_grids)
    ])
    lag_std = np.zeros_like(lag_vals)
    if vals.std() > 0:
        lag_std = (lag_vals - vals.mean()) / vals.std()

    sig_level = 0.05
    cluster_type = np.full(n_grids, '不显著 (NS)', dtype=object)
    for i in range(n_grids):
        if lisa.p_sim[i] > sig_level:
            cluster_type[i] = '不显著 (NS)'
        elif vals_std[i] > 0 and lag_std[i] > 0:
            cluster_type[i] = '高-高集聚 (HH)'
        elif vals_std[i] < 0 and lag_std[i] < 0:
            cluster_type[i] = '低-低集聚 (LL)'
        elif vals_std[i] > 0 and lag_std[i] < 0:
            cluster_type[i] = '高-低集聚 (HL)'
        elif vals_std[i] < 0 and lag_std[i] > 0:
            cluster_type[i] = '低-高集聚 (LH)'

    # 统计
    unique, cnts = np.unique(cluster_type, return_counts=True)
    print("  LISA 聚类统计:")
    for u, c in zip(unique, cnts):
        print(f"    {u}: {c} 个网格")

    # 导出 LISA
    print("  导出 LISA 结果...")
    lisa_geoms = []
    for cell in grid_cells:
        ext = [inv_trans.transform(x, y) for x, y in cell['geometry'].exterior.coords]
        lisa_geoms.append(Polygon(ext))

    lisa_gdf = gpd.GeoDataFrame({
        'cell_row': [c['row'] for c in grid_cells],
        'cell_col': [c['col'] for c in grid_cells],
        'count': [c['count'] for c in grid_cells],
        'local_I': lisa.Is,
        'p_value': lisa.p_sim,
        'z_std': vals_std,
        'lag_std': lag_std,
        'cluster': cluster_type
    }, geometry=lisa_geoms, crs=GEO_CRS)
    lisa_gdf.to_file(os.path.join(OUTPUT, "局域莫兰指数_LISA.shp"), encoding='gbk')
else:
    print("  网格数不足，无法计算 LISA")
    lisa_available = False

# ============================================
# 9. 汇总报告
# ============================================
print("\n" + "=" * 60)
print("结果汇总")
print("=" * 60)

report = f"""
============================================================
      赣州稀土矿场空间分布类型分析报告
============================================================

数据概况:
  - 全国矿产地总数: {total_natl}
  - 赣州范围内矿点数: {n_points}
  - 赣州市面积: {area_km2:.2f} km2
  - 平均密度: {n_points / area_km2:.4f} 个/km2
  - 坐标系: WGS84 → {proj_crs_used} (投影)
  - 网格尺寸: {GRID_SIZE}m × {GRID_SIZE}m

------------------------------------------------------------
1. 最临近指数 (Nearest Neighbor Index)
------------------------------------------------------------
  观测平均最近邻距离  d_obs = {d_obs:.2f} m
  理论最近邻距离      d_exp = {d_exp:.2f} m
  最临近指数          R = {NNI:.6f}
  Z-score             Z = {Z_nni:.4f}
  p-value             p = {p_nni:.6f}
  分布类型: {'集聚分布' if NNI < 1 else '均匀分布' if NNI > 1 else '随机分布'}

  R < 1 集聚, R = 1 随机, R > 1 均匀

------------------------------------------------------------
2. 泰森多边形面积变异系数
------------------------------------------------------------
  有效泰森多边形数:  {len(valid_polys)}
  平均面积:          {mean_area/1e6:.4f} km2
  面积标准差:        {std_area/1e6:.4f} km2
  变异系数            CV = {CV:.2f}%
  分布类型: {'集聚分布 (CV>64%)' if CV > 64 else '随机分布 (33%<CV<64%)' if CV > 33 else '均匀分布 (CV<33%)'}

------------------------------------------------------------
3. 地理集中指数
------------------------------------------------------------
  有效网格数:          {len(grid_cells)}
  最大网格矿点数:      {counts.max()}
  地理集中指数          G = {G:.4f}
  均匀分布期望值        G = {G_uniform:.4f}
  判断: {'集中分布 (G > G_uniform)' if G > G_uniform else '接近均匀分布'}

------------------------------------------------------------
4. 全局莫兰指数 (Global Moran's I)
------------------------------------------------------------
  Moran's I = {moran_I_val:.6f}
  E[I] = {moran_EI:.6f}
  Z-score = {moran_z_val:.4f}
  p-value = {moran_p_val:.6f}
  判断: {'显著空间正相关 (集聚)' if moran_p_val < 0.05 and moran_I_val > 0 else
         '显著空间负相关 (分散)' if moran_p_val < 0.05 else '不显著 (趋向随机)'}

------------------------------------------------------------
5. 局域莫兰指数 (LISA)
------------------------------------------------------------"""

if w_for_lisa is not None and n_grids > 2:
    for u, c in zip(unique, cnts):
        report += f"\n    {u}: {c} 个"

report += f"""

------------------------------------------------------------
综合结论:
  R = {NNI:.4f} ({'<' if NNI < 1 else '>' if NNI > 1 else '='} 1)
  CV = {CV:.1f}% ({'集聚' if CV > 64 else '随机' if CV > 33 else '均匀'})
  G = {G:.2f} (vs {G_uniform:.2f})
  Moran I = {moran_I_val:.4f} (p={moran_p_val:.4f})

  赣州稀土矿场整体呈{'集聚' if NNI < 1 else '均匀' if NNI > 1 else '随机'}分布格局。
============================================================
"""

print(report)

with open(os.path.join(OUTPUT, "空间分布分析报告.txt"), 'w', encoding='utf-8') as f:
    f.write(report)

# 统计结果 CSV (手动写避免pandas兼容问题)
csv_path = os.path.join(OUTPUT, "统计结果汇总.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("指标,数值\n")
    f.write(f"矿点总数,{n_points}\n")
    f.write(f"赣州面积(km2),{area_km2:.4f}\n")
    f.write(f"矿点密度(个/km2),{n_points/area_km2:.6f}\n")
    f.write(f"最临近指数_R,{NNI:.6f}\n")
    f.write(f"NNI_Z-score,{Z_nni:.4f}\n")
    f.write(f"NNI_p-value,{p_nni:.6f}\n")
    f.write(f"泰森多边形_CV(%),{CV:.2f}\n")
    f.write(f"泰森多边形数量,{len(valid_polys)}\n")
    f.write(f"地理集中指数_G,{G:.4f}\n")
    f.write(f"均匀分布_G,{G_uniform:.4f}\n")
    f.write(f"网格数,{len(grid_cells)}\n")
    f.write(f"全局Moran_I,{moran_I_val:.6f}\n")
    f.write(f"Moran_Z-score,{moran_z_val:.4f}\n")
    f.write(f"Moran_p-value,{moran_p_val:.6f}\n")

print(f"\n所有输出文件: {OUTPUT}/")
for f in sorted(os.listdir(OUTPUT)):
    fpath = os.path.join(OUTPUT, f)
    size = os.path.getsize(fpath)
    print(f"  {f} ({size:,} bytes)")

print("\n完毕! 可用 ArcGIS Pro 打开输出目录中的 .shp 文件。")
