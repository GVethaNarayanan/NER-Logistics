const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle0' });
  await page.type('input[id="username"]', 'admin');
  await page.type('input[id="password"]', 'admin_dev_password');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0' }),
    page.click('button[type="submit"]'),
  ]);
  await page.goto('http://localhost:5173/routes', { waitUntil: 'networkidle0' });
  console.log(await page.content());
  await browser.close();
})();
