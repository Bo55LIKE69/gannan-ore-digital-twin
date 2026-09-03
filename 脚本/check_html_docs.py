# -*- coding: utf-8 -*-
"""三份 HTML 文档的基础体检：标签平衡 / 锚点一致 / CSS 变量闭合"""
import io, re, sys, os

FILES = ["技术复盘与学习指南.html", "后端与数据库演进方案.html", "AI时代学代码指南.html"]
VOID = {"meta", "br", "hr", "img", "input", "link", "source"}
TAGS = ["div", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "pre", "code",
        "ul", "ol", "li", "p", "strong", "em", "b", "nav", "header", "footer", "span", "thead"]

for fn in FILES:
    if not os.path.exists(fn):
        print("[SKIP] %s 不存在" % fn); continue
    s = io.open(fn, "r", encoding="utf-8").read()
    errs = []

    # 1) 标签平衡
    for t in TAGS:
        o = len(re.findall(r"<%s[\s>]" % t, s))
        c = len(re.findall(r"</%s>" % t, s))
        if o != c:
            errs.append("标签不平衡 <%s>: 开 %d / 闭 %d" % (t, o, c))

    # 2) 锚点一致性
    ids = set(re.findall(r'id="(s\d+)"', s))
    hrefs = set(re.findall(r'href="#(s\d+)"', s))
    if ids and hrefs - ids:
        errs.append("目录锚点无对应 id: %s" % (hrefs - ids))
    if ids and ids - hrefs:
        errs.append("有 id 未进目录: %s" % (ids - hrefs))

    # 3) CSS 变量：使用的 var(--x) 必须已定义
    defined = set(re.findall(r"(--[a-z0-9]+)\s*:", s))
    used = set(re.findall(r"var\((--[a-z0-9]+)\)", s))
    miss = used - defined
    if miss:
        errs.append("未定义的 CSS 变量: %s" % miss)

    # 4) 疑似未转义的裸 <（排除 <script> 区块内的 JS 比较/字符串）
    body = re.sub(r"<script[\s\S]*?</script>", "", s)
    bad = re.findall(r"<(?![a-zA-Z/!])", body)
    if bad:
        errs.append("疑似未转义的 '<' 共 %d 处" % len(bad))

    # 5) 占位符残留（window.XXX 是架构示意图里的合法写法）
    for ph in ["TODO", "PLACEHOLDER", "待补充", "【待填"]:
        if ph in s:
            errs.append("占位符残留: %s" % ph)

    # 6) 深色残留（浅色主题校验；#dfe4ec 已被复用为 --line，不算）
    dark = re.findall(r"#(?:0f1115|161a21|1c212b|2a3140|a3adbe|6f7a8c)", s)
    if dark:
        errs.append("深色残留色值: %s" % set(dark))

    status = "PASS" if not errs else "FAIL"
    print("%-28s %s  (%d 字符, %d 个 id)" % (fn, status, len(s), len(ids)))
    for e in errs:
        print("    - " + e)

sys.exit(0)
