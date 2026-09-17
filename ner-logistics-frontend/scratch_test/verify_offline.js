const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  console.log('Starting Playwright for Real Browser Verification...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('1. Opening Incident page...');
  await page.goto('http://localhost:5173/login');

  // Login as admin or field_official
  await page.fill('#username', 'test_field_official');
  await page.fill('#password', 'password123');
  await page.click('button:has-text("Sign In")');
  await page.waitForTimeout(2000); // Wait for auth

  await page.click('a:has-text("Incidents")');
  await page.waitForTimeout(1000);
  console.log('Incident page loaded and authenticated.');

  console.log('2. Enabling DevTools Network -> Offline...');
  await context.setOffline(true);

  console.log('3. Submitting an incident with a photo (Offline)...');
  await page.fill('textarea', 'Offline test incident ' + Date.now());
  
  // Pick location
  await page.click('button:has-text("Pick on Map")');
  await page.waitForTimeout(500);
  await page.locator('.leaflet-container').click({ position: { x: 100, y: 100 } });
  await page.waitForTimeout(500);

  // Upload photo
  const dummyPhotoPath = path.join(__dirname, 'dummy.png');
  fs.writeFileSync(dummyPhotoPath, 'fake photo content');
  await page.setInputFiles('input[type="file"]', dummyPhotoPath);

  // Submit
  await page.click('button:has-text("Submit Incident")');
  await page.waitForTimeout(2000);

  page.on('console', msg => console.log('BROWSER: ' + msg.text()));

  console.log('4. Confirming incident is persisted in IndexedDB...');
  await page.waitForTimeout(2000);
  
  let checkQueue = async () => {
    return await page.evaluate(async () => {
      return new Promise((resolve, reject) => {
        const req = window.indexedDB.open('NerLogisticsOfflineDB');
        req.onsuccess = (e) => {
          const db = e.target.result;
          if (!db.objectStoreNames.contains('incidents_queue')) return resolve([]);
          const tx = db.transaction('incidents_queue', 'readonly');
          const store = tx.objectStore('incidents_queue');
          const getReq = store.getAll();
          getReq.onsuccess = () => resolve(getReq.result);
        };
        req.onerror = reject;
      });
    });
  };

  let queue = await checkQueue();
  console.log(`Offline Queue count: ${queue.length}`);

  console.log('5. Simulating network disconnect and reconnect instead of page reload (Vite Dev Server limitation)...');
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.waitForTimeout(2000);

  console.log('5. Setting up interception before reconnecting...');
  // Intercept the uploadPhoto to force a failure using wildcard to ensure it catches it
  await page.route('**/photo', route => {
    console.log('Simulating photo upload failure!');
    route.abort('failed');
  });

  console.log('6. Re-enabling network and triggering auto-sync...');
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  
  console.log('7. Waiting for auto-sync to process...');
  await page.waitForTimeout(4000);

  console.log('8/9/10/11/12. Checking state after incident success but photo failure...');
  let queueState = await checkQueue();
  
  if (queueState.length > 0) {
    const item = queueState[0];
    console.log(`Incident ID acquired: ${item.serverId}`);
    console.log(`Payload cleared? ${item.payload === null}`);
    console.log(`Photo remains? ${item.photo !== null}`);
    console.log(`Error message: ${item.lastError}`);
  } else {
    console.log('QUEUE IS EMPTY! This should not happen if photo failed.');
  }

  console.log('13. Simulating mixed valid/invalid batch...');
  // Add a valid and invalid incident to the DB directly for test
  await page.evaluate(async () => {
    return new Promise((resolve, reject) => {
      const req = window.indexedDB.open('NerLogisticsOfflineDB');
      req.onsuccess = (e) => {
        const db = e.target.result;
        const tx = db.transaction('incidents_queue', 'readwrite');
        const store = tx.objectStore('incidents_queue');
        store.put({
          localId: 'valid-123',
          payload: { incident_type: 'accident', severity: 'low', latitude: 26, longitude: 91 },
          photo: null,
          status: 'pending',
          retryCount: 0
        });
        // road_id 99999 violates backend validation probably, or we just put a weird lat/long
        // The backend `schemas.IncidentCreate` enforces `severity` is Literal['low', 'medium', 'high']
        store.put({
          localId: 'invalid-456',
          payload: { incident_type: 'accident', severity: 'EXTREME', latitude: 26, longitude: 91 },
          photo: null,
          status: 'pending',
          retryCount: 0
        });
        tx.oncomplete = () => resolve();
      };
      req.onerror = reject;
    });
  });
  
  // Unroute the photo so normal requests work
  await page.unroute('**/photo');
  
  console.log('Syncing mixed batch...');
  await page.click('button:has-text("Sync Now")');
  await page.waitForTimeout(3000);

  let finalQueue = await checkQueue();
  
  console.log(`Final Queue size: ${finalQueue.length}`);
  finalQueue.forEach((q, i) => {
    console.log(`Item ${i}: status=${q.status}, error=${q.lastError}, serverId=${q.serverId}`);
  });

  await browser.close();
  console.log('Done!');
})();
