const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://localhost:5173/register');
  await page.evaluate(() => {
    document.querySelector('input#email').removeAttribute('required');
    document.querySelector('input#password').removeAttribute('required');
    document.querySelector('input#username').removeAttribute('required');
  });
  await page.fill('input#username', 'testuser422');
  await page.fill('input#password', 'password');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(2000);
  console.log(await page.content());
  await browser.close();
})();
