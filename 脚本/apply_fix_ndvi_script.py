# -*- coding: utf-8 -*-
"""在 analysis_layers.js 脚本标签后插入 ndvi_data.js 引用（不依赖行首缩进）"""
P = '赣南矿脉_数字孪生大屏.html'
s = open(P, encoding='utf-8').read()
marker = 'analysis_layers.js"></script>'
assert s.count(marker) == 1, 'marker 出现 %d 次' % s.count(marker)
idx = s.index(marker)
nl = s.index('\n', idx)
s = s[:nl + 1] + '  <script src="ndvi_data.js"></script>\n' + s[nl + 1:]
open(P, 'w', encoding='utf-8').write(s)
print('done, 文件字符数', len(s))
