// UI9 冒烟测试：矿点光标贴地 + 弹窗导航时消失
const path = require('path');
const { chromium } = require('playwright-core');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = 'http://127.0.0.1:8731/' + encodeURIComponent('赣南矿脉_数字孪生大屏.html');

(async () => {
  const errs = [];
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist',
           '--disable-gpu-sandbox', '--enable-unsafe-swiftshader']
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('PAGEERR: ' + e.message));

  await page.goto(URL, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(3500);

  // 1) 点标贴地: markerEnts[0] 的 height 应 ≈ surfaceH + 6 (而非 base+1200)
  const m = await page.evaluate(() => {
    const e = markerEnts[0];
    const pos = e.position.getValue(viewer.clock.currentTime);
    const cart = Cesium.Cartographic.fromCartesian(pos);
    const lon = cart.longitude * 180 / Math.PI, lat = cart.latitude * 180 / Math.PI;
    const h = cart.height;
    const ground = surfaceH(lon, lat, 0);
    return { diff: h - ground, lon: lon, lat: lat, ground: ground };
  });
  console.log('MARKER_DIFF=' + m.diff.toFixed(1) + 'm (期望≈6, 原bug≈1200)');

  // 2) 点工艺卡 -> 弹窗显示
  await page.click('#procList .proccard[data-g="1"]');
  await page.waitForTimeout(3200);
  const p1 = await page.$eval('#popup', e => e.classList.contains('show'));
  console.log('POPUP_AFTER_CLICK1=' + p1);

  // 3) 点地图空白(canvas 中部偏右下, 避开左右面板与居中 popup) -> 弹窗消失
  await page.mouse.click(1300, 650);
  await page.waitForTimeout(400);
  const pHidden = await page.$eval('#popup', e => !e.classList.contains('show'));
  console.log('POPUP_HIDDEN_ON_BLANK=' + pHidden);

  // 4) 再点另一张卡 -> 飞行中旧窗格消失, 飞完新窗格显示
  await page.click('#procList .proccard[data-g="3"]');
  await page.waitForTimeout(80);    // click 同步触发 flyToProc -> hidePopup
  const pSync = await page.$eval('#popup', e => !e.classList.contains('show'));
  await page.waitForTimeout(3200);  // 飞完, showProcPopup 显示
  const p2 = await page.$eval('#popup', e => e.classList.contains('show'));
  console.log('POPUP_HIDDEN_SYNC=' + pSync, 'POPUP_AFTER_CLICK2=' + p2);

  // 5) markerEnts 数量 = 408, 且随 points 开关可隐藏
  const cnt = await page.evaluate(() => markerEnts.length);
  console.log('MARKER_COUNT=' + cnt);

  await browser.close();
  const ok = Math.abs(m.diff) < 30 && p1 && pHidden && pSync && p2 && cnt === 408 && errs.length === 0;
  console.log('ERRS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  console.log(ok ? 'UI9 PASS' : 'UI9 FAIL');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
