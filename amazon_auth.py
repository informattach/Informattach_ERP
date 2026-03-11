import os
import sys
import asyncio
import random
from dotenv import load_dotenv
from playwright.async_api import Page
from otp_reader import get_latest_amazon_otp

load_dotenv()

STATE_FILE = os.path.join(os.path.dirname(__file__), "amazon_state.json")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

async def is_auth_page(p: Page) -> bool:
    try:
        ul = p.url.lower()
        if "/ap/signin" in ul or "/ap/challenge" in ul or "/ap/cvf/" in ul or "errors/validatecaptcha" in ul:
            return True
        if await p.locator("input[type='email'], input[type='password'], input[name='password']").count() > 0:
            if await p.locator("input[type='email']").first.is_visible() or await p.locator("input[type='password']").first.is_visible():
                return True
        if await p.locator("input[name='code'], input[name='cvf_captcha_input'], input[name='otpCode'], input#auth-mfa-otpcode").count() > 0:
            if await p.locator("input[name='code']").first.is_visible() or await p.locator("input[name='cvf_captcha_input']").first.is_visible() or await p.locator("input[name='otpCode']").first.is_visible() or await p.locator("input#auth-mfa-otpcode").first.is_visible():
                return True
        if "/dp/" not in ul and "/gp/product/" not in ul and "goldbox" not in ul and "/hz/wishlist/" not in ul:
            body_text = await p.locator("body").inner_text()
            body_lower = body_text.lower()
            if ("giriş yapmak" in body_lower or "sign in to" in body_lower or "lütfen giriş yap" in body_lower):
                gw_links = await p.locator("a[href*='/ap/signin']").all()
                for link in gw_links:
                    id_attr = await link.get_attribute("id")
                    if id_attr and "nav-link" not in id_attr and await link.is_visible():
                        return True
        return False
    except Exception:
        return False

async def ensure_logged_in(page: Page, target_url: str = "https://www.amazon.com/"):
    await page.goto(target_url, timeout=0)
    await asyncio.sleep(random.uniform(3, 5))
    
    # Proaktif giriş tetiklemesi
    if not await is_auth_page(page):
        try:
            account_nav = page.locator("#nav-link-accountList")
            if await account_nav.count() > 0 and await account_nav.first.is_visible():
                nav_text = await account_nav.first.inner_text()
                if "sign in" in nav_text.lower() or "giriş yap" in nav_text.lower():
                    print("🤖 Oturum açılmamış! Amazon otomatik yönlendirmediği için giriş ekranı zorlanıyor...")
                    await account_nav.first.click()
                    await asyncio.sleep(random.uniform(3, 5))
        except Exception as e:
            pass
            
    timeout_counter = 60
    while await is_auth_page(page):
        if timeout_counter <= 0:
            print("❌ ZAMAN AŞIMI: İşlem süresi doldu. Bot işlemi iptal ediliyor.")
            sys.exit(1)
            
        print(f"🚨 UYARI: Otonom Login Asistanı Aktif! (Kalan Süre: {timeout_counter*5}sn)")
        
        try:
            email_input = page.locator("input[type='email'], input[name='email']")
            pass_input = page.locator("input[type='password'], input[name='password']")
            otp_input = page.locator("input[name='code'], input[name='cvf_captcha_input'], input[name='otpCode'], input#auth-mfa-otpcode")
            
            # Gateway Check
            if await email_input.count() == 0 and await pass_input.count() == 0 and await otp_input.count() == 0:
                gateway_btns = await page.locator("a[href*='/ap/signin']").all()
                for btn in gateway_btns:
                    id_attr = await btn.get_attribute("id")
                    if id_attr and "nav-link" in id_attr:
                        continue
                    if await btn.is_visible():
                        print("🤖 'Lütfen Giriş Yapın' ara ekranı tespit edildi. Yönlendirme butonuna basılıyor...")
                        await btn.click()
                        await asyncio.sleep(4)
                        break
                        
            # E-posta Otomasyonu
            if await email_input.count() > 0 and await email_input.first.is_visible():
                az_user = os.environ.get("AMAZON_USER")
                if az_user:
                    print(f"🤖 E-posta otomatik dolduruluyor: {az_user}")
                    await email_input.first.fill(az_user)
                    await asyncio.sleep(1)
                    submit_btn = page.locator("input#continue, span#continue, input[type='submit']")
                    if await submit_btn.count() > 0:
                        await submit_btn.first.click()
                        await asyncio.sleep(3)
                        
            # Şifre Otomasyonu
            if await pass_input.count() > 0 and await pass_input.first.is_visible():
                az_pass = os.environ.get("AMAZON_PASS")
                if az_pass:
                    print("🤖 Şifre kutusu otomatik dolduruluyor...")
                    await pass_input.first.fill(az_pass)
                    await asyncio.sleep(1)
                    remember_box = page.locator("input[name='rememberMe']")
                    if await remember_box.count() > 0 and await remember_box.first.is_visible():
                        try:
                            await remember_box.first.check()
                        except: pass
                    submit_btn = page.locator("input#signInSubmit, input[type='submit']")
                    if await submit_btn.count() > 0:
                        await submit_btn.first.click()
                        await asyncio.sleep(4)
                        
            # OTP Otomasyonu
            if await otp_input.count() > 0 and await otp_input.first.is_visible():
                print("🤖 Doğrulama (OTP) kutusu tespit edildi. E-Posta okunuyor...")
                code = get_latest_amazon_otp(max_wait_seconds=15)
                if code:
                    print(f"🤖 {code} şifresi alındı! Otomatik giriliyor...")
                    await otp_input.first.fill(code)
                    await asyncio.sleep(1)
                    submit_btn = page.locator("input[type='submit'], button[type='submit'], span.a-button-inner input")
                    if await submit_btn.count() > 0:
                        await submit_btn.first.click()
                        await asyncio.sleep(5)
                else:
                    print("🤖 E-postada kod bulunamadı (OTP beklemede)...")
        except Exception:
            pass

        await asyncio.sleep(5)
        timeout_counter -= 1
        
        try:
            if not await is_auth_page(page):
                await asyncio.sleep(4)
                if not await is_auth_page(page):
                    print("✅ Başarıyla giriş yapıldı!")
                    print("🔄 Sizi hedeflenen sayfaya tekrar yönlendiriyorum...")
                    try:
                        await page.goto(target_url, timeout=0)
                        await asyncio.sleep(random.uniform(3, 5))
                    except Exception:
                        pass
                    break
        except Exception:
            print("❌ Tarayıcı kapatıldı, iptal.")
            sys.exit(1)
            
    # Başarılı girişten sonra çerezleri kaydet
    await page.context.storage_state(path=STATE_FILE)
    print(f"✅ Çerezler kaydedildi: {STATE_FILE}")
