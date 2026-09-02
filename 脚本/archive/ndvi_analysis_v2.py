# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 v2 — 修复覆盖缺失问题

改进:
  1. 按 WRS-2 path/row 分组选景，确保全城覆盖（赣州跨越 path 121/122, row 42/43）
  2. 每组合选取 top N 景（按云量），而非全局 top N
  3. 最多 100 景/年，确保足够覆盖
  4. 放宽云量阈值至 60%，扩大搜索窗口至 4-10 月
  5. 使用增量均值合成（低内存），按 path/row 分组后加权平均
  6. 报告各区覆盖统计

数据源: Microsoft Planetary Computer → Landsat Collection 2 Level-2
投影: EPSG:4326, ~30m 分辨率
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

# ============================================
# 加载赣州边界
# ============================================
CITY_GEOJSON = os.path.join(BASE, "赣州市_360700_批量下载", "市级", "赣州市_360700.geojson")
import json as _json
with open(CITY_GEOJSON, 'r', encoding='utf-8') as f:
    city_data = _json.load(f)

from shapely.geometry import shape
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
PAD = 0.15
search_bbox = [city_bounds[0]-PAD, city_bounds[1]-PAD, city_bounds[2]+PAD, city_bounds[3]+PAD]

# 输出网格参数 (EPSG:4326, ~30m)
RES = 0.0003
OUT_WIDTH = int((city_bounds[2] - city_bounds[0]) / RES) + 1
OUT_HEIGHT = int((city_bounds[3] - city_bounds[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(city_bounds[0], city_bounds[1], city_bounds[2], city_bounds[3],
                            OUT_WIDTH, OUT_HEIGHT)
NODATA = -9999

print(f"输出网格: {OUT_WIDTH} x {OUT_HEIGHT} ({OUT_WIDTH*OUT_HEIGHT/1e6:.1f}M 像素)")

# ============================================
# 连接 MPC
# ============================================
print("\n" + "=" * 60)
print("连接 Microsoft Planetary Computer...")
print("=" * 60)

from pystac_client import Client
import planetary_computer as pc

for attempt in range(5):
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        print("  MPC 连接成功")
        break
    except Exception as e:
        if attempt < 4:
            wait = (attempt + 1) * 15
            print(f"  连接失败 (attempt {attempt+1}/5): {e}, 等待 {wait}s...")
            time.sleep(wait)
        else:
            raise

# ============================================
# 参数
# ============================================
YEARS = [1990, 2000, 2010, 2015, 2020, 2024]

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

# QA 波段位掩码
QA_FILL = 1 << 0
QA_DILATED_CLOUD = 1 << 1
QA_CIRRUS = 1 << 2
QA_CLOUD = 1 << 3
QA_CLOUD_SHADOW = 1 << 4

def is_clear(qa_band):
    """更宽松的云掩膜：仅移除明确的云和云影，保留薄卷云"""
    bad = QA_DILATED_CLOUD | QA_CLOUD | QA_CLOUD_SHADOW | QA_FILL
    return (qa_band & bad) == 0

def ndvi_from_sr(nir, red):
    nir_sr = (nir.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    red_sr = (red.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    ndvi = (nir_sr - red_sr) / (nir_sr + red_sr + 1e-8)
    return ndvi.clip(-1, 1)

# ============================================
# 辅助：搜索（带重试）
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
                print(f"  MPC 查询失败 (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
                raise

# ============================================
# 处理单景 NDVI
# ============================================
def process_scene(item, city_geom, search_bbox, OUT_TRANSFORM, OUT_WIDTH, OUT_HEIGHT):
    """处理单景 Landsat → 计算 NDVI → reproject 到统一网格"""
    if NIR_KEY not in item.assets or RED_KEY not in item.assets:
        return None, None

    nir_url = pc.sign(item.assets[NIR_KEY].href)
    red_url = pc.sign(item.assets[RED_KEY].href)
    qa_url = pc.sign(item.assets[QA_KEY].href) if QA_KEY in item.assets else None

    with rasterio.open(nir_url) as nir_src:
        scene_crs = nir_src.crs

        if scene_crs and scene_crs != CRS.from_epsg(4326):
            scene_bounds_wgs84 = transform_bounds(scene_crs, CRS.from_epsg(4326), *nir_src.bounds)
        else:
            scene_bounds_wgs84 = nir_src.bounds

        overlap_lon_min = max(search_bbox[0], scene_bounds_wgs84[0])
        overlap_lat_min = max(search_bbox[1], scene_bounds_wgs84[1])
        overlap_lon_max = min(search_bbox[2], scene_bounds_wgs84[2])
        overlap_lat_max = min(search_bbox[3], scene_bounds_wgs84[3])

        if overlap_lon_min >= overlap_lon_max or overlap_lat_min >= overlap_lat_max:
            return None, None

        if scene_crs and scene_crs != CRS.from_epsg(4326):
            overlap_proj = transform_bounds(
                CRS.from_epsg(4326), scene_crs,
                overlap_lon_min, overlap_lat_min, overlap_lon_max, overlap_lat_max
            )
            window = nir_src.window(*overlap_proj)
        else:
            window = nir_src.window(overlap_lon_min, overlap_lat_max, overlap_lon_max, overlap_lat_min)

        win_w, win_h = int(window.width), int(window.height)
        max_dim = 4000
        if max(win_w, win_h) > max_dim:
            scale = max_dim / max(win_w, win_h)
            out_w, out_h = int(win_w * scale), int(win_h * scale)
        else:
            out_w, out_h = win_w, win_h

        if out_w < 10 or out_h < 10:
            return None, None

        with rasterio.open(red_url) as red_src:
            nir_data = nir_src.read(1, window=window, out_shape=(out_h, out_w))
            red_data = red_src.read(1, window=window, out_shape=(out_h, out_w))

        nir_nodata = nir_src.nodata
        red_nodata = red_src.nodata
        if nir_nodata is not None:
            nir_data = np.where(nir_data == nir_nodata, np.nan, nir_data)
        if red_nodata is not None:
            red_data = np.where(red_data == red_nodata, np.nan, red_data)

        if qa_url:
            with rasterio.open(qa_url) as qa_src:
                qa_data = qa_src.read(1, window=window, out_shape=(out_h, out_w))
                clear = is_clear(qa_data)
                nir_data = np.where(clear, nir_data, np.nan)
                red_data = np.where(clear, red_data, np.nan)

        ndvi = ndvi_from_sr(nir_data, red_data)
        src_transform = nir_src.window_transform(window)
        src_transform = src_transform * src_transform.scale(win_w / out_w, win_h / out_h)

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

    valid_count = np.sum(~np.isnan(ndvi_wgs84))
    return ndvi_wgs84, valid_count


# ============================================
# 主循环
# ============================================
for year in YEARS:
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path):
        if os.path.getsize(out_path) > 2 * 1024 * 1024:
            print(f"\n[{year}] 已存在，跳过 (如需重算请手动删除)")
            continue
        else:
            print(f"\n[{year}] 已有文件太小，重新处理...")
            os.remove(out_path)

    print(f"\n{'='*60}")
    print(f"[{year}] 搜索 Landsat 影像...")
    print(f"{'='*60}")

    platforms = YEAR_PLATFORMS.get(year, ["landsat-8"])

    # 第一阶段：宽松搜索（云量<60%，4-10月）
    items = search_with_retry(
        catalog, search_bbox,
        f"{year}-04-01/{year}-10-31",
        {"platform": {"in": platforms}, "eo:cloud_cover": {"lt": 60}},
        max_items=300
    )

    if len(items) == 0:
        # 更宽松搜索
        items = search_with_retry(
            catalog, search_bbox,
            f"{year}-03-01/{year}-11-30",
            {"platform": {"in": platforms}, "eo:cloud_cover": {"lt": 80}},
            max_items=300
        )

    print(f"  搜索到 {len(items)} 景")

    if len(items) == 0:
        print(f"  [{year}] 无可用数据，跳过")
        continue

    # ---- 筛选与城市有交集的场景，按 path/row 分组 ----
    path_row_groups = {}
    skipped_geom = 0
    for item in items:
        try:
            item_geom = shape(item.geometry) if item.geometry else None
            if item_geom is None:
                continue
            if not item_geom.intersects(city_geom):
                skipped_geom += 1
                continue
        except Exception:
            pass

        # 提取 WRS path/row
        wrs_path = item.properties.get('landsat:wrs_path', 'unknown')
        wrs_row = item.properties.get('landsat:wrs_row', 'unknown')
        key = f"p{wrs_path:0>3s}_r{wrs_row:0>3s}" if isinstance(wrs_path, int) else f"p{wrs_path}_r{wrs_row}"

        if key not in path_row_groups:
            path_row_groups[key] = []
        path_row_groups[key].append(item)

    print(f"  与城市相交: {sum(len(v) for v in path_row_groups.values())} 景 "
          f"(跳过 {skipped_geom} 景), 分布在 {len(path_row_groups)} 个 path/row 组合")

    for key in sorted(path_row_groups.keys()):
        print(f"    {key}: {len(path_row_groups[key])} 景")

    if len(path_row_groups) == 0:
        print(f"  [{year}] 无交集场景，跳过")
        continue

    # ---- 每组合按云量排序，选 top N ----
    selected = []
    per_group_limit = max(15, 80 // len(path_row_groups))  # 至少每组合15景

    for key, group in path_row_groups.items():
        group.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        top_n = min(per_group_limit, len(group))
        selected.extend(group[:top_n])

    # 去重（同一场景可能出现在多个组合）
    seen_ids = set()
    unique_selected = []
    for item in selected:
        item_id = item.id
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_selected.append(item)

    # 最终按云量排序，总数不超过100
    unique_selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    unique_selected = unique_selected[:100]

    print(f"  选取 {len(unique_selected)} 景进行处理")
    platform_counts = {}
    for item in unique_selected:
        p = item.properties.get('platform', 'unknown')
        platform_counts[p] = platform_counts.get(p, 0) + 1
    print(f"  平台分布: {platform_counts}")

    # ---- 处理每景，增量均值合成 ----
    ndvi_sum = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float64)
    ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)
    n_processed = 0

    for idx, item in enumerate(unique_selected):
        try:
            ndvi_arr, n_valid = process_scene(item, city_geom, search_bbox,
                                              OUT_TRANSFORM, OUT_WIDTH, OUT_HEIGHT)
            if ndvi_arr is None:
                continue

            mask = ~np.isnan(ndvi_arr)
            ndvi_sum[mask] += ndvi_arr[mask].astype(np.float64)
            ndvi_count[mask] += 1
            n_processed += 1

        except Exception as e:
            if idx < 5:
                print(f"    场景 {idx} ({item.id[:30]}) 处理失败: {e}")
            continue

        if (idx + 1) % 20 == 0:
            sys.stdout.write(f"\r  处理: {idx+1}/{len(unique_selected)}, 成功: {n_processed}")
            sys.stdout.flush()

    print(f"\r  成功处理: {n_processed}/{len(unique_selected)} 景")

    if n_processed == 0:
        print(f"  [{year}] 无有效数据，跳过")
        continue

    # ---- 计算均值 ----
    valid = ndvi_count > 0
    ndvi_mean = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    ndvi_mean[valid] = (ndvi_sum[valid] / ndvi_count[valid]).astype(np.float32)
    del ndvi_sum

    # ---- 覆盖统计 ----
    print(f"  合成前覆盖统计:")
    single_cover_pct = np.sum(ndvi_count == 1) / valid.sum() * 100 if valid.sum() > 0 else 0
    multi_cover_pct = np.sum(ndvi_count >= 3) / valid.sum() * 100 if valid.sum() > 0 else 0
    print(f"    仅1景覆盖: {single_cover_pct:.1f}%, 3景及以上: {multi_cover_pct:.1f}%")
    print(f"    平均覆盖景数: {ndvi_count[valid].mean():.1f}")

    # ---- 按城市多边形 mask 裁剪 ----
    print(f"  多边形 mask 裁剪...")
    city_mask = geometry_mask(
        [city_geom],
        out_shape=(OUT_HEIGHT, OUT_WIDTH),
        transform=OUT_TRANSFORM,
        invert=True,
        all_touched=True
    )

    ndvi_mean[~city_mask] = np.nan
    n_city_pixels = np.sum(city_mask)
    n_valid_final = np.sum(~np.isnan(ndvi_mean))
    coverage_in_city = n_valid_final / n_city_pixels * 100 if n_city_pixels > 0 else 0

    print(f"  多边形内像素: {n_city_pixels}, 有效 NDVI: {n_valid_final} ({coverage_in_city:.1f}%)")

    # ---- 覆盖不足时的二次补充搜索 ----
    if coverage_in_city < 70 and n_processed < 100:
        print(f"  ⚠ 覆盖率不足 ({coverage_in_city:.1f}%)，尝试补充搜索...")

        # 识别空缺区域：按网格分块检查
        block_size = 500
        gap_blocks = 0
        for bi in range(0, OUT_HEIGHT, block_size):
            for bj in range(0, OUT_WIDTH, block_size):
                block = ndvi_mean[bi:bi+block_size, bj:bj+block_size]
                block_city = city_mask[bi:bi+block_size, bj:bj+block_size]
                if np.sum(block_city) > 100:
                    block_valid = np.sum(~np.isnan(block))
                    block_total = np.sum(block_city)
                    if block_valid / block_total < 0.5:
                        gap_blocks += 1

        print(f"    空缺区块: {gap_blocks}")

        # 放宽搜索获取更多场景
        extra_items = search_with_retry(
            catalog, search_bbox,
            f"{year}-04-01/{year}-10-31",
            {"platform": {"in": platforms}, "eo:cloud_cover": {"lt": 80}},
            max_items=200
        )

        extra_valid = []
        for item in extra_items:
            try:
                item_geom = shape(item.geometry) if item.geometry else None
                if item_geom and item_geom.intersects(city_geom):
                    extra_valid.append(item)
            except Exception:
                pass

        extra_valid.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        existing_ids = {item.id for item in unique_selected}
        extra_new = [item for item in extra_valid if item.id not in existing_ids][:50]

        if extra_new:
            print(f"    补充处理 {len(extra_new)} 额外场景...")
            extra_processed = 0
            for idx, item in enumerate(extra_new):
                try:
                    ndvi_arr, n_valid = process_scene(item, city_geom, search_bbox,
                                                      OUT_TRANSFORM, OUT_WIDTH, OUT_HEIGHT)
                    if ndvi_arr is None:
                        continue
                    mask = ~np.isnan(ndvi_arr)
                    ndvi_count[mask] += 1
                    # 更新 ndvi_mean: new_mean = (old_count*old_mean + new_val) / (old_count + 1)
                    existing_count = ndvi_count[mask] - 1  # 加之前的count
                    old_mean = ndvi_mean[mask].copy()
                    ndvi_mean[mask] = (existing_count * old_mean + ndvi_arr[mask].astype(np.float64)) / ndvi_count[mask]
                    extra_processed += 1
                except Exception:
                    continue
                if (idx + 1) % 20 == 0:
                    sys.stdout.write(f"\r      补充: {idx+1}/{len(extra_new)}, 成功: {extra_processed}")
                    sys.stdout.flush()
            print(f"\r      补充成功: {extra_processed}/{len(extra_new)} 景")

            # 重新裁剪
            ndvi_mean[~city_mask] = np.nan
            n_valid_final = np.sum(~np.isnan(ndvi_mean))
            coverage_in_city = n_valid_final / n_city_pixels * 100 if n_city_pixels > 0 else 0
            print(f"    补充后覆盖率: {coverage_in_city:.1f}%")
        else:
            print(f"    无额外场景可用")
    else:
        pass

    if n_valid_final == 0:
        print(f"  [{year}] 城市范围内无有效 NDVI 数据")
        continue

    # ---- Crop 到有效范围 ----
    rows, cols = np.where(~np.isnan(ndvi_mean))
    r_min, r_max = rows.min(), rows.max() + 1
    c_min, c_max = cols.min(), cols.max() + 1
    ndvi_cropped = ndvi_mean[r_min:r_max, c_min:c_max]
    cropped_transform = OUT_TRANSFORM * rasterio.Affine.translation(c_min, r_min)

    # ---- 导出 GeoTIFF ----
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
            index='NDVI',
            method='mean_composite_path_row_balanced',
            n_scenes=str(n_processed + extra_processed if 'extra_processed' in dir() else n_processed),
            source='Landsat_C2_L2_via_MPC',
            coverage_pct=f"{coverage_in_city:.1f}"
        )

    file_mb = os.path.getsize(out_path) / 1024 / 1024
    ndvi_values = out_data[out_data != NODATA]
    print(f"  已保存: {os.path.basename(out_path)} ({file_mb:.1f} MB)")
    print(f"  NDVI 范围: [{np.min(ndvi_values):.4f}, {np.max(ndvi_values):.4f}], "
          f"均值={np.mean(ndvi_values):.4f}")

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
                coverage_tag = src.tags().get('coverage_pct', 'N/A')
                summary_rows.append({
                    'year': year, 'mean': mean_v, 'std': std_v,
                    'min': min_v, 'max': max_v, 'veg_ratio': veg_pct,
                    'coverage': coverage_tag
                })
                print(f"  {year}: 均值={mean_v:.4f}, σ={std_v:.4f}, "
                      f"植被覆盖={veg_pct:.1f}%, 覆盖率={coverage_tag}%")

csv_path = os.path.join(OUTPUT, "NDVI统计汇总.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%)\n")
    for s in summary_rows:
        f.write(f"{s['year']},{s['mean']:.4f},{s['std']:.4f},{s['min']:.4f},{s['max']:.4f},{s['veg_ratio']:.1f},{s['coverage']}\n")

print(f"\n统计表: {csv_path}")
print(f"\n所有输出: {OUTPUT}/")
for fname in sorted(os.listdir(OUTPUT)):
    fpath = os.path.join(OUTPUT, fname)
    size = os.path.getsize(fpath)
    if size > 1024*1024:
        print(f"  {fname} ({size/1024/1024:.1f} MB)")
    else:
        print(f"  {fname} ({size:.0f} KB)")

print("\n完毕!")
