# -*- coding: utf-8 -*-
"""补删分析区残留的 NDVI 开关行。"""
import io
PATH = r"E:\Data\赣州稀土\赣南矿脉_数字孪生大屏.html"
s = io.open(PATH, "r", encoding="utf-8").read()
old = '    <div class="sw-row"><span>植被指数 NDVI</span><div class="sw" id="swAl_ndvi"></div></div>\n'
assert s.count(old) == 1, "NDVI sw-row count=%d" % s.count(old)
s = s.replace(old, "")
io.open(PATH, "w", encoding="utf-8").write(s)
print("OK: removed NDVI sw-row")
