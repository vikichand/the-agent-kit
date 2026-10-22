// Renders assets/banner.html to assets/banner-dark.png and assets/banner-light.png at 2x.
// Usage: node assets/render-banner.js
// Needs puppeteer; set PUPPETEER to its path if it is not resolvable from here.
const path = require('path');
const puppeteer = require(process.env.PUPPETEER || 'puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  for (const theme of ['dark', 'light']) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 356, deviceScaleFactor: 2 });
    await page.goto('file://' + path.join(__dirname, 'banner.html') + (theme === 'light' ? '#light' : ''));
    const card = await page.$('.card');
    await card.screenshot({ path: path.join(__dirname, `banner-${theme}.png`), omitBackground: true });
    await page.close();
  }
  await browser.close();
})();
