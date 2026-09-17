const { chromium } = require('playwright');

(async () => {
  console.log('Starting Playwright for Real Browser Verification of Alerts...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // 1. Authenticate as Admin
    console.log('1. Navigating to login...');
    await page.goto('http://localhost:5173/login');
    
    // We will try admin / admin_dev_password
    await page.fill('#username', 'admin');
    await page.fill('#password', 'admin_dev_password');
    await page.click('button:has-text("Sign In")');
    
    // Wait for success (redirect to /)
    await page.waitForURL('http://localhost:5173/', { timeout: 10000 });
    console.log('Logged in as admin.');

    // 2. Navigate to Alerts
    console.log('2. Navigating to Alerts panel...');
    await page.goto('http://localhost:5173/alerts');
    await page.waitForSelector('text=System Alerts');

    // 3. Admin can see "New Alert" button
    console.log('3. Checking for New Alert button...');
    try {
      const newAlertBtn = await page.waitForSelector('button:has-text("New Alert")', { timeout: 10000 });
      if (!newAlertBtn) throw new Error("Button returned null");
    } catch (e) {
      await page.screenshot({ path: 'alerts_failed.png' });
      throw new Error("New Alert button not found for admin! See alerts_failed.png");
    }
    const newAlertBtn = await page.$('button:has-text("New Alert")');
    
    // 4. Create an Alert
    console.log('4. Creating a manual alert...');
    await newAlertBtn.click();
    await page.waitForSelector('text=Create Manual Alert');
    
    const uniqueMsg = `Playwright Test Alert ${Date.now()}`;
    const selects = await page.locator('select').all();
    // 0: Filter Status, 1: Filter Severity, 2: Modal Type, 3: Modal Severity
    await selects[2].selectOption('infrastructure');
    await selects[3].selectOption('high');
    
    await page.fill('textarea[placeholder*="E.g."]', uniqueMsg);
    await page.fill('textarea[placeholder*="Local translation"]', 'Locale msg');
    
    await page.click('button:has-text("Create Alert")');
    
    // Wait for modal to close
    await page.waitForSelector('text=Create Manual Alert', { state: 'hidden' });
    console.log('Alert created successfully.');

    // 5. Verify the alert appears in the list
    console.log('5. Verifying alert appears in the list...');
    await page.waitForSelector(`text=${uniqueMsg}`);
    console.log('Alert found in list!');

    // 6. Verify severity display
    console.log('6. Verifying severity display (HIGH)...');
    const severityBadge = await page.locator(`div:has-text("${uniqueMsg}") >> text=high`);
    if (await severityBadge.count() > 0) {
      console.log('Severity badge found.');
    } else {
      throw new Error('Severity badge not found on new alert!');
    }

    // 7. Verify non-admin cannot access create
    console.log('7. Verifying non-admin access...');
    // Logout and login as standard (field official)
    await page.evaluate(() => localStorage.clear());
    await page.evaluate(() => sessionStorage.clear());
    await page.goto('http://localhost:5173/login');
    await page.fill('#username', 'test_field_official');
    await page.fill('#password', 'password123');
    await page.click('button:has-text("Sign In")');
    await page.waitForURL('http://localhost:5173/');
    
    await page.goto('http://localhost:5173/alerts');
    await page.waitForSelector('text=System Alerts');
    
    const newAlertBtnStandard = await page.locator('button:has-text("New Alert")');
    if (await newAlertBtnStandard.count() > 0) {
      throw new Error('Standard user can see New Alert button!');
    }
    console.log('Standard user correctly denied access to creation UI.');

    console.log('All real browser verifications passed!');
    
  } catch (error) {
    console.error('Test Failed:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
