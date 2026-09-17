const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle0' });
  
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle0' });
  await page.type('input[id="username"]', 'admin');
  await page.type('input[id="password"]', 'admin_dev_password');
  
  // click and wait for dashboard to load
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0' }),
    page.click('button[type="submit"]'),
  ]);
  
  await page.goto('http://localhost:5173/routes', { waitUntil: 'networkidle0' });
  
  await page.click('button[aria-label="Toggle Language"]');
  await new Promise(r => setTimeout(r, 1000));
  
  const h1 = await page.$eval('h1', el => el.textContent).catch(e => e.toString());
  console.log('H1 is:', h1);
  
  await browser.close();
})().catch(console.error);
