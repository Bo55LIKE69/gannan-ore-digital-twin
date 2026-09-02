# -*- coding: utf-8 -*-
"""
为「赣南矿脉 · 3D 数字孪生」页面生成离线地形数据包：
  1) 高程网格 1024x1024（uint16，0.1 m 精度，相对 minH 编码）
  2) 有效掩膜（bit-packed，1 bit/格点）—— DEM 按赣州边界裁剪，外围是 nodata
  3) 山体阴影纹理 2048x2048（JPEG，dataURI 内嵌，脱离 file:// 限制）

输出：dem_terrain_data.js

用法：
  E:/adaconda/python.exe 脚本/build_dem_terrain.py
"""
import base64
import io
import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEM = os.path.join(ROOT, "数据", "DEM", "ganzhou_dem.tif")
HS = os.path.join(ROOT, "数据", "DEM", "ganzhou_hillshade.tif")
OUT = os.path.join(ROOT, "dem_terrain_data.js")

GRID = 1024          # 高程网格边长（顶点数）
ERODE = 2            # 掩膜腐蚀次数，去掉边缘半格
HS_SIZE = 2048       # 山体阴影纹理边长
HS_Q = 82            # JPEG 质量


# ---------- 高程网格（nodata 感知的区块平均） ----------
def build_height_grid():
    with rasterio.open(DEM) as src:
        W, H = src.width, src.height
        nodata = src.nodata if src.nodata is not None else -32768
        west, south, east, north = src.bounds
        print("DEM 源: %dx%d  nodata=%s  范围 %.4f,%.4f ~ %.4f,%.4f"
              % (W, H, nodata, west, south, east, north))

        col_edges = np.rint(np.linspace(0, W, GRID + 1)).astype(np.int64)
        col_edges = np.clip(col_edges, 0, W - 1)

        h_sum = np.zeros((GRID, GRID), dtype=np.float64)
        h_cnt = np.zeros((GRID, GRID), dtype=np.float64)

        for j in range(GRID):
            r0 = int(j * H / GRID)
            r1 = int((j + 1) * H / GRID)
            if r1 <= r0:
                r1 = r0 + 1
            strip = src.read(1, window=((r0, r1), (0, W)))
            valid = (strip != nodata).astype(np.float64)
            vals = np.where(valid > 0, strip, 0.0).astype(np.float64)
            # 沿列方向按输出格网累加
            sm = np.add.reduceat(vals, col_edges[:-1], axis=1)
            ct = np.add.reduceat(valid, col_edges[:-1], axis=1)
            h_sum[j] += sm.sum(axis=0)
            h_cnt[j] += ct.sum(axis=0)

    with np.errstate(invalid="ignore", divide="ignore"):
        heights = np.where(h_cnt > 0, h_sum / np.maximum(h_cnt, 1), np.nan)
    mask = h_cnt > 0
    print("  有效格点占比: %.1f%%" % (mask.mean() * 100))
    return heights, mask, (west, south, east, north)


def erode(m, n=1):
    for _ in range(n):
        p = np.pad(m, 1, constant_values=False)
        c = p[1:-1, 1:-1]
        m = c & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def pack_bits(mask):
    flat = mask.reshape(-1)
    nbytes = (flat.size + 7) // 8
    b = np.zeros(nbytes, dtype=np.uint8)
    for k in range(8):
        idx = np.arange(k, flat.size, 8)
        if idx.size == 0:
            break
        chunk = flat[idx].astype(np.uint8)
        pad = np.zeros(nbytes, dtype=np.uint8)
        pad[: chunk.size] = chunk
        b |= pad << np.uint8(k)
    return b


# ---------- 山体阴影纹理 ----------
def build_hillshade(bounds):
    w, s, e, n = bounds
    dst = np.zeros((HS_SIZE, HS_SIZE), dtype=np.uint8)
    with rasterio.open(HS) as src:
        print("晕渲源: %dx%d %s" % (src.width, src.height, src.crs))
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=from_bounds(w, s, e, n, HS_SIZE, HS_SIZE),
            dst_crs="EPSG:4326",
            resampling=Resampling.average,
        )
    return dst


