# -*- coding: utf-8 -*-
"""构建发布目录 dist/：Cesium 本地化 + 资源压缩 + 路径改写，产出零外部依赖的静态站点"""
import io, os, re, shutil, tarfile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
SRC_HTML = "赣南矿脉_数字孪生大屏.html"
TGZ = os.path.join(ROOT, ".temp", "cesium.tgz")

DATA_JS = ["dash_data.js", "dem_terrain_data.js", "hotspot_data.js",
           "point_score.js", "analysis_layers.js"]

# 工艺图：中文名 -> 英文短名（避免上传/URL 编码问题）
PROC_MAP = {
    "工艺图/池浸.png":            "img/proc-1-pool-leach.jpg",
    "工艺图/堆浸.png":            "img/proc-2-heap-leach.jpg",
    "工艺图/原地浸矿.png":        "img/proc-3-in-situ.jpg",
    "工艺图/无铵绿色原地浸矿.png": "img/proc-4-green-in-situ.jpg",
}

DOCS = {
    "技术复盘与学习指南.html": "docs/tech-guide.html",
    "后端与数据库演进方案.html": "docs/backend-plan.html",
    "AI时代学代码指南.html":   "docs/ai-learning.html",
}


def clean():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)


def extract_cesium():
    """从 npm tarball 里只取 package/Build/Cesium/** -> dist/Cesium/"""
    n = 0
    with tarfile.open(TGZ, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            if not m.name.startswith("package/Build/Cesium/"):
                continue
            rel = m.name[len("package/Build/Cesium/"):]
            out = os.path.join(DIST, "Cesium", *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            src = tf.extractfile(m)
            with open(out, "wb") as f:
                f.write(src.read())
            n += 1
    assert n > 100, "Cesium 解压文件数异常: %d" % n
    print("Cesium 解压 %d 个文件" % n)


def copy_data():
    for f in DATA_JS:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(DIST, f))
        print("  + %s (%.2f MB)" % (f, os.path.getsize(os.path.join(ROOT, f)) / 1e6))


def build_images():
    os.makedirs(os.path.join(DIST, "img"), exist_ok=True)
    for src, dst in PROC_MAP.items():
        p = os.path.join(ROOT, src)
        im = Image.open(p)
        if im.width > 1100:
            im = im.resize((1100, int(im.height * 1100 / im.width)), Image.LANCZOS)
        out = os.path.join(DIST, *dst.split("/"))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGB")
        im.save(out, "JPEG", quality=84, optimize=True)
        print("  + %s -> %s (%.2f MB -> %.0f KB)" %
              (src, dst, os.path.getsize(p) / 1e6, os.path.getsize(out) / 1024))


def build_docs():
    os.makedirs(os.path.join(DIST, "docs"), exist_ok=True)
    items = []
    for src, dst in DOCS.items():
        shutil.copy2(os.path.join(ROOT, src), os.path.join(DIST, *dst.split("/")))
        title = re.search(r"<title>(.*?)</title>",
                          io.open(os.path.join(ROOT, src), encoding="utf-8").read()).group(1)
        items.append((dst.split("/")[-1], title))
    lis = "\n".join('      <li><a href="%s">%s</a></li>' % (f, t) for f, t in items)
    page = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>项目文档 · 赣南稀土数字孪生</title>
<style>
body{margin:0;background:#f6f7f9;color:#1b2331;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:64px 24px}
h1{font-size:24px;margin:0 0 6px}
p.sub{color:#4b5567;margin:0 0 28px;font-size:14px}
ul{list-style:none;padding:0;margin:0}
li{border:1px solid #dfe4ec;background:#fff;border-radius:8px;margin:10px 0}
a{display:block;padding:16px 20px;color:#1f6feb;text-decoration:none;font-size:15px}
a:hover{background:#f2f6fd}
a small{display:block;color:#8a93a6;font-size:12.5px;margin-top:4px}
.back{display:inline-block;margin-top:26px;font-size:13.5px}
</style></head><body><div class="wrap">
<h1>项目文档</h1>
<p class="sub">赣南稀土矿脉三维数字孪生可视化平台 · 配套说明文档</p>
<ul>
%s
</ul>
<a class="back" href="../index.html">&larr; 回到数字孪生大屏</a>
</div></body></html>
""" % lis
    io.open(os.path.join(DIST, "docs", "index.html"), "w", encoding="utf-8", newline="\n").write(page)
    print("  + docs/index.html（%d 份文档）" % len(items))


def build_html():
    s = io.open(os.path.join(ROOT, SRC_HTML), encoding="utf-8").read()

    # 1) Cesium 本地化（必须在引入 Cesium.js 之前声明 CESIUM_BASE_URL）
    old_cdn = '<script src="https://cesium.com/downloads/cesiumjs/releases/1.114/Build/Cesium/Cesium.js"></script>'
    assert s.count(old_cdn) == 1
    s = s.replace(old_cdn,
                  '<script>window.CESIUM_BASE_URL = "./Cesium/";</script>\n'
                  '<script src="./Cesium/Cesium.js"></script>')

    old_css = '<link href="https://cesium.com/downloads/cesiumjs/releases/1.114/Build/Cesium/Widgets/widgets.css" rel="stylesheet">'
    assert s.count(old_css) == 1
    s = s.replace(old_css, '<link href="./Cesium/Widgets/widgets.css" rel="stylesheet">')

    # 2) Google Fonts 异步化：国内可能加载慢，不能阻塞首屏渲染
    old_font = re.search(r'<link href="https://fonts\.googleapis\.com[^>]*>', s).group(0)
    s = s.replace(old_font,
                  '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;600;700;900&family=JetBrains+Mono:wght@300;400;500;600&family=Playfair+Display:wght@700&display=swap" rel="stylesheet" media="print" onload="this.media=\'all\'">')

    # 3) 工艺图路径改为英文短名
    for src, dst in PROC_MAP.items():
        assert s.count(src) == 1, "工艺图引用未找到或不唯一: %s" % src
        s = s.replace(src, dst)

    # 4) 残留的绝对/外部依赖检查
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', s)
    ext = [u for u in ext if "fonts.googleapis" not in u and "data:image" not in u]
    assert not ext, "仍存在外部依赖: %s" % ext

    io.open(os.path.join(DIST, "index.html"), "w", encoding="utf-8", newline="\n").write(s)
    print("  + index.html (%.1f KB)" % (len(s.encode("utf-8")) / 1024))


def main():
    if not os.path.exists(TGZ):
        raise SystemExit("缺少 .temp/cesium.tgz")
    clean()
    print("[1/5] 解压 Cesium")
    extract_cesium()
    print("[2/5] 复制数据")
    copy_data()
    print("[3/5] 压缩工艺图")
    build_images()
    print("[4/5] 生成文档页")
    build_docs()
    print("[5/5] 生成 index.html")
    build_html()

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(DIST) for f in fs)
    cnt = sum(len(fs) for _, _, fs in os.walk(DIST))
    print("\ndist/ 就绪：%d 个文件，%.1f MB" % (cnt, total / 1e6))


if __name__ == "__main__":
    main()
