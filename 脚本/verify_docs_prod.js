// 线上 docs 子页冒烟
const { chromium } = require('playwright-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'https://dcd63df0dc9844bb8e3f492abb3e65eb.app.workbuddy.link/docs/';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1180, height: 760 } });
  const errs = [], bad = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url()); });
  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await page.waitForTimeout(800);
  const r = await page.evaluate(() => ({
    title: document.title, links: [...document.querySelectorAll('a[href$=".html"]')].map(a => a.getAttribute('href'))
  }));
  await page.screenshot({ path: '可视化/docs_prod.png' });
  console.log(JSON.stringify(r));
  console.log('errors:', errs.length, 'bad:', bad.length);
  await browser.close();
})();