// UI10 验证：矿点贴地(高度≈地形顶面) + 弹窗导航稳定切换
const { chromium } = require('playwright-core');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = 'http://127.0.0.1:8731/%E8%B5%A3%E5%8D%97%E7%9F%BF%E8%84%89_%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E5%A4%A7%E5%B1%8F.html';

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ['--headless=new','--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist','--no-sandbox']
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errs = [];
  page.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('PAGEERR: '+e.message));
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(5000);

  // 1) 矿点 marker 高度 vs 地形真实顶面
  const m = await page.evaluate(() => {
    const pe = markerEnts[0];
    const pos = pe.position.getValue(Cesium.JulianDate.now());
    const cart = Cesium.Cartographic.fromCartesian(pos);
    const lon = Cesium.Math.toDegrees(cart.longitude), lat = Cesium.Math.toDegrees(cart.latitude);
    const markerH = cart.height;
    const topH = terrainTopH(lon, lat) + 4;
    const surfH = surfaceH(lon, lat, 0);
    return { markerH, topH, surfH, diffTop: Math.abs(markerH-topH), diffSurf: markerH - surfH, hasDDT: pe.point.disableDepthTestDistance !== undefined };
  });
  console.log('MARKER markerH=%s topH=%s diffTop=%s diffSurf=%s hasDDT=%s',
    m.markerH.toFixed(1), m.topH.toFixed(1), m.diffTop.toFixed(2), m.diffSurf.toFixed(1), m.hasDDT);

  // 2) 随 EXAG 联动：改夸张后 marker 高度应重新贴合
  await page.evaluate(() => {
    const rng = document.querySelector('#sExag');
    rng.value = '2.4';
    rng.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(900);
  const m2 = await page.evaluate(() => {
    const pe = markerEnts[0];
    const pos = pe.position.getValue(Cesium.JulianDate.now());
    const cart = Cesium.Cartographic.fromCartesian(pos);
    const lon = Cesium.Math.toDegrees(cart.longitude), lat = Cesium.Math.toDegrees(cart.latitude);
    return { diffTop: Math.abs(cart.height - (terrainTopH(lon, lat) + 4)) };
  });
  console.log('MARKER_AFTER_EXAG diffTop=%s', m2.diffTop.toFixed(2));
  await page.screenshot({ path: '可视化/ui10_attached.png' });

  // 还原 EXAG
  await page.evaluate(() => {
    const rng = document.querySelector('#sExag');
    rng.value = '1.6'; rng.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(700);

  // 3) 弹窗竞态：点卡1，飞行中(300ms后)点卡2，最终应只显示卡2，不残留卡1
  await page.click('#procList .proccard[data-g="1"]');
  await page.waitForTimeout(300);            // 卡1 飞行中
  await page.click('#procList .proccard[data-g="2"]');  // 立即点卡2
  await page.waitForTimeout(3200);           // 卡2 飞完
  const pop = await page.evaluate(() => {
    const pp = document.querySelector('#popup');
    return { show: pp.classList.contains('show'), title: document.querySelector('#ppTitle').textContent };
  });
  console.log('POPUP_AFTER_RACE show=%s title="%s"', pop.show, pop.title);
  const okRace = pop.show && /第2代/.test(pop.title) && !/第1代/.test(pop.title);

  // 4) 再点卡3，弹窗应切换到第3代
  await page.click('#procList .proccard[data-g="3"]');
  await page.waitForTimeout(3000);
  const pop3 = await page.evaluate(() => {
    const pp = document.querySelector('#popup');
    return { show: pp.classList.contains('show'), title: document.querySelector('#ppTitle').textContent };
  });
  console.log('POPUP_CARD3 show=%s title="%s"', pop3.show, pop3.title);
  const okSwitch = pop3.show && /第3代/.test(pop3.title);

  // 5) 点地图空白，弹窗消失（先在 canvas 上扫描一个真正落空的像素）
  const blank = await page.evaluate(() => {
    const sc = viewer.scene, w = window.innerWidth, h = window.innerHeight;
    for (let gy = 0.2; gy < 0.95; gy += 0.05){
      for (let gx = 0.2; gx < 0.8; gx += 0.05){
        const x = Math.round(w*gx), y = Math.round(h*gy);
        if (!sc.pick(new Cesium.Cartesian2(x, y))) return { x, y };
      }
    }
    return null;
  });
  console.log('BLANK_PIXEL=' + JSON.stringify(blank));
  if (blank){ await page.mouse.click(blank.x, blank.y); }
  await page.waitForTimeout(400);
  const hidden = await page.evaluate(() => !document.querySelector('#popup').classList.contains('show'));
  console.log('POPUP_HIDDEN_ON_BLANK=%s', hidden);

  const ok = m.diffTop < 1.5 && !m.hasDDT && m2.diffTop < 1.5 && okRace && okSwitch && hidden && errs.length === 0;
  console.log('RESULT ' + (ok ? 'PASS' : 'FAIL') + ' errs=' + errs.length);
  if (errs.length) console.log(errs.slice(0,5).join('\n'));
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
