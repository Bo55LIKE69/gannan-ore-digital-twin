// UI5 冒烟测试：验证 NDVI 已移除、地表锚点已移除、DEM 配色多选可切换、图例色带同步
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const FILE = encodeURIComponent('赣南矿脉_数字孪生大屏.html');
const URL = 'http://127.0.0.1:8731/' + FILE;

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
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
  await page.waitForTimeout(4000); // 让 Cesium 渲染若干帧

  const before = await page.evaluate(() => ({
    hasPalSel: !!document.getElementById('palSel'),
    palOpts: document.getElementById('palSel')
      ? Array.from(document.getElementById('palSel').options).map(o => o.value) : [],
    ndviDefined: (typeof window.NDVI_DATA !== 'undefined'),
    swPin: !!document.getElementById('swPin'),
    rampBg: document.querySelector('.ramp') ? document.querySelector('.ramp').style.background : '',
    rl0: document.getElementById('rl0') ? document.getElementById('rl0').textContent : '',
    rl1: document.getElementById('rl1') ? document.getElementById('rl1').textContent : '',
    demPalUniform: (window.terrainUniforms ? window.terrainUniforms.u_demPal : 'NO_UNIFORM')
  }));
  console.log('BEFORE ' + JSON.stringify(before));

  await page.selectOption('#palSel', 'elev');
  await page.waitForTimeout(900);
  const elev = await page.evaluate(() => ({
    demPalUniform: window.terrainUniforms ? window.terrainUniforms.u_demPal : 'NO',
    rampBg: document.querySelector('.ramp').style.background.slice(0, 70)
  }));
  console.log('AFTER_ELEV ' + JSON.stringify(elev));
  await page.screenshot({ path: '可视化/ui5_elev.png' });

  await page.selectOption('#palSel', 'gray');
  await page.waitForTimeout(700);
  const gray = await page.evaluate(() => ({
    demPalUniform: window.terrainUniforms ? window.terrainUniforms.u_demPal : 'NO',
    rampBg: document.querySelector('.ramp').style.background.slice(0, 70)
  }));
  console.log('AFTER_GRAY ' + JSON.stringify(gray));
  await page.screenshot({ path: '可视化/ui5_gray.png' });

  // 回到默认地形配色做总览截图
  await page.selectOption('#palSel', 'terrain');
  await page.waitForTimeout(700);
  await page.screenshot({ path: '可视化/ui5_default.png' });

  console.log('ERRORS count=' + errors.length + ' ' + JSON.stringify(errors.slice(0, 12)));
  await browser.close();
  // 判定
  const ok = before.hasPalSel && before.palOpts.length === 4 && !before.ndviDefined &&
             !before.swPin && before.rl0 && before.rl1 &&
             before.demPalUniform === 0 && elev.demPalUniform === 1 && gray.demPalUniform === 2 &&
             errors.length === 0;
  console.log('RESULT ' + (ok ? 'PASS' : 'FAIL'));
  process.exit(ok ? 0 : 2);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
