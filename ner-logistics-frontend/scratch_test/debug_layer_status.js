const { chromium } = require('playwright');

(async () => {
    console.log("Starting network capture on Dashboard...");
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    page.on('response', async (response) => {
        const status = response.status();
        if (status >= 400) {
            const request = response.request();
            console.log("\n==============================");
            console.log("FAILURE DETECTED");
            console.log("Method:", request.method());
            console.log("URL:", request.url());
            console.log("Post Data:", request.postData() || "None");
            console.log("Status Code:", status);
            try {
                const body = await response.json();
                console.log("Response JSON:", JSON.stringify(body, null, 2));
            } catch (e) {
                const text = await response.text();
                console.log("Response Text:", text);
            }
            console.log("==============================\n");
        }
    });

    try {
        await page.goto('http://localhost:5173/');
        // Wait for leaflet container to ensure Dashboard is fully loaded and API calls are made
        await page.waitForSelector('.leaflet-container', { timeout: 10000 });
        // Wait a bit more for background API calls (like Layer Status)
        await page.waitForTimeout(3000);
        console.log("Capture complete.");
    } catch (e) {
        console.error("Error during page load:", e);
    } finally {
        await browser.close();
    }
})();
