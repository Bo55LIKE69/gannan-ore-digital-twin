// 浅色矿图风核查：截图 + 残留深色/低对比度检测
const { chromium } = require('playwright-core');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const FILE = encodeURIComponent('赣南矿脉_数字孪生大屏.html');
const URL = 'http://127.0.0.1:8731/' + FILE;

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
           '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']
  });
  const errors = [];
  for (const vp of [{w:1600,h:900,tag:'pc'},{w:390,h:844,tag:'mobile'}]) {
    const page = await browser.newPage({ viewport: { width: vp.w, height: vp.h } });
    page.on('console', m => { if (m.type() === 'error') errors.push(vp.tag+': '+m.text()); });
    page.on('pageerror', e => errors.push(vp.tag+' PAGEERR: ' + e.message));
    await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
    await page.waitForFunction(
      () => window.DEM_DATA && document.querySelector('#loadMsg') &&
            /顶点/.test(document.querySelector('#loadMsg').textContent),
      { timeout: 90000 }).catch(() => {});
    await page.waitForTimeout(5000);
    await page.screenshot({ path: `可视化/light_${vp.tag}.png` });
    const info = await page.evaluate(() => {
      const cs = getComputedStyle(document.body);
      const panel = document.querySelector('.panel');
      const pcs = panel ? getComputedStyle(panel) : null;
      return {
        bg: cs.backgroundColor,
        color: cs.color,
        panelBg: pcs ? pcs.backgroundColor : null,
        hasGraticule: !!document.querySelector('.graticule'),
        hasContourTint: !!document.querySelector('.contourTint' || '.contour-tint'),
        contourBg: (function(){ const e=document.querySelector('.contour-tint'); return e?e.style.backgroundImage.slice(0,40):null; })(),
        rulerTicks: document.querySelectorAll('#lonRuler i').length,
        scaleLabel: (document.getElementById('sbLabel')||{}).textContent,
        pointCount: (typeof pointEnts !== 'undefined') ? pointEnts.length : -1
      };
    });
    console.log(vp.tag.toUpperCase() + ' ' + JSON.stringify(info));
    if (vp.tag === 'pc') await page.close(); else await page.close();
  }
  console.log('ERRORS count=' + errors.length + ' ' + JSON.stringify(errors.slice(0, 6)));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
