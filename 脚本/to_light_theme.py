# -*- coding: utf-8 -*-
"""把深色主题的两份 HTML 文档整体转换成浅色主题（带唯一性断言的精确替换）"""
import io, re, sys

LIGHT_ROOT = """:root{
  --bg:#f6f7f9; --bg2:#ffffff; --bg3:#eef1f6; --line:#dfe4ec;
  --tx:#1b2331; --tx2:#4b5567; --tx3:#8a93a6;
  --gold:#9a6b12; --blue:#1f6feb; --green:#17794a; --red:#c0392b; --purple:#7c4dcd;
  --mono:'JetBrains Mono','Cascadia Code',Consolas,'Courier New',monospace;
}"""

DARK_ROOT_RE = re.compile(
    r":root\{\s*--bg:#0f1115;.*?--mono:'JetBrains Mono'.*?;?\s*\}", re.S)

# (文件名, [(旧串, 新串, 期望次数)])
JOBS = {
    "技术复盘与学习指南.html": [
        ("strong{color:#fff; font-weight:600}",
         "strong{color:#0f1729; font-weight:650}", 1),
        ("background:#0a0c10; border:1px solid var(--line)",
         "background:#fbfcfe; border:1px solid var(--line)", 1),
        ("font-size:12.5px; color:#c8d0dc; display:block",
         "font-size:12.5px; color:#2b3240; display:block", 1),
        (".kw{color:#c792ea} .fn{color:#82aaff} .str{color:#c3e88d} .num{color:#f78c6c}",
         ".kw{color:#8250df} .fn{color:#0550ae} .str{color:#0a7d34} .num{color:#b8500a}", 1),
        (".cm{color:#5c6773; font-style:italic} .gl{color:#ffcb6b} .ty{color:#ffcb6b}",
         ".cm{color:#8a93a6; font-style:italic} .gl{color:#9a6700} .ty{color:#9a6700}", 1),
        ("tbody tr:nth-child(even){background:rgba(255,255,255,.018)}",
         "tbody tr:nth-child(even){background:rgba(15,23,41,.028)}", 1),
        ("tbody tr:hover{background:rgba(90,169,230,.06)}",
         "tbody tr:hover{background:rgba(31,111,235,.07)}", 1),
        # 打印样式：浅色主题下不再需要强制白底覆盖
        ("""@media print{
  body{background:#fff; color:#111}
  .toc{page-break-inside:avoid} pre{background:#f6f8fa; border-color:#ddd}
  pre code{color:#222} .cm{color:#6a737d} .kw{color:#d73a49} .str{color:#032f62}
  h2{page-break-after:avoid}
}""",
         """@media print{
  body{background:#fff; color:#111}
  .toc{page-break-inside:avoid}
  h2{page-break-after:avoid} pre{page-break-inside:avoid}
}""", 1),
    ],
    "后端与数据库演进方案.html": [
        ("strong{color:#fff; font-weight:600}",
         "strong{color:#0f1729; font-weight:650}", 1),
        ("tbody tr:nth-child(even){background:rgba(255,255,255,.018)}",
         "tbody tr:nth-child(even){background:rgba(15,23,41,.028)}", 1),
        ("tbody tr:hover{background:rgba(90,169,230,.06)}",
         "tbody tr:hover{background:rgba(31,111,235,.07)}", 1),
        ('style="color:#fff"', 'style="color:#0f1729"', 1),
        # pre 用 --bg2（浅色下为白），补一层浅灰底与正文区分
        ("pre{\n  background:var(--bg2); border:1px solid var(--line); border-radius:8px;",
         "pre{\n  background:#fbfcfe; border:1px solid var(--line); border-radius:8px;", 1),
    ],
}


def main():
    ok = True
    for fn, subs in JOBS.items():
        with io.open(fn, "r", encoding="utf-8") as f:
            s = f.read()

        s2, n = DARK_ROOT_RE.subn(LIGHT_ROOT, s)
        assert n == 1, "%s :root 替换失败 (n=%d)" % (fn, n)

        for old, new, want in subs:
            cnt = s2.count(old)
            if cnt != want:
                ok = False
                print("[FAIL] %s | %r -> 期望 %d 次，实际 %d 次" % (fn, old[:48], want, cnt))
                continue
            s2 = s2.replace(old, new)
            print("[ok]   %s | %s" % (fn, old[:46].replace("\n", "\\n")))

        if not ok:
            continue
        with io.open(fn, "w", encoding="utf-8", newline="\n") as f:
            f.write(s2)
        print("== 已写入 %s (%d 字符)" % (fn, len(s2)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
