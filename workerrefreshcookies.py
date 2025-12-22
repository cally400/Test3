import asyncio
from playwright.async_api import async_playwright
import json
import os

USERNAME = os.getenv("AGENT_USERNAME")
PASSWORD = os.getenv("AGENT_PASSWORD")

LOGIN_URL = "https://agents.ichancy.com/login"
COOKIES_FILE = "ichancy_cookies.json"


async def refresh_cookies():
    print("🚀 بدء عملية تجديد الكوكيز...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = await browser.new_context()
        page = await context.new_page()

        print("🌐 فتح صفحة تسجيل الدخول...")
        await page.goto(LOGIN_URL, timeout=60000)

        # تعبئة البيانات
        await page.fill('input[name="username"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)

        print("🔐 تسجيل الدخول...")
        await page.click('button[type="submit"]')

        # انتظار تجاوز Cloudflare + إعادة التوجيه
        print("⏳ انتظار اكتمال التحقق من Cloudflare...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(5)

        # 🔥 أهم خطوة: انتظار ظهور لوحة التحكم
        try:
            await page.wait_for_selector("div.dashboard", timeout=20000)
            print("🎉 تم تسجيل الدخول بنجاح!")
        except:
            print("❌ فشل تسجيل الدخول — لم تظهر لوحة التحكم")
            await browser.close()
            return

        # استخراج الكوكيز
        cookies = await context.cookies()

        # حفظ الكوكيز
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)

        print("✅ تم تحديث الكوكيز بنجاح!")
        print(f"📁 تم حفظ الكوكيز في: {COOKIES_FILE}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(refresh_cookies())
