// 线上站点冒烟：部署链接 /index.html
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = process.env.PROD_URL || 'https://dcd63df0dc9844bb8e3f492abb3e65eb.app.workbuddy.link/';

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
           '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const errs = [], fails = [], bad = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('requestfailed', r => {
    if (!/favicon|fonts\.googleapis/.test(r.url())) fails.push(r.url() + ' :: ' + r.failure().errorText);
  });
  page.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url()); });

  await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
  await page.waitForFunction(
    () => document.querySelector('#loadMsg') && /顶点|就绪|完成/.test(document.querySelector('#loadMsg').textContent),
    { timeout: 150000 }
  ).catch(() => {});
  await page.waitForTimeout(6000);

  const r = await page.evaluate(() => ({
    title: document.title,
    cesiumVersion: typeof Cesium !== 'undefined' ? Cesium.VERSION : null,
    hasDem: typeof window.DEM_DATA !== 'undefined' && !!window.DEM_DATA,
    entities: typeof viewer !== 'undefined' ? viewer.entities.values.length : -1,
    loadMsg: document.querySelector('#loadMsg') ? document.querySelector('#loadMsg').textContent.trim() : null,
    procImgs: [...document.querySelectorAll('img.procimg')].filter(i => i.complete && i.naturalWidth > 0).length
  }));
  await page.screenshot({ path: '可视化/dist_prod.png' });

  const realErrs = errs.filter(e => !/favicon|fonts\.googleapis|ERR_NAME|ERR_CONNECTION|net::/.test(e));
  console.log(JSON.stringify(r, null, 1));
  console.log('控制台错误:', realErrs.length ? realErrs.slice(0, 5) : '无');
  console.log('请求失败:', fails.length ? fails.slice(0, 5) : '无');
  console.log('HTTP>=400:', bad.length ? bad.slice(0, 6) : '无');
  console.log(realErrs.length === 0 && bad.length === 0 && r.cesiumVersion && r.hasDem ? 'PASS' : 'FAIL');
  await browser.close();
})();