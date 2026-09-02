// 多高度截图看矿点可见性
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
  await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
  await page.waitForFunction(
    () => window.DEM_DATA && document.querySelector('#loadMsg') &&
          /顶点/.test(document.querySelector('#loadMsg').textContent),
    { timeout: 90000 }
  ).catch(() => {});
  await page.waitForTimeout(4500);

  // 1) 全览（默认相机，不移动）
  await page.screenshot({ path: '可视化/pt_overview.png' });

  // 2) 中景：赣州中心 350km
  await page.evaluate(() => viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(114.93, 25.85, 350000),
    orientation: { heading: 0, pitch: -1.0, roll: 0 }, duration: 0 }));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: '可视化/pt_mid.png' });

  // 3) 近景：120km
  await page.evaluate(() => viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(114.78, 25.68, 120000),
    orientation: { heading: 0, pitch: -1.15, roll: 0 }, duration: 0 }));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: '可视化/pt_near.png' });

  // 报告相机高度与矿点包围盒
  const cam = await page.evaluate(() => {
    var c = viewer.camera.positionCartographic;
    return { height: c.height.toFixed(0), lon: c.longitude.toFixed(3), lat: c.latitude.toFixed(3) };
  });
  console.log('CAM ' + JSON.stringify(cam));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
