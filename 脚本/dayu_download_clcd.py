# -*- coding: utf-8 -*-
"""
大余县 CLCD 土地覆盖数据下载与裁切
数据源: CLCD v1.0.5 (Yang et al., 1985-2025) Zenodo record 18180184
方法: 多线程 Range 分块下载全国版 tif -> rasterio 按大余县边界(mask)裁切
输出:
  数据/大余县/CLCD_raw/CLCD_v01_YYYY_albert.tif        (全国原始, 保留备用)
  数据/大余县/CLCD_dayu/CLCD_v01_YYYY_dayu.tif         (大余县裁切, 论文用)
"""
import os
import sys
import time
import json
import urllib.request
import concurrent.futures

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
REC = "18180184"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "数据", "大余县", "CLCD_raw")
DAYU = os.path.join(BASE, "数据", "大余县", "CLCD_dayu")
BOUND = os.path.join(BASE, "boundary", "dayu_boundary_albers.shp")
os.makedirs(RAW, exist_ok=True)
os.makedirs(DAYU, exist_ok=True)

proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("http_proxy")

def make_opener():
    if proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        op = urllib.request.build_opener()
    op.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
    return op

def file_size(op, link):
    req = urllib.request.Request(link, method="HEAD")
    r = op.open(req, timeout=60)
    return int(r.headers.get("Content-Length", 0))

def download_tif(year, threads=8):
    fname = f"CLCD_v01_{year}_albert.tif"
    link = f"https://zenodo.org/api/records/{REC}/files/{fname}/content"
    out = os.path.join(RAW, fname)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print(f"[skip] {fname} 已存在 {os.path.getsize(out)/1e6:.0f}MB")
        return out
    op = make_opener()
    size = file_size(op, link)
    print(f"[info] {fname} 总大小 {size/1e6:.0f}MB, 分 {threads} 块下载")
    chunks = [(i * size // threads, min(size, (i + 1) * size // threads) - 1) for i in range(threads)]
    tmp = out + ".parts"
    os.makedirs(tmp, exist_ok=True)

    def dl(seg):
        i, (s, e) = seg
        p = os.path.join(tmp, f"{i}.part")
        if os.path.exists(p) and os.path.getsize(p) == (e - s + 1):
            return
        for attempt in range(4):
            try:
                req = urllib.request.Request(link, headers={"Range": f"bytes={s}-{e}"})
                data = op.open(req, timeout=300).read()
                with open(p, "wb") as f:
                    f.write(data)
                return
            except Exception as e:
                if attempt < 3:
                    time.sleep(3)
                else:
                    raise

    for attempt in range(3):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
                list(ex.map(dl, list(enumerate(chunks))))
            break
        except Exception as e:
            print(f"  [retry 整体] {attempt}: {e}")
            time.sleep(5)
    # 合并
    with open(out, "wb") as fo:
        for i in range(threads):
            p = os.path.join(tmp, f"{i}.part")
            with open(p, "rb") as fi:
                fo.write(fi.read())
            os.remove(p)
    os.rmdir(tmp)
    if os.path.getsize(out) != size:
        raise RuntimeError(f"{fname} 大小校验失败: {os.path.getsize(out)} != {size}")
    print(f"[done] {fname} -> {out} ({os.path.getsize(out)/1e6:.0f}MB)")
    return out

def clip_dayu(tif_path, year):
    import rasterio
    from rasterio.mask import mask
    import geopandas as gpd
    gdf = gpd.read_file(BOUND)
    out = os.path.join(DAYU, f"CLCD_v01_{year}_dayu.tif")
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print(f"[skip clip] {out}")
        return out
    with rasterio.open(tif_path) as ds:
        data, transform = mask(ds, gdf.geometry, crop=True, nodata=0)
        meta = ds.meta.copy()
        meta.update(height=data.shape[1], width=data.shape[2], transform=transform,
                    dtype=data.dtype, nodata=0, compress="LZW")
        with rasterio.open(out, "w", **meta) as d:
            d.write(data)
    print(f"[clip] {out} ({os.path.getsize(out)/1e6:.2f}MB)")
    return out

def main():
    years = sys.argv[1].split(",") if len(sys.argv) > 1 else ["1990", "2000", "2010", "2015", "2020", "2025"]
    t0 = time.time()
    for y in years:
        p = download_tif(y)
        clip_dayu(p, y)
    print(f"\nALL DONE 用时 { (time.time()-t0)/60:.1f} min")
    print("裁切结果:")
    for y in years:
        fp = os.path.join(DAYU, f"CLCD_v01_{y}_dayu.tif")
        if os.path.exists(fp):
            print(f"  {y}: {os.path.getsize(fp)/1e6:.2f}MB")

if __name__ == "__main__":
    main()
