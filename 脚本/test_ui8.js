// UI8 冒烟测试：工艺卡精准导航 + 画廊折叠
const path = require('path');
const { chromium } = require('playwright-core');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = 'http://127.0.0.1:8731/' + encodeURIComponent('赣南矿脉_数字孪生大屏.html');

(async () => {
  const errs = [];
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist',
           '--disable-gpu-sandbox', '--enable-unsafe-swiftshader']
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('PAGEERR: ' + e.message));

  await page.goto(URL, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(3500); // 等 Cesium 初始化 + loader 隐藏

  // 1) 工艺卡数量 & 图片加载
  const cards = await page.$$eval('#procList .proccard', els => els.length);
  const imgsOk = await page.$$eval('#procList .proccard img',
    els => els.filter(e => e.complete && e.naturalWidth > 0).length);
  console.log('PROC_CARDS=' + cards, 'IMGS_OK=' + imgsOk);

  // 2) 点击第一张卡 -> 精准落点(龙南 114.7048,24.9722)
  await page.click('#procList .proccard[data-g="1"]');
  await page.waitForTimeout(3500); // 等飞行 2.2s + 弹窗 1.5s
  const cam = await page.evaluate(() => {
    const c = viewer.camera.position;
    const cart = Cesium.Cartographic.fromCartesian(c);
    return { lon: cart.longitude * 180 / Math.PI, lat: cart.latitude * 180 / Math.PI };
  });
  const dLon = Math.abs(cam.lon - 114.7048), dLat = Math.abs(cam.lat - 24.9722);
  console.log('CAM_AFTER_CLICK lon=' + cam.lon.toFixed(4) + ' lat=' + cam.lat.toFixed(4) +
              ' dLon=' + dLon.toFixed(4) + ' dLat=' + dLat.toFixed(4));
  const popupShown = await page.$eval('#popup', e => e.classList.contains('show'));
  console.log('PROC_POPUP_SHOWN=' + popupShown);

  // 3) 折叠 toggle
  await page.click('#procSecT');
  await page.waitForTimeout(400);
  const collapsed = await page.$eval('#procSec', e => e.classList.contains('collapsed'));
  const listHidden = await page.$eval('#procList', e => getComputedStyle(e).display === 'none');
  console.log('COLLAPSED=' + collapsed, 'LIST_HIDDEN=' + listHidden);
  // 再点展开
  await page.click('#procSecT');
  await page.waitForTimeout(300);
  const expanded = await page.$eval('#procSec', e => !e.classList.contains('collapsed'));
  console.log('EXPANDED_AGAIN=' + expanded);

  // 截图
  await page.screenshot({ path: '可视化/ui8_collapsed.png' });

  await browser.close();

  // 判定
  const ok = cards === 4 && imgsOk === 4 && popupShown &&
             dLon < 0.06 && dLat < 0.15 && collapsed && listHidden && expanded &&
             errs.length === 0;
  console.log('ERRS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  console.log(ok ? 'UI8 PASS' : 'UI8 FAIL');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
