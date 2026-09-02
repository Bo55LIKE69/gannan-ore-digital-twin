// UI7 验证：工艺画廊渲染、图片加载、点卡片飞行无异常
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const FILE = encodeURIComponent('赣南矿脉_数字孪生大屏.html');
const URL = 'http://127.0.0.1:8731/' + FILE;

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
           '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  page.on('pageerror', e => errors.push('PAGEERR: ' + e.message));

  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(6000);

  const r = await page.evaluate(() => {
    const cards = document.querySelectorAll('#procList .proccard');
    const imgs = [...document.querySelectorAll('#procList .procimg')];
    const loaded = imgs.filter(i => i.complete && i.naturalWidth > 0).length;
    return {
      cardCount: cards.length,
      imgCount: imgs.length,
      imgLoaded: loaded,
      firstSrc: imgs[0] ? imgs[0].getAttribute('src') : null,
      rightPanelHasChapter: !!document.querySelector('.chapter'),
      rightPanelHasChTabs: !!document.querySelector('.chtabs'),
      hint: document.getElementById('hint') ? document.getElementById('hint').textContent : null
    };
  });

  await page.click('#procList .proccard');
  await page.waitForTimeout(3500);
  await page.screenshot({ path: '可视化/ui7_gallery.png' });

  const realErrors = errors.filter(e => !/swiftshader|Y6|GL_|WebGL|THREE|GPU stall/i.test(e));
  console.log(JSON.stringify({ ...r, errors: realErrors }, null, 2));

  const ok = r.cardCount === 4 && r.imgCount === 4 && r.imgLoaded === 4
    && !r.rightPanelHasChapter && !r.rightPanelHasChTabs
    && !r.hint.includes('切换章节') && realErrors.length === 0;
  console.log(ok ? 'PASS' : 'FAIL');
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('RUNNER ERR', e); process.exit(2); });
