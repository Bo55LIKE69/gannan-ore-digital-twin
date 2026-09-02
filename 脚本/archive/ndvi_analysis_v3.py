# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 v3 —— 修复覆盖缺失

核心修复: 按 WRS-2 path/row 分组选景，确保覆盖赣州全部区域
赣州跨越 Landsat path 120-123, row 41-43，必须从每个 path 选取场景

方法: Landsat C2 L2 生长季中值/均值合成, EPSG:4326 ~30m
"""

import os, sys, json, time
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.features import geometry_mask
import warnings
warnings.filterwarnings('ignore')

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "NDVI分析结果")
os.makedirs(OUTPUT, exist_ok=True)

# ============================================================
# 加载赣州边界
# ============================================================
CITY_GEOJSON = os.path.join(BASE, "赣州市_360700_批量下载", "市级", "赣州市_360700.geojson")
with open(CITY_GEOJSON, 'r', encoding='utf-8') as f:
    city_data = json.load(f)

from shapely.geometry import shape
from shapely.ops import unary_union

city_polys = []
for feat in city_data['features']:
    geom = shape(feat['geometry'])
    city_polys.extend(list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom])
city_geom = unary_union(city_polys)
city_bounds = city_geom.bounds
print(f"赣州范围: {city_bounds[0]:.3f}~{city_bounds[2]:.3f}E, "
      f"{city_bounds[1]:.3f}~{city_bounds[3]:.3f}N")

# 搜索 bbox 略大于城市边界
PAD = 0.15
search_bbox = [city_bounds[0]-PAD, city_bounds[1]-PAD, city_bounds[2]+PAD, city_bounds[3]+PAD]

# 输出网格 (EPSG:4326, ~0.0003° ≈ 30m)
RES = 0.0003
OUT_WIDTH  = int((city_bounds[2] - city_bounds[0]) / RES) + 1
OUT_HEIGHT = int((city_bounds[3] - city_bounds[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(*city_bounds, OUT_WIDTH, OUT_HEIGHT)
NODATA = np.float32(-9999)

print(f"输出网格: {OUT_WIDTH} x {OUT_HEIGHT} ({OUT_WIDTH*OUT_HEIGHT/1e6:.1f}M px)")

# ============================================================
# MPC 连接
# ============================================================
from pystac_client import Client
import planetary_computer as pc

for attempt in range(5):
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        print("MPC 连接成功\n")
        break
    except Exception as e:
        if attempt < 4:
            time.sleep((attempt+1)*15)
        else:
            raise

# ============================================================
# 参数
# ============================================================
YEARS = [1990, 2000, 2010, 2015, 2020, 2024]
YEAR_PLATFORMS = {
    1990: ["landsat-5"],
    2000: ["landsat-5", "landsat-7"],
    2010: ["landsat-5", "landsat-7"],
    2015: ["landsat-8"],
    2020: ["landsat-8"],
    2024: ["landsat-8", "landsat-9"],
}

# Landsat SR 缩放参数
SR_SCALE  = 0.0000275
SR_OFFSET = -0.2

# QA 位掩码
QA_FILL          = 1 << 0
QA_DILATED_CLOUD = 1 << 1
QA_CIRRUS        = 1 << 2
QA_CLOUD         = 1 << 3
QA_CLOUD_SHADOW  = 1 << 4

def is_clear(qa):
    """云 + 云影 + 填充 = 坏像素"""
    return (qa & (QA_DILATED_CLOUD | QA_CLOUD | QA_CLOUD_SHADOW | QA_FILL)) == 0

def ndvi_from_sr(nir, red):
    nir_sr = (nir.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    red_sr = (red.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    return ((nir_sr - red_sr) / (nir_sr + red_sr + 1e-8)).clip(-1, 1)

def search_mpc(bbox, dt, platforms, cc_max, max_items):
    """搜索 Landsat 场景 (带重试)"""
    for attempt in range(3):
        try:
            s = catalog.search(
                collections=["landsat-c2-l2"],
                bbox=bbox, datetime=dt,
                query={"platform": {"in": platforms}, "eo:cloud_cover": {"lt": cc_max}},
                max_items=max_items
            )
            return list(s.items())
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt+1)*8)
            else:
                raise
    return []

def process_scene(item):
    """处理单个 Landsat 场景 → 全网格 NDVI 数组"""
    nir_url = pc.sign(item.assets['nir08'].href)
    red_url = pc.sign(item.assets['red'].href)
    qa_url  = pc.sign(item.assets['qa_pixel'].href) if 'qa_pixel' in item.assets else None

    with rasterio.open(nir_url) as nir_src:
        sc_crs = nir_src.crs

        # 计算场景与搜索区交集
        if sc_crs and sc_crs != CRS.from_epsg(4326):
            sc_b_wgs = transform_bounds(sc_crs, CRS.from_epsg(4326), *nir_src.bounds)
        else:
            sc_b_wgs = nir_src.bounds

        ol = [max(search_bbox[0], sc_b_wgs[0]), max(search_bbox[1], sc_b_wgs[1]),
              min(search_bbox[2], sc_b_wgs[2]), min(search_bbox[3], sc_b_wgs[3])]
        if ol[0] >= ol[2] or ol[1] >= ol[3]:
            return None

        # window 计算
        if sc_crs and sc_crs != CRS.from_epsg(4326):
            ol_proj = transform_bounds(CRS.from_epsg(4326), sc_crs, *ol)
            window = nir_src.window(*ol_proj)
        else:
            window = nir_src.window(ol[0], ol[3], ol[2], ol[1])

        ww, wh = int(window.width), int(window.height)
        max_dim = 4000
        scale = min(1.0, max_dim / max(ww, wh))
        ow, oh = max(10, int(ww*scale)), max(10, int(wh*scale))

        with rasterio.open(red_url) as red_src:
            nir_arr = nir_src.read(1, window=window, out_shape=(oh, ow))
            red_arr = red_src.read(1, window=window, out_shape=(oh, ow))

        # nodata → nan
        for arr, nd in [(nir_arr, nir_src.nodata), (red_arr, red_src.nodata)]:
            if nd is not None:
                arr[arr == nd] = np.nan

        # 云掩膜
        if qa_url:
            with rasterio.open(qa_url) as qa_src:
                qa_arr = qa_src.read(1, window=window, out_shape=(oh, ow))
                mask = is_clear(qa_arr)
                nir_arr = np.where(mask, nir_arr, np.nan)
                red_arr = np.where(mask, red_arr, np.nan)

        ndvi = ndvi_from_sr(nir_arr, red_arr)
        src_tf = nir_src.window_transform(window)
        src_tf = src_tf * src_tf.scale(ww/ow, wh/oh)

    # Reproject 到统一网格
    out = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    reproject(
        source=ndvi, destination=out,
        src_transform=src_tf, src_crs=sc_crs,
        dst_transform=OUT_TRANSFORM, dst_crs=CRS.from_epsg(4326),
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )
    return out

# ============================================================
# 主循环
# ============================================================
for year in YEARS:
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 2*1024*1024:
        print(f"[{year}] 已存在，跳过\n")
        continue
    elif os.path.exists(out_path):
        os.remove(out_path)

    print(f"=" * 60)
    print(f"[{year}] 搜索 Landsat ...")
    platforms = YEAR_PLATFORMS.get(year, ["landsat-8"])

    items = search_mpc(search_bbox, f"{year}-04-01/{year}-10-31", platforms, 50, 300)
    if len(items) < 20:
        print(f"  第1轮仅{len(items)}景，放宽云量至70%...")
        items2 = search_mpc(search_bbox, f"{year}-03-01/{year}-11-30", platforms, 70, 300)
        # 合并去重
        ids = {it.id for it in items}
        for it in items2:
            if it.id not in ids:
                items.append(it)
                ids.add(it.id)

    print(f"  共 {len(items)} 景")

    # ---- 筛选与城市相交的场景，按 path 分组 ----
    path_groups = {}
    for item in items:
        try:
            item_geom = shape(item.geometry) if item.geometry else None
            if not item_geom or not item_geom.intersects(city_geom):
                continue
        except Exception:
            continue
        pp = item.properties.get('landsat:wrs_path', 'unknown')
        path_groups.setdefault(pp, []).append(item)

    print(f"  城市相交: {sum(len(v) for v in path_groups.values())} 景, "
          f"分布在 path {sorted(path_groups.keys())}")

    # ---- 每 path 选云量最低的 12 景 ----
    selected = []
    for pp, grp in path_groups.items():
        grp.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        selected.extend(grp[:12])

    # 去重 + 按云量排序
    seen = set()
    selected = [s for s in selected if not (s.id in seen or seen.add(s.id))]
    selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    selected = selected[:80]

    cloud_info = ", ".join([f"path{p}={c}景" for p, c in
        __import__('collections').Counter(s.properties.get('landsat:wrs_path','?') for s in selected).items()])
    print(f"  选中 {len(selected)} 景 ({cloud_info})")

    # ---- 增量均值合成 ----
    ndvi_sum   = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float64)
    ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)
    n_ok = 0

    for idx, item in enumerate(selected):
        try:
            arr = process_scene(item)
            if arr is None:
                continue
            mask = ~np.isnan(arr)
            ndvi_sum[mask]   += arr[mask].astype(np.float64)
            ndvi_count[mask] += 1
            n_ok += 1
        except Exception as e:
            if idx < 3:
                print(f"  场景[{idx}] 失败: {e}")
            continue
        if (idx+1) % 20 == 0:
            sys.stdout.write(f"\r  处理 {idx+1}/{len(selected)}, 成功 {n_ok}")
            sys.stdout.flush()

    print(f"\r  成功: {n_ok}/{len(selected)}")

    if n_ok == 0:
        print(f"  [{year}] 无有效数据\n")
        continue

    # ---- 计算均值 ----
    valid = ndvi_count > 0
    ndvi = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    ndvi[valid] = (ndvi_sum[valid] / ndvi_count[valid]).astype(np.float32)
    del ndvi_sum

    cover_1 = np.sum(ndvi_count == 1) / valid.sum() * 100
    cover_3 = np.sum(ndvi_count >= 3) / valid.sum() * 100
    print(f"  覆盖: 仅1景={cover_1:.1f}%, ≥3景={cover_3:.1f}%, 均值={ndvi_count[valid].mean():.1f}景")

    # ---- 按城市边界 mask 裁剪 ----
    city_mask = geometry_mask([city_geom], out_shape=(OUT_HEIGHT, OUT_WIDTH),
                              transform=OUT_TRANSFORM, invert=True, all_touched=True)
    ndvi[~city_mask] = np.nan
    n_city = np.sum(city_mask)
    n_valid = np.sum(~np.isnan(ndvi))
    cov_pct = n_valid / n_city * 100 if n_city > 0 else 0

    # 分区域覆盖检查
    mid_col = OUT_WIDTH // 2
    for region, col_slice in [("西半部", slice(0, mid_col)), ("东半部", slice(mid_col, None))]:
        region_mask = city_mask[:, col_slice]
        region_ndvi = ndvi[:, col_slice]
        r_total = np.sum(region_mask)
        r_valid = np.sum(~np.isnan(region_ndvi)) if r_total > 0 else 0
        r_pct = r_valid / r_total * 100 if r_total > 0 else 0
        print(f"    {region}: {r_pct:.1f}%")

    print(f"  城市整体覆盖率: {cov_pct:.1f}% ({n_valid}/{n_city})")

    if cov_pct < 50:
        print(f"  ⚠ 覆盖率偏低，可能云量较大或该年份数据不足")

    # ---- 裁剪输出 ----
    rows, cols = np.where(~np.isnan(ndvi))
    if len(rows) == 0:
        print(f"  [{year}] 裁切后无数据\n")
        continue
    r0, r1, c0, c1 = rows.min(), rows.max()+1, cols.min(), cols.max()+1
    ndvi_crop = ndvi[r0:r1, c0:c1]
    crop_tf   = OUT_TRANSFORM * rasterio.Affine.translation(c0, r0)

    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
        dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
        compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(year=str(year), index='NDVI', method='mean_composite_path_balanced',
                        n_scenes=str(n_ok), coverage_pct=f"{cov_pct:.1f}")

    mb = os.path.getsize(out_path)/1024/1024
    vals = out_data[out_data != NODATA]
    print(f"  保存: {os.path.basename(out_path)} ({mb:.1f}MB)")
    print(f"  NDVI: [{np.min(vals):.4f}, {np.max(vals):.4f}], mean={np.mean(vals):.4f}\n")

# ============================================================
# 统计汇总
# ============================================================
print("=" * 60)
print("NDVI 统计汇总")
print("=" * 60)

rows = []
for year in YEARS:
    fp = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if not os.path.exists(fp):
        continue
    with rasterio.open(fp) as src:
        data = src.read(1)
        v = data[data != NODATA]
        if len(v) == 0:
            continue
        veg_pct = np.sum(v > 0.3) / len(v) * 100
        cov = src.tags().get('coverage_pct', 'N/A')
        rows.append([year, np.mean(v), np.std(v), np.min(v), np.max(v), veg_pct, float(cov)])
        print(f"  {year}: mean={np.mean(v):.4f}, σ={np.std(v):.4f}, "
              f"veg={veg_pct:.1f}%, city_cov={cov}%")

csv = os.path.join(OUTPUT, "NDVI统计汇总.csv")
with open(csv, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%)\n")
    for r in rows:
        f.write(f"{r[0]},{r[1]:.4f},{r[2]:.4f},{r[3]:.4f},{r[4]:.4f},{r[5]:.1f},{r[6]:.1f}\n")

print(f"\n统计表: {csv}")
print("完毕!")
