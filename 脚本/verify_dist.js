// dist/ 本地冒烟：Cesium 本地化 / 数据加载 / 矿点渲染 / 工艺图 / 零报错
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = process.env.DIST_URL || 'http://127.0.0.1:8741/index.html';

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
           '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const errs = [], fails = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('requestfailed', r => {
    if (!/favicon/.test(r.url())) fails.push(r.url() + ' :: ' + r.failure().errorText);
  });
  const bad = [];
  page.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url()); });

  await page.goto(URL, { waitUntil: 'load', timeout: 90000 });

  // 等 DEM 顶点构建完成
  await page.waitForFunction(
    () => document.querySelector('#loadMsg') && /顶点|就绪|完成/.test(document.querySelector('#loadMsg').textContent),
    { timeout: 120000 }
  ).catch(() => {});
  await page.waitForTimeout(5000);

  const r = await page.evaluate(() => {
    const imgs = [...document.querySelectorAll('img.procimg')];
    return {
      title: document.title,
      cesiumVersion: typeof Cesium !== 'undefined' ? Cesium.VERSION : null,
      cesiumBase: typeof CESIUM_BASE_URL !== 'undefined' ? CESIUM_BASE_URL : null,
      hasDem: typeof window.DEM_DATA !== 'undefined' && !!window.DEM_DATA,
      points: (typeof pointScore !== 'undefined' && pointScore) ? pointScore.length
            : (typeof window.pointScore !== 'undefined' && window.pointScore) ? window.pointScore.length : -1,
      entities: typeof viewer !== 'undefined' ? viewer.entities.values.length : -1,
      loadMsg: document.querySelector('#loadMsg') ? document.querySelector('#loadMsg').textContent.trim() : null,
      procImgs: imgs.length,
      procLoaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length
    };
  });

  // 展开工艺画廊，确认图片真的能加载
  await page.evaluate(() => {
    const h = document.querySelector('#procToggle') || document.querySelector('.proc-head');
    if (h) h.click();
  }).catch(() => {});
  await page.waitForTimeout(1500);
  const r2 = await page.evaluate(() => {
    const imgs = [...document.querySelectorAll('img.procimg')];
    return { n: imgs.length, ok: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
             src0: imgs[0] ? imgs[0].currentSrc || imgs[0].src : null };
  });

  await page.screenshot({ path: '可视化/dist_local.png' });

  console.log('--- 页面状态 ---');
  console.log(JSON.stringify(r, null, 1));
  console.log('工艺图:', JSON.stringify(r2));
  const realErrs = errs.filter(e => !/favicon|fonts\.googleapis|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION/.test(e));
  console.log('控制台错误:', realErrs.length ? realErrs.slice(0, 6) : '无');
  console.log('请求失败:', fails.length ? fails.slice(0, 6) : '无');
  console.log('HTTP>=400:', bad.length ? bad.slice(0, 8) : '无');

  const ok = r.cesiumVersion && r.hasDem && r2.ok >= 1 && realErrs.length === 0 && bad.length === 0;
  console.log(ok ? '\nPASS' : '\nFAIL');
  await browser.close();
})();