def to_jpeg_data_uri(gray):
    from PIL import Image
    img = Image.fromarray(gray, mode="L").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=HS_Q, optimize=True)
    raw = buf.getvalue()
    print("  晕渲 JPEG: %.2f MB" % (len(raw) / 1048576.0))
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


# ---------- 与县域数据做一致性自检 ----------
def sanity_check(mask, bounds):
    path = os.path.join(ROOT, "dash_data.js")
    if not os.path.exists(path):
        return
    import re
    txt = open(path, encoding="utf-8").read()
    pts = re.findall(r"\[(\d{2,3}\.\d+),(\d{2}\.\d+),", txt)
    if not pts:
        return
    w, s, e, n = bounds
    inside = 0
    total = 0
    for a, b in pts[:4000]:
        lon, lat = float(a), float(b)
        if not (w <= lon <= e and s <= lat <= n):
            continue
        total += 1
        i = int((lon - w) / (e - w) * (GRID - 1))
        j = int((n - lat) / (n - s) * (GRID - 1))
        if 0 <= i < GRID and 0 <= j < GRID and mask[j, i]:
            inside += 1
    if total:
        print("  矿点落在有效地形上: %.1f%% (%d/%d)" % (inside / total * 100, inside, total))


def main():
    heights, raw_mask, bounds = build_height_grid()
    w, s, e, n = bounds

    mask = erode(raw_mask, ERODE)
    print("  腐蚀后有效格点占比: %.1f%%" % (mask.mean() * 100))

    print("自检 ...")
    sanity_check(raw_mask, bounds)

    print("生成山体阴影 ...")
    hs = build_hillshade(bounds)
    hs_uri = to_jpeg_data_uri(hs)

    hmin = float(np.nanmin(heights))
    hmax = float(np.nanmax(heights))
    print("  高程范围: %.1f ~ %.1f m" % (hmin, hmax))

    enc = np.round((np.nan_to_num(heights, nan=0.0) - hmin) * 10.0).astype(np.uint16)
    hb64 = base64.b64encode(enc.tobytes()).decode("ascii")
    mb64 = base64.b64encode(pack_bits(mask).tobytes()).decode("ascii")
    print("  高程 base64 %.2f MB / 掩膜 %.2f MB"
          % (len(hb64) / 1048576.0, len(mb64) / 1048576.0))

    # 有效区域地理范围（用于相机框景）
    ys, xs = np.where(mask)
    vb = {
        "west": float(w + xs.min() / (GRID - 1) * (e - w)),
        "east": float(w + xs.max() / (GRID - 1) * (e - w)),
        "north": float(n - ys.min() / (GRID - 1) * (n - s)),
        "south": float(n - ys.max() / (GRID - 1) * (n - s)),
    }
    print("  有效地形范围: %.4f,%.4f ~ %.4f,%.4f"
          % (vb["west"], vb["south"], vb["east"], vb["north"]))

    lines = [
        "// 自动生成，请勿手改 —— 源脚本：脚本/build_dem_terrain.py",
        "window.DEM_DATA = {",
        "  west: %.9f, south: %.9f, east: %.9f, north: %.9f," % (w, s, e, n),
        "  width: %d, height: %d," % (GRID, GRID),
        "  minH: %.2f, maxH: %.2f," % (hmin, hmax),
        "  scale: 0.1,",
        "  view: { west: %.6f, south: %.6f, east: %.6f, north: %.6f },"
        % (vb["west"], vb["south"], vb["east"], vb["north"]),
        '  heights: "%s",' % hb64,
        '  mask: "%s",' % mb64,
        '  hillshade: "%s"' % hs_uri,
        "};",
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("已写出:", OUT, "(%.2f MB)" % (os.path.getsize(OUT) / 1048576.0))


if __name__ == "__main__":
    main()
