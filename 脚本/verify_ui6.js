// UI6 核查：矿点仍在、整体离地抬升控件已移除、无致命报错
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
    pointEntsLen: (typeof pointEnts !== 'undefined') ? pointEnts.length : -1,
    visiblePts: (typeof pointEnts !== 'undefined') ? pointEnts.filter(e => e.show).length : -1,
    sLiftExists: !!document.getElementById('sLift'),
    vLiftExists: !!document.getElementById('vLift'),
    swPointsOn: document.getElementById('swPoints') ? document.getElementById('swPoints').classList.contains('on') : null,
    LIFT_DEFINED: (typeof LIFT !== 'undefined')
  }));
  console.log('INFO ' + JSON.stringify(info));
  console.log('ERRORS count=' + errors.length + ' ' + JSON.stringify(errors.slice(0, 8)));

  const ok = info.pointEntsLen === 408 && info.visiblePts === 408 &&
             !info.sLiftExists && !info.vLiftExists && !info.LIFT_DEFINED;
  console.log('RESULT ' + (ok ? 'PASS' : 'FAIL'));
  await browser.close();
  process.exit(ok ? 0 : 2);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
