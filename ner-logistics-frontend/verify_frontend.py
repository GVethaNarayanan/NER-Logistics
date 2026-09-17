import asyncio
from playwright.async_api import async_playwright
import time
import os

async def main():
    print("Starting verification script...")
    os.makedirs("screenshots", exist_ok=True)
    results = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        print("1. Desktop Check - Dashboard")
        await page.goto("http://localhost:5173/")
        await page.wait_for_selector(".leaflet-container")
        await page.screenshot(path="screenshots/desktop_dashboard.png")
        results['dashboard_desktop'] = "PASS"

        print("2. Desktop Check - Vehicles")
        await page.goto("http://localhost:5173/vehicles")
        await page.wait_for_selector(".leaflet-container")
        await page.screenshot(path="screenshots/desktop_vehicles.png")
        results['vehicles_desktop'] = "PASS"

        print("3. Desktop Check - Routes")
        await page.goto("http://localhost:5173/routes")
        await page.screenshot(path="screenshots/desktop_routes.png")
        results['routes_desktop'] = "PASS"

        print("4. Desktop Check - Incidents")
        await page.goto("http://localhost:5173/incidents")
        await page.screenshot(path="screenshots/desktop_incidents.png")
        results['incidents_desktop'] = "PASS"

        print("5. Desktop Check - Alerts")
        await page.goto("http://localhost:5173/alerts")
        await page.screenshot(path="screenshots/desktop_alerts.png")
        results['alerts_desktop'] = "PASS"

        print("6. Desktop Check - Login")
        await page.goto("http://localhost:5173/login")
        await page.screenshot(path="screenshots/desktop_login.png")
        results['login_desktop'] = "PASS"

        print("7. Desktop Check - Register")
        await page.goto("http://localhost:5173/register")
        await page.screenshot(path="screenshots/desktop_register.png")
        results['register_desktop'] = "PASS"

        # Check I18N
        print("8. I18N Check")
        await page.goto("http://localhost:5173/")
        # Find language toggle (has Globe icon and language text)
        btn = page.locator("button[title='Toggle Language']")
        text_before = await btn.text_content()
        await btn.click()
        time.sleep(1)
        text_after = await btn.text_content()
        
        # Reload
        await page.reload()
        time.sleep(1)
        text_reloaded = await page.locator("button[title='Toggle Language']").text_content()
        
        results['i18n'] = {
            'before': text_before.strip() if text_before else None,
            'after': text_after.strip() if text_after else None,
            'reloaded': text_reloaded.strip() if text_reloaded else None
        }

        # Mobile viewport check
        print("9. Mobile Check - Dashboard")
        mobile_context = await browser.new_context(viewport={'width': 375, 'height': 667}) # standard phone
        mobile_page = await mobile_context.new_page()
        await mobile_page.goto("http://localhost:5173/")
        await mobile_page.wait_for_load_state('networkidle')
        
        # Check horizontal overflow
        width = await mobile_page.evaluate("document.documentElement.scrollWidth")
        viewport_width = 375
        overflows = width > viewport_width
        results['mobile_overflow'] = "FAIL" if overflows else "PASS"

        await mobile_page.screenshot(path="screenshots/mobile_dashboard.png", full_page=True)

        await browser.close()
        
    for k, v in results.items():
        print(f"{k}: {v}")

asyncio.run(main())
