// 三份文档浅色主题截图核验
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const path = require('path');
const ROOT = 'E:\\Data\\赣州稀土';

const FILES = ['技术复盘与学习指南.html', '后端与数据库演进方案.html', 'AI时代学代码指南.html'];
const OUT = ['可视化/doc_guide.png', '可视化/doc_plan.png', '可视化/doc_ai.png'];

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true, args: ['--no-sandbox']
  });
  const page = await browser.newPage({ viewport: { width: 1180, height: 900 } });
  for (let i = 0; i < FILES.length; i++) {
    await page.goto('file:///' + path.join(ROOT, FILES[i]).replace(/\\/g, '/'), { waitUntil: 'load' });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(ROOT, OUT[i]) });
    // 顺便核对计算后的背景/文字色
    const c = await page.evaluate(() => {
      const b = getComputedStyle(document.body);
      const p = document.querySelector('p');
      const pre = document.querySelector('pre code');
      return {
        bodyBg: b.backgroundColor, bodyColor: b.color,
        pColor: p ? getComputedStyle(p).color : null,
        preColor: pre ? getComputedStyle(pre).color : null
      };
    });
    console.log(FILES[i], JSON.stringify(c));
  }
  await browser.close();
})();
