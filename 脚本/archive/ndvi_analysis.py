# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 (1990, 2000, 2010, 2015, 2020, 2024)
数据源: Microsoft Planetary Computer → Landsat Collection 2 Level-2
方法: 年度生长季中值合成 → 按城市边界 mask → EPSG:4326 输出

修复:
  1. 按场景 geometry 与城市 polygon 交集筛选 Landsat 影像
  2. 定义统一 EPSG:4326 输出网格，各场景 reproject 对齐后合成
  3. 按实际多边形边界 mask 裁剪（不规则裁剪）
"""

import os, sys, json
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, reproject, Resampling, calculate_default_transform
from rasterio.features import geometry_mask
import warnings
warnings.filterwarnings('ignore')

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "NDVI分析结果")
os.makedirs(OUTPUT, exist_ok=True)

# ============================================
# 加载赣州边界
# ============================================
CITY_GEOJSON = os.path.join(BASE, "市级", "赣州市_360700.geojson")
with open(CITY_GEOJSON, 'r', encoding='utf-8') as f:
    city_data = json.load(f)

from shapely.geometry import shape, box, Polygon as ShapelyPolygon
from shapely.ops import unary_union

features = city_data['features']
city_polys = []
for feat in features:
    geom = shape(feat['geometry'])
    if geom.geom_type == 'MultiPolygon':
        city_polys.extend(list(geom.geoms))
    else:
        city_polys.append(geom)

city_geom = unary_union(city_polys)
city_bounds = city_geom.bounds
print(f"赣州边界: lon=[{city_bounds[0]:.4f}, {city_bounds[2]:.4f}], "
      f"lat=[{city_bounds[1]:.4f}, {city_bounds[3]:.4f}]")

# 扩展边界用于 STAC 搜索 (度)
PAD = 0.1
search_bbox = [city_bounds[0]-PAD, city_bounds[1]-PAD, city_bounds[2]+PAD, city_bounds[3]+PAD]

# 输出网格参数 (EPSG:4326)
RES = 0.0003  # ~30m
OUT_WIDTH = int((city_bounds[2] - city_bounds[0]) / RES) + 1
OUT_HEIGHT = int((city_bounds[3] - city_bounds[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(city_bounds[0], city_bounds[1], city_bounds[2], city_bounds[3],
                            OUT_WIDTH, OUT_HEIGHT)
NODATA = -9999

YEARS = [1990, 2000, 2010, 2015, 2020, 2024]

# ============================================
# 连接 MPC
# ============================================
print("\n" + "=" * 60)
print("赣州多年 NDVI 计算 (Landsat C2 L2, 生长季中值合成)")
print("=" * 60)

from pystac_client import Client
import planetary_computer as pc
import time

# 带重试连接 MPC
for attempt in range(5):
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        break
    except Exception as e:
        if attempt < 4:
            wait = (attempt + 1) * 15
            print(f"  MPC connection failed (attempt {attempt+1}/5): {e}")
            print(f"  Waiting {wait}s...")
            time.sleep(wait)
        else:
            raise

YEAR_PLATFORMS = {
    1990: ["landsat-5"],
    2000: ["landsat-5", "landsat-7"],
    2010: ["landsat-5", "landsat-7"],
    2015: ["landsat-8"],
    2020: ["landsat-8"],
    2024: ["landsat-8", "landsat-9"],
}

NIR_KEY = 'nir08'
RED_KEY = 'red'
QA_KEY  = 'qa_pixel'
SR_SCALE = 0.0000275
SR_OFFSET = -0.2

QA_DILATED_CLOUD = 1 << 1
QA_CIRRUS = 1 << 2
QA_CLOUD = 1 << 3
QA_CLOUD_SHADOW = 1 << 4

def is_clear(qa_band):
    cloud_mask = QA_DILATED_CLOUD | QA_CIRRUS | QA_CLOUD | QA_CLOUD_SHADOW
    return (qa_band & cloud_mask) == 0

def ndvi_from_sr(nir, red):
    nir = (nir.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    red = (red.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    ndvi = (nir - red) / (nir + red + 1e-8)
    return ndvi.clip(-1, 1)

# ============================================
# 辅助：带重试的 MPC 搜索
# ============================================
def search_with_retry(catalog, bbox, datetime_str, query, max_items, max_retries=3):
    for attempt in range(max_retries):
        try:
            search = catalog.search(
                collections=["landsat-c2-l2"],
                bbox=bbox,
                datetime=datetime_str,
                query=query,
                max_items=max_items
            )
            return list(search.items())
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 10
                print(f"  MPC query failed (attempt {attempt+1}/{max_retries}): {e}")
                print(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise

# ============================================
# 主循环：每年计算 NDVI
# ============================================
for year in YEARS:
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path):
        if os.path.getsize(out_path) > 1024 * 1024:
            print(f"\n[{year}] Output exists, skipping")
            continue
        else:
            print(f"\n[{year}] Output too small, reprocessing...")
            os.remove(out_path)

    print(f"\n{'='*60}")
    print(f"[{year}] Searching Landsat scenes...")
    print(f"{'='*60}")

    platforms = YEAR_PLATFORMS.get(year, ["landsat-8"])

    try:
        items = search_with_retry(
            catalog, search_bbox,
            f"{year}-06-01/{year}-09-30",
            {"platform": {"in": platforms}, "eo:cloud_cover": {"lt": 30}},
            max_items=100
        )
    except Exception as e:
        print(f"  Search failed: {e}")
        continue

    if len(items) == 0:
        try:
            items = search_with_retry(
                catalog, search_bbox,
                f"{year}-05-01/{year}-10-31",
                {"platform": {"in": platforms}, "eo:cloud_cover": {"lt": 60}},
                max_items=100
            )
        except Exception as e:
            print(f"  Search failed: {e}")
            continue

    # ---- 关键修复: 筛选与城市 polygon 有交集的场景 ----
    valid_items = []
    skipped_geom = 0
    for item in items:
        try:
            item_geom = shape(item.geometry) if item.geometry else None
            if item_geom is None:
                continue
            if item_geom.intersects(city_geom):
                valid_items.append(item)
            else:
                skipped_geom += 1
        except Exception:
            # 如果 geometry 解析失败，保守保留
            valid_items.append(item)

    print(f"  搜索到 {len(items)} 景，与城市有交集: {len(valid_items)} 景 (跳过 {skipped_geom} 景)")

    if len(valid_items) == 0:
        print(f"  {year} 年无可用数据，跳过")
        continue

    # 按云量排序，取最佳30景
    valid_items.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    valid_items = valid_items[:20]
    first_platform = valid_items[0].properties.get('platform', platforms[0])
    print(f"  选取最佳 {len(valid_items)} 景，平台: {first_platform}")

    # ---- 处理每景 ----
    ndvi_stack = []
    n_processed = 0

    for idx, item in enumerate(valid_items):
        try:
            if NIR_KEY not in item.assets or RED_KEY not in item.assets:
                continue

            nir_url = pc.sign(item.assets[NIR_KEY].href)
            red_url = pc.sign(item.assets[RED_KEY].href)
            qa_url = pc.sign(item.assets[QA_KEY].href) if QA_KEY in item.assets else None

            with rasterio.open(nir_url) as nir_src:
                scene_crs = nir_src.crs

                # 在 WGS84 下计算城市 bbox 与场景 footprint 的交集
                # 将场景 bounds 转到 WGS84
                if scene_crs and scene_crs != CRS.from_epsg(4326):
                    scene_bounds_wgs84 = transform_bounds(scene_crs, CRS.from_epsg(4326),
                                                          *nir_src.bounds)
                else:
                    scene_bounds_wgs84 = nir_src.bounds

                # 交集
                overlap_lon_min = max(search_bbox[0], scene_bounds_wgs84[0])
                overlap_lat_min = max(search_bbox[1], scene_bounds_wgs84[1])
                overlap_lon_max = min(search_bbox[2], scene_bounds_wgs84[2])
                overlap_lat_max = min(search_bbox[3], scene_bounds_wgs84[3])

                if overlap_lon_min >= overlap_lon_max or overlap_lat_min >= overlap_lat_max:
                    continue

                # 将交集转回场景 CRS 再计算 window
                if scene_crs and scene_crs != CRS.from_epsg(4326):
                    overlap_proj = transform_bounds(
                        CRS.from_epsg(4326), scene_crs,
                        overlap_lon_min, overlap_lat_min,
                        overlap_lon_max, overlap_lat_max
                    )
                    window = nir_src.window(*overlap_proj)
                else:
                    window = nir_src.window(
                        overlap_lon_min, overlap_lat_max,
                        overlap_lon_max, overlap_lat_min
                    )

                # 限制输出大小
                win_w = int(window.width)
                win_h = int(window.height)
                max_dim = 3000
                if max(win_w, win_h) > max_dim:
                    scale = max_dim / max(win_w, win_h)
                    out_w, out_h = int(win_w * scale), int(win_h * scale)
                else:
                    out_w, out_h = win_w, win_h

                if out_w < 10 or out_h < 10:
                    continue

                with rasterio.open(red_url) as red_src:
                    nir_data = nir_src.read(1, window=window, out_shape=(out_h, out_w))
                    red_data = red_src.read(1, window=window, out_shape=(out_h, out_w))

                nir_nodata = nir_src.nodata
                red_nodata = red_src.nodata
                if nir_nodata is not None:
                    nir_data = np.where(nir_data == nir_nodata, np.nan, nir_data)
                if red_nodata is not None:
                    red_data = np.where(red_data == red_nodata, np.nan, red_data)

                # 云掩膜
                if qa_url:
                    with rasterio.open(qa_url) as qa_src:
                        qa_data = qa_src.read(1, window=window, out_shape=(out_h, out_w))
                        clear = is_clear(qa_data)
                        nir_data = np.where(clear, nir_data, np.nan)
                        red_data = np.where(clear, red_data, np.nan)

                # 计算 NDVI
                ndvi = ndvi_from_sr(nir_data, red_data)

                # 源数据 transform (用于后续 reproject)
                src_transform = nir_src.window_transform(window)
                # 重新计算 out_shape 对应的 transform
                src_transform = src_transform * src_transform.scale(
                    win_w / out_w, win_h / out_h
                )

            # ---- Reproject 到统一 EPSG:4326 网格 ----
            ndvi_wgs84 = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
            reproject(
                source=ndvi,
                destination=ndvi_wgs84,
                src_transform=src_transform,
                src_crs=scene_crs,
                dst_transform=OUT_TRANSFORM,
                dst_crs=CRS.from_epsg(4326),
                src_nodata=np.nan,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear
            )

            ndvi_stack.append(ndvi_wgs84)
            n_processed += 1

        except Exception as e:
            if idx < 5:
                print(f"    场景 {idx} 处理失败: {e}")
            continue

        if (idx + 1) % 10 == 0:
            sys.stdout.write(f"\r  处理中: {idx+1}/{len(valid_items)}, 成功: {n_processed}")
            sys.stdout.flush()

    print(f"\r  成功处理: {n_processed}/{len(valid_items)} 景")

    if len(ndvi_stack) == 0:
        print(f"  {year} 年无有效数据")
        continue

    # ---- 增量均值合成 (低内存) ----
    print(f"  Mean composite ({len(ndvi_stack)} scenes, incremental)...")
    ndvi_sum = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float64)
    ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)

    for i, arr in enumerate(ndvi_stack):
        mask = ~np.isnan(arr)
        ndvi_sum[mask] += arr[mask].astype(np.float64)
        ndvi_count[mask] += 1
        if (i + 1) % 10 == 0:
            print(f"    accumulated {i+1}/{len(ndvi_stack)}")

    valid = ndvi_count > 0
    ndvi_mean = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    ndvi_mean[valid] = (ndvi_sum[valid] / ndvi_count[valid]).astype(np.float32)
    ndvi_median = ndvi_mean  # 统一变量名供后续使用
    del ndvi_sum, ndvi_count

    # ---- 按城市多边形 mask 裁剪 ----
    print(f"  多边形 mask 裁剪...")
    city_mask = geometry_mask(
        [city_geom],
        out_shape=(OUT_HEIGHT, OUT_WIDTH),
        transform=OUT_TRANSFORM,
        invert=True,
        all_touched=True
    )

    ndvi_median[~city_mask] = np.nan
    n_city_pixels = np.sum(city_mask)
    n_valid = np.sum(~np.isnan(ndvi_median))

    print(f"  多边形内像素: {n_city_pixels}, 有效 NDVI: {n_valid} "
          f"({n_valid/n_city_pixels*100:.1f}%)" if n_city_pixels > 0 else "  多边形内无像素!")

    if n_valid == 0:
        print(f"  {year} 年城市范围内无有效 NDVI 数据")
        continue

    # ---- Crop 到实际有效范围 ----
    rows, cols = np.where(~np.isnan(ndvi_median))
    r_min, r_max = rows.min(), rows.max() + 1
    c_min, c_max = cols.min(), cols.max() + 1
    ndvi_cropped = ndvi_median[r_min:r_max, c_min:c_max]
    cropped_transform = OUT_TRANSFORM * rasterio.Affine.translation(c_min, r_min)

    # ---- 导出 ----
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")

    with rasterio.open(
        out_path, 'w',
        driver='GTiff',
        height=ndvi_cropped.shape[0],
        width=ndvi_cropped.shape[1],
        count=1,
        dtype='float32',
        crs=CRS.from_epsg(4326),
        transform=cropped_transform,
        compress='lzw',
        nodata=NODATA,
        tiled=True,
        blockxsize=256,
        blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_cropped), NODATA, ndvi_cropped).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(
            year=str(year),
            satellite=first_platform,
            index='NDVI',
            method='median_composite_growing_season_masked',
            n_scenes=str(n_processed),
            source='Landsat_C2_L2_via_MPC'
        )

    file_mb = os.path.getsize(out_path) / 1024 / 1024
    ndvi_final = out_data[out_data != NODATA]
    print(f"  已保存: {os.path.basename(out_path)} ({file_mb:.1f} MB)")
    print(f"  NDVI 范围: [{np.min(ndvi_final):.4f}, {np.max(ndvi_final):.4f}], mean={np.mean(ndvi_final):.4f}")

# ============================================
# NDVI 变化统计
# ============================================
print(f"\n{'='*60}")
print("NDVI 统计汇总")
print(f"{'='*60}")

summary_rows = []
for year in YEARS:
    tif_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(tif_path):
        with rasterio.open(tif_path) as src:
            data = src.read(1)
            valid = data[data != NODATA]
            if len(valid) > 0:
                mean_v = np.mean(valid)
                std_v = np.std(valid)
                max_v = np.max(valid)
                min_v = np.min(valid)
                veg_pct = np.sum(valid > 0.3) / len(valid) * 100
                summary_rows.append({
                    'year': year, 'mean': mean_v, 'std': std_v,
                    'min': min_v, 'max': max_v, 'veg_ratio': veg_pct
                })
                print(f"  {year}: 均值={mean_v:.4f}, 标准差={std_v:.4f}, "
                      f"min={min_v:.4f}, max={max_v:.4f}, 植被覆盖比={veg_pct:.1f}%")

csv_path = os.path.join(OUTPUT, "NDVI统计汇总.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%)\n")
    for s in summary_rows:
        f.write(f"{s['year']},{s['mean']:.4f},{s['std']:.4f},{s['min']:.4f},{s['max']:.4f},{s['veg_ratio']:.1f}\n")

print(f"\n统计表: {csv_path}")
print(f"\n所有输出: {OUTPUT}/")
for fname in sorted(os.listdir(OUTPUT)):
    fpath = os.path.join(OUTPUT, fname)
    size = os.path.getsize(fpath)
    print(f"  {fname} ({size/1024/1024:.1f} MB)" if size > 1024*1024 else f"  {fname} ({size:.0f} KB)")

print("\n完毕!")
