// 核查：矿点是否渲染、数量、报错
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
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERR: ' + e.message));

  await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
  await page.waitForFunction(
    () => window.DEM_DATA && document.querySelector('#loadMsg') &&
          /顶点/.test(document.querySelector('#loadMsg').textContent),
    { timeout: 90000 }
  ).catch(() => {});
  await page.waitForTimeout(4500);

  const info = await page.evaluate(() => ({
    psExists: (typeof window.POINT_SCORE !== 'undefined'),
    psPtsLen: (window.POINT_SCORE && window.POINT_SCORE.pts) ? window.POINT_SCORE.pts.length : -1,
    pointEntsLen: (typeof pointEnts !== 'undefined') ? pointEnts.length : -1,
    visiblePts: (typeof pointEnts !== 'undefined') ? pointEnts.filter(e => e.show).length : -1,
    layerPoints: (typeof LAYER !== 'undefined') ? LAYER.points : null,
    activeCats: (typeof activeCats !== 'undefined') ? JSON.stringify(activeCats) : null,
    swPointsOn: document.getElementById('swPoints') ? document.getElementById('swPoints').classList.contains('on') : null
  }));
  console.log('INFO ' + JSON.stringify(info, null, 0));

  // 飞行到赣州中心近景看矿点
  await page.evaluate(() => {
    if (window.viewer) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(114.93, 25.85, 120000),
        orientation: { heading: 0, pitch: -1.1, roll: 0 }, duration: 0
      });
    }
  });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: '可视化/check_points.png' });

  console.log('ERRORS count=' + errors.length + ' ' + JSON.stringify(errors.slice(0, 12)));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
