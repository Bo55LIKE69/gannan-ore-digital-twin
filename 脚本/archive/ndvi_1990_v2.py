# -*- coding: utf-8 -*-
"""
1990 NDVI 补算 — 基于 ndvi_final.py 参数微调
仅放宽搜索: 4-10月, 云量<80%, 每path 20景, 总共100景
"""
import os, sys, json, time
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.features import geometry_mask
from shapely.geometry import shape
from shapely.ops import unary_union
from pystac_client import Client
import planetary_computer as pc
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "NDVI分析结果")
os.makedirs(OUTPUT, exist_ok=True)

CITY_GEOJSON = os.path.join(BASE, "赣州市_360700_批量下载", "市级", "赣州市_360700.geojson")
with open(CITY_GEOJSON, 'r', encoding='utf-8') as f:
    city_data = json.load(f)

city_polys = []
for feat in city_data['features']:
    geom = shape(feat['geometry'])
    city_polys.extend(list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom])
city_geom = unary_union(city_polys)
cb = city_geom.bounds
print(f"赣州: {cb[0]:.3f}~{cb[2]:.3f}E, {cb[1]:.3f}~{cb[3]:.3f}N")

PAD = 0.15
SEARCH_BBOX = [cb[0]-PAD, cb[1]-PAD, cb[2]+PAD, cb[3]+PAD]

RES = 0.001
OUT_WIDTH  = int((cb[2] - cb[0]) / RES) + 1
OUT_HEIGHT = int((cb[3] - cb[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(cb[0], cb[1], cb[2], cb[3], OUT_WIDTH, OUT_HEIGHT)
NODATA = np.float32(-9999)
MAX_WINDOW = 800

SR_SCALE  = 0.0000275
SR_OFFSET = -0.2

print(f"输出网格: {OUT_WIDTH}x{OUT_HEIGHT} ({OUT_WIDTH*OUT_HEIGHT/1e6:.1f}M px)")

# MPC
print("连接 MPC...")
for attempt in range(5):
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        print("MPC 已连接\n")
        break
    except Exception as e:
        print(f"  尝试 {attempt+1}/5 失败: {e}")
        if attempt < 4:
            time.sleep((attempt+1)*15)
        else:
            raise


def search_mpc(bbox, dt, platforms, cc_max, max_items):
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
            print(f"  搜索重试 {attempt+1}: {e}")
            if attempt < 2:
                time.sleep((attempt+1)*8)
    return []


def process_scene(item):
    nir_url = pc.sign(item.assets['nir08'].href)
    red_url = pc.sign(item.assets['red'].href)

    with rasterio.open(nir_url) as nir_src:
        sc_crs = nir_src.crs
        if sc_crs and sc_crs != CRS.from_epsg(4326):
            sc_b_wgs = transform_bounds(sc_crs, CRS.from_epsg(4326), *nir_src.bounds)
        else:
            sc_b_wgs = nir_src.bounds

        ol_l = max(SEARCH_BBOX[0], sc_b_wgs[0])
        ol_b = max(SEARCH_BBOX[1], sc_b_wgs[1])
        ol_r = min(SEARCH_BBOX[2], sc_b_wgs[2])
        ol_t = min(SEARCH_BBOX[3], sc_b_wgs[3])

        if ol_l >= ol_r or ol_b >= ol_t:
            return None

        if sc_crs and sc_crs != CRS.from_epsg(4326):
            ol_proj = transform_bounds(CRS.from_epsg(4326), sc_crs, ol_l, ol_b, ol_r, ol_t)
            window = nir_src.window(ol_proj[0], ol_proj[1], ol_proj[2], ol_proj[3])
        else:
            window = nir_src.window(ol_l, ol_b, ol_r, ol_t)

        ww, wh = int(window.width), int(window.height)
        scale = min(1.0, MAX_WINDOW / max(ww, wh))
        ow, oh = max(10, int(ww*scale)), max(10, int(wh*scale))

        with rasterio.open(red_url) as red_src:
            nir_arr = nir_src.read(1, window=window, out_shape=(oh, ow))
            red_arr = red_src.read(1, window=window, out_shape=(oh, ow))

        if nir_src.nodata is not None:
            nir_arr = np.where(nir_arr == nir_src.nodata, np.nan, nir_arr)
        if red_src.nodata is not None:
            red_arr = np.where(red_arr == red_src.nodata, np.nan, red_arr)

        nir_arr = np.where((nir_arr > 1000) & (nir_arr < 60000), nir_arr, np.nan)
        red_arr = np.where((red_arr > 1000) & (red_arr < 60000), red_arr, np.nan)

        nir_sr = (nir_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
        red_sr = (red_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
        ndvi_arr = ((nir_sr-red_sr)/(nir_sr+red_sr+1e-8)).clip(-1, 1)

        src_tf = nir_src.window_transform(window)
        src_tf = src_tf * src_tf.scale(ww/ow, wh/oh)

    out = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    reproject(
        source=ndvi_arr, destination=out,
        src_transform=src_tf, src_crs=sc_crs,
        dst_transform=OUT_TRANSFORM, dst_crs=CRS.from_epsg(4326),
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )
    return out


# ============================================================
# 1990 处理
# ============================================================
year = 1990
out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
if os.path.exists(out_path):
    os.remove(out_path)

print(f"{'='*60}")
print(f"[{year}] 搜索 Landsat-5 (放宽参数)...")

# 主搜索: 4-10月, 云量<80%
items = search_mpc(SEARCH_BBOX, f"{year}-04-01/{year}-10-31", ["landsat-5"], 80, 500)
print(f"  4-10月,云量<80%: {len(items)} 景")

# 扩展搜索: 全年
if len(items) < 80:
    items2 = search_mpc(SEARCH_BBOX, f"{year}-01-01/{year}-12-31", ["landsat-5"], 100, 500)
    ids = {it.id for it in items}
    for it in items2:
        if it.id not in ids:
            items.append(it); ids.add(it.id)
    print(f"  合并全年: {len(items)} 景")

# 按 path 分组
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

n_city = sum(len(v) for v in path_groups.values())
print(f"  城市相交: {n_city} 景, path={sorted(path_groups.keys())}")

if n_city == 0:
    print("无数据")
    sys.exit(1)

# 选景: 每path 20景, 总共100景, 按云量排序
selected = []
per_path = 20
for pp, grp in path_groups.items():
    grp.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    selected.extend(grp[:per_path])

seen = set()
selected = [s for s in selected if not (s.id in seen or seen.add(s.id))]
selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
selected = selected[:100]

pcnt = Counter(s.properties.get('landsat:wrs_path', '?') for s in selected)
clouds = [s.properties.get('eo:cloud_cover', 999) for s in selected]
print(f"  选中 {len(selected)} 景: {dict(pcnt)}")
if clouds:
    print(f"  云量: {min(clouds):.0f}%~{max(clouds):.0f}%, 平均{np.mean(clouds):.1f}%")

# 处理
ndvi_sum   = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float64)
ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)
n_ok = 0
t0 = time.time()

for idx, item in enumerate(selected):
    try:
        arr = process_scene(item)
        if arr is None:
            continue
        valid = ~np.isnan(arr)
        ndvi_sum[valid]   += arr[valid].astype(np.float64)
        ndvi_count[valid] += 1
        n_ok += 1
    except Exception as e:
        if idx < 3:
            print(f"  场景[{idx}] {item.id[:30]} 失败: {e}")
        continue

    done = idx + 1
    if done % 10 == 0 or done == len(selected):
        elapsed = time.time() - t0
        sys.stdout.write(f"\r  处理: {done}/{len(selected)}, 成功: {n_ok}, "
                       f"{elapsed/done:.1f}s/景, 总{elapsed:.0f}s")
        sys.stdout.flush()

elapsed = time.time() - t0
print(f"\r  成功: {n_ok}/{len(selected)}, "
      f"{elapsed/n_ok:.1f}s/景, 总{elapsed:.0f}s" if n_ok > 0 else f"\r  成功: 0/{len(selected)}")

if n_ok == 0:
    print("无有效数据")
    sys.exit(1)

valid_mask = ndvi_count > 0
ndvi = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
ndvi[valid_mask] = (ndvi_sum[valid_mask] / ndvi_count[valid_mask]).astype(np.float32)
del ndvi_sum

mean_scenes = ndvi_count[valid_mask].mean()
cover_1 = np.sum(ndvi_count == 1) / valid_mask.sum() * 100
cover_5 = np.sum(ndvi_count >= 5) / valid_mask.sum() * 100
print(f"  覆盖: 平均{mean_scenes:.1f}景, 仅1景={cover_1:.1f}%, >=5景={cover_5:.1f}%")

city_mask = geometry_mask(
    [city_geom], out_shape=(OUT_HEIGHT, OUT_WIDTH),
    transform=OUT_TRANSFORM, invert=True, all_touched=True
)
ndvi[~city_mask] = np.nan
n_city_px = np.sum(city_mask)
n_valid = np.sum(~np.isnan(ndvi))
cov_pct = n_valid / n_city_px * 100 if n_city_px > 0 else 0

mid = OUT_WIDTH // 2
for label, sl in [("西", slice(0, mid)), ("东", slice(mid, None))]:
    rm = city_mask[:, sl]; rn = ndvi[:, sl]
    rt = np.sum(rm); rv = np.sum(~np.isnan(rn)) if rt > 0 else 0
    if rt > 0: print(f"    {label}半部: {rv/rt*100:.1f}%")
print(f"  城市整体覆盖: {cov_pct:.1f}%")

if n_valid == 0:
    print("城市内无有效数据")
    sys.exit(1)

rows, cols = np.where(~np.isnan(ndvi))
r0, r1 = rows.min(), rows.max() + 1
c0, c1 = cols.min(), cols.max() + 1
ndvi_crop = ndvi[r0:r1, c0:c1]
crop_tf = OUT_TRANSFORM * rasterio.Affine.translation(c0, r0)

with rasterio.open(
    out_path, 'w', driver='GTiff',
    height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
    dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
    compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
) as dst:
    out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
    dst.write(out_data, 1)
    dst.update_tags(
        year=str(year), index='NDVI', method='Landsat_mean_100m',
        n_scenes=str(n_ok), coverage_pct=f"{cov_pct:.1f}"
    )

mb = os.path.getsize(out_path) / 1024 / 1024
vals = out_data[out_data != NODATA]
print(f"  保存: {os.path.basename(out_path)} ({mb:.1f} MB)")
print(f"  NDVI: mean={np.mean(vals):.4f}, range=[{np.min(vals):.4f}, {np.max(vals):.4f}]")

# 更新 CSV
csv_path = os.path.join(OUTPUT, "NDVI统计汇总.csv")
rows_list = []
for yy in [1990, 2000, 2010, 2015, 2020, 2024]:
    fp = os.path.join(OUTPUT, f"赣州_NDVI_{yy}_wgs84.tif")
    if not os.path.exists(fp):
        continue
    with rasterio.open(fp) as src:
        data = src.read(1)
        v = data[data != NODATA]
        if len(v) == 0:
            continue
        veg = np.sum(v > 0.3) / len(v) * 100
        cov = src.tags().get('coverage_pct', 'N/A')
        rows_list.append(f"{yy},{np.mean(v):.4f},{np.std(v):.4f},{np.min(v):.4f},{np.max(v):.4f},{veg:.1f},{cov}")

with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%)\n")
    f.write("\n".join(rows_list) + "\n")

print(f"CSV 已更新: {csv_path}")
print("=== 完毕 ===")
