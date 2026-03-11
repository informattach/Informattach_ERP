import asyncio
import os
import json
import random
from playwright.async_api import async_playwright

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp_uploads")
STATE_FILE = os.path.join(os.path.dirname(__file__), "amazon_state.json")

# Amazon Business List URL (You may need to change this to the exact List ID page)
AMAZON_LIST_URL = "https://www.amazon.com/hz/wishlist/ls/VJV9BTR7JWGH?type=Wishlist&ref=cm_wl_list_create" 

async def auto_scroll(page):
    for _ in range(3):
        await page.mouse.wheel(0, random.randint(300, 600))
        await asyncio.sleep(0.5)

async def login_and_save_session():
    """
    Opens a visible browser so the user can manually log in and solve 2FA/Captchas.
    Saves the cookies/session state to `amazon_state.json` once logged in.
    """
    print("Masaüstünde yeni bir tarayıcı penceresi açılıyor...")
    print("Lütfen açılan pencereden Amazon Business hesabınıza GİRİŞ YAPIN.")
    print("Eğer Doğrulama/Captcha/OTP sorarsa, tarayıcı üzerinden elinizle çözün.")
    print("Giriş işleminiz tam anlamıyla bittikten (Ana Sayfayı gördükten) sonra bu terminale dönüp ENTER'a basın.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Headless = False (Visible to user)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        await page.goto("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F%3Fref_%3Dnav_custrec_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
        
        await page.goto("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F%3Fref_%3Dnav_custrec_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
        
        print("\n⏳ LÜTFEN AÇILAN PENCEREDEN GİRİŞ YAPIN. (Otomatik kapanması için 120 saniyeniz var)...")
        
        # We cannot use input() because Streamlit subprocess doesn't have an attached TTY/stdin.
        # Instead, we will just wait 120 seconds or until the user closes the window.
        try:
            for i in range(120, 0, -1):
                if i % 10 == 0:
                    print(f"Kalan süre: {i} saniye...")
                await asyncio.sleep(1)
        except Exception:
            pass
            
        print("\nSüre doldu, mevcut çerezler kaydediliyor...")
        
        # Giriş yapıldığında current state'i (Cookies, LocalStorage vb) JSON olarak donanım diskine kaydet
        await context.storage_state(path=STATE_FILE)
        
        print(f"✅ Oturum Çerezleri Başarıyla Kaydedildi! Dosya: {STATE_FILE}")
        print("Pencere kapatılıyor...")
        await browser.close()


async def download_amazon_list_background():
    """
    Uses the saved session state to log in invisibly (Headless),
    navigates to the Amazon List, and clicks the Export CSV/XLS button.
    Saves the file to temp_uploads.
    """
    if not os.path.exists(STATE_FILE):
        print("❌ HATA: amazon_state.json bulunamadı. Lütfen önce Ana Menüden 'Oturum Aç (Session Save)' işlemini gerçekleştirin.")
        return False
        
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print("🤖 Otonom Liste İndirme Botu Uyandı...")

    async with async_playwright() as p:
        # Load the saved session state to bypass login
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_FILE)
        page = await context.new_page()

        print("1. Amazon Listeler Sayfasına Gidiliyor...")
        try:
            await page.goto(AMAZON_LIST_URL, wait_until="domcontentloaded", timeout=60000)
            
            # SESSION EXPIRATION CHECK
            page_title = await page.title()
            if "Sign-In" in page_title or "Sign In" in page_title:
                print("❌ KRİTİK HATA: Amazon oturumu (Cookie) sona ermiş veya engellenmiş!")
                print("Lütfen arayüzdeki '🔑 Amazon Oturumu Aç (Session Save)' butonuna tıklayarak hesabınıza yeniden giriş yapın.")
                await browser.close()
                return False
                
            await auto_scroll(page)
            
            # Fetch all list URLs from the sidebar
            lists_to_download = await page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a'));
                    const listLinks = [];
                    anchors.forEach(a => {
                        if (a.href && a.href.includes('/hz/wishlist/ls/')) {
                            const cleanUrl = a.href.split('?')[0];
                            const text = a.textContent.trim().replace(/\\n/g, '');
                            // Filter out Amazon UI elements like "More" and template variables like "{listId}" (%7B)
                            if (text && text.length > 2 && text.toLowerCase() !== 'more' && !cleanUrl.includes('%7B') && !text.includes('{list')) {
                                listLinks.push({ title: text, url: cleanUrl });
                            }
                        }
                    });
                    
                    const unique = [];
                    const seen = new Set();
                    for (const item of listLinks) {
                        if (!seen.has(item.url)) {
                            seen.add(item.url);
                            unique.push(item);
                        }
                    }
                    return unique;
                }
            """)
            
            print(f"📌 {len(lists_to_download)} adet liste tespit edildi. Sırayla indirilecek...")
            
            for list_item in lists_to_download:
                print(f"\\n👉 Liste İşleniyor: {list_item['title']} ({list_item['url']})")
                await page.goto(list_item['url'], wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
                
                try:
                    async with page.expect_download(timeout=45000) as download_info:
                        await page.evaluate("""
                            // 1. Try the specific Business list export button first
                            let downloadBtn = document.querySelector('a#ure-export-list') || document.querySelector('span#ure-export-list');
                            
                            // 2. Fallback to generic text search
                            if (!downloadBtn) {
                                const spans = Array.from(document.querySelectorAll('span'));
                                downloadBtn = spans.find(s => s.textContent.trim() === 'Download');
                            }
                            
                            if (downloadBtn) {
                                downloadBtn.click();
                            } else {
                                throw new Error("Download button not found in DOM.");
                            }
                        """)
                    
                    download = await download_info.value
                    
                    # Clean title for filename mapping
                    safe_title = "".join([c for c in list_item['title'] if c.isalnum() or c==' ']).strip()
                    safe_title = safe_title.replace(" ", "_").replace("__", "_")
                    filename = f"exportedList_{safe_title}.xlsx"
                    file_path = os.path.join(DOWNLOAD_DIR, filename)
                    
                    await download.save_as(file_path)
                    print(f"✅ Orijinal Excel dosyası başarıyla indirildi: {file_path}")
                    
                except Exception as e:
                    print(f"❗ Orijinal İndirme Butonu Yok: '{list_item['title']}'. Hata: {str(e)[:50]}")
                    print(f"🔄 Alternatif Sıyırıcı (DOM Scraper) Devreye Giriyor...")
                    
                    try:
                        print(f"  > Sepet Yükleniyor... Aşağı Kaydırılıyor (En alttan ürünleri toplamak için)...")
                        await auto_scroll(page)
                        await asyncio.sleep(4)
                        
                        # Extract data from the DOM directly as fallback (For Business Essentials style lists)
                        items = await page.evaluate("""
                            () => {
                                const results = [];
                                const seen = new Set();
                                
                                // Safest approach: Look for any link containing /dp/ASIN
                                const links = document.querySelectorAll('a[href*="/dp/"]');
                                
                                for (let a of links) {
                                    const match = a.href.match(/\\/dp\\/([A-Z0-9]{10})/);
                                    if (!match) continue;
                                    
                                    const asin = match[1];
                                    if (seen.has(asin)) continue;
                                    
                                    // Make sure it's a product link, not a review link or something else
                                    // Usually the main product link has a title attribute or an image inside
                                    let title = a.getAttribute('title') || '';
                                    if (!title) {
                                        const img = a.querySelector('img');
                                        if (img) title = img.alt || '';
                                    }
                                    if (!title) {
                                        title = a.textContent.trim();
                                    }
                                    
                                    if (title && title.length > 5) {
                                        // Attempt to find price in a parent container
                                        let price = '';
                                        try {
                                            const parent = a.closest('.a-fixed-left-grid, .a-list-item, div[id^="itemMain"]');
                                            if (parent) {
                                                const priceEl = parent.querySelector('.a-price .a-offscreen');
                                                if (priceEl) price = priceEl.textContent.trim();
                                            }
                                        } catch(e) {}
                                        
                                        seen.add(asin);
                                        results.push({asin: asin, title: title, price: price});
                                    }
                                }
                                return results;
                            }
                        """)
                        
                        if items:
                            import pandas as pd
                            print(f"  > DOM'dan {len(items)} adet ASIN çıkarıldı. Excel oluşturuluyor...")
                            # Create a dummy DataFrame mimicking the structure expected by sync_bot
                            # Expected by database.py (import_amazon_drafts):
                            # col 1 (index 1): ASIN
                            # col 6 (index 6): Availability (Will put "In Stock")
                            # col 7 (index 7): Price
                            # col 8 (index 8): Title
                            
                            # Pad to 12 empty rows matching standard Amazon export
                            data = []
                            for _ in range(13):
                                # Just mock 9 columns
                                data.append([""] * 9)
                                
                            for item in items:
                                row = [""] * 9
                                row[0] = "Line number" # Just to pacify
                                row[1] = item['asin']
                                row[6] = "In Stock"
                                row[7] = item['price'] if item['price'] else ""
                                row[8] = item['title']
                                data.append(row)
                                
                            df = pd.DataFrame(data)
                            safe_title = "".join([c for c in list_item['title'] if c.isalnum() or c==' ']).strip()
                            safe_title = safe_title.replace(" ", "_").replace("__", "_")
                            filename = f"exportedList_{safe_title}_scraped.xlsx"
                            file_path = os.path.join(DOWNLOAD_DIR, filename)
                            
                            df.to_excel(file_path, index=False, header=False)
                            print(f"✅ Alternatif DOM Excel'i başarıyla oluşturuldu: {file_path}")
                        else:
                            print(f"❌ DOM çıkarımı başarısız. ASIN bulunamadı.")
                            
                    except Exception as fallback_e:
                        print(f"❌ Alternatif Çıkarım başarısız oldu: {str(fallback_e)}")
                    
        except Exception as e:
            print(f"❌ Kapatılıyor. Hata Oluştu: {e}")
            return False
        finally:
            await browser.close()
            
    return True

async def upload_amazon_list_background(file_path):
    """
    Kullanıcının veritabanından çekilerek oluşturulan 10 karakterli ASIN Upload Excel'ini
    Amazon'un Orijinal Shopping List "Upload spreadsheets" sayfasına headless olarak yükler.
    """
    if not os.path.exists(file_path):
        print(f"❌ Yüklenecek dosya bulunamadı: {file_path}")
        return False
        
    print(f"🚀 Otonom Amazon Yükleyici Uyandı. Dosya: {file_path}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_FILE)
        page = await context.new_page()
        
        try:
            print("1. Amazon Shopping List sayfasına gidiliyor...")
            await page.goto(AMAZON_LIST_URL, wait_until="domcontentloaded", timeout=60000)
            
            # SESSION EXPIRATION CHECK
            page_title = await page.title()
            if "Sign-In" in page_title or "Sign In" in page_title:
                print("❌ KRİTİK HATA: Amazon oturumu (Cookie) sona ermiş veya engellenmiş!")
                print("Lütfen arayüzdeki '🔑 Amazon Oturumu Aç (Session Save)' butonuna tıklayarak hesabınıza yeniden giriş yapın.")
                await browser.close()
                return False
                
            await asyncio.sleep(5)
            
            # Dismiss any potential onboarding tooltips or popovers
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
            
            print("2. 'Edit items in list' butonuna tıklanıyor...")
            # Click the exact Edit items text
            await page.locator("a", has_text="Edit items in list").first.click(timeout=15000, force=True)
            await asyncio.sleep(4)
            
            print("3. 'Upload spreadsheet' kutucuğuna tıklanıyor...")
            # Using the aria-label from the user
            await page.locator('[aria-label="add-item-using-spreadsheet-upload"]').click(timeout=15000, force=True)
            await asyncio.sleep(4)
            
            print("4. Dosya seçici tetiklenip '.xlsx' yükleniyor...")
            # Wait for the file chooser dialog by intercepting the 'Browse for file' button click
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await page.locator('[data-testid="bulk-file-upload-button"]').click(force=True)
            
            file_chooser = await fc_info.value
            await file_chooser.set_files(file_path)
            await asyncio.sleep(3)
            
            print("5. 'Update list' butonuna basılıp veriler Amazon'a gönderiliyor...")
            await page.locator('[data-testid="bulk-list-upload-upload-button"]').click(timeout=15000)
            
            print("⏳ Amazon'un dosyayı işlemesi bekleniyor (15 saniye)...")
            await asyncio.sleep(15)
            
            print("✅ Amazon yükleme işlemi başarıyla tamamlandı!")
            return True
            
        except Exception as e:
            print(f"❌ Yükleme Sırasında Hata Oluştu: {e}")
            return False
        finally:
            await browser.close()

async def scrape_amazon_deals_background():
    """
    Amazon'un Fırsat/İndirim sayfalarını (Today's Deals, Business Savings, Prime Exclusive) 
    ziyaret edip Regex DOM çıkarma mantığıyla ASIN'leri toplayıp Excel olarak dışa aktarır.
    """
    DEAL_LISTS = [
        {"name": "Todays_Deals", "url": "https://www.amazon.com/gp/goldbox/?ref_=abn_cs_deals&pd_rd_r=097a5016-a7f9-4cff-941a-28fd29c21161&pd_rd_w=w0e8W&pd_rd_wg=ITdyf"},
        {"name": "Business_Savings", "url": "https://www.amazon.com/ab/business-discounts?ref_=abn_cs_ab_sg&pd_rd_r=abf0d4ff-ae95-4ed4-b114-c74acdd5bd48&pd_rd_w=aS0pT&pd_rd_wg=9KLpC"},
        {"name": "Prime_Exclusive", "url": "https://www.amazon.com/b?node=202448500011"}
    ]
    
    print("🚀 Otonom Fırsat (Deals) Kazıyıcı Uyandı...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_FILE)
        page = await context.new_page()
        
        try:
            for deal in DEAL_LISTS:
                print(f"\\n👉 Fırsat İşleniyor: {deal['name']} ({deal['url'][:80]}...)")
                await page.goto(deal['url'], wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                
                print(f"  > Sayfa Yükleniyor... Aşağı Kaydırılıyor (Gizli Fırsatları toplamak için)...")
                # Daha agresif ve derin kaydırma (15 kez 1200 piksel)
                for i in range(18):
                    await page.mouse.wheel(0, 1200)
                    await asyncio.sleep(1.5)
                    if i % 5 == 0:
                        print(f"    - Sayfanın derinliklerine iniliyor ({i}/18) ...")
                        
                # Ayrıca buton varsa "View more deals" vb. tetiklemeye çalış (opsiyonel)
                try:
                    await page.evaluate("""() => {
                        const moreBtn = Array.from(document.querySelectorAll('a, button')).find(el => el.textContent && el.textContent.toLowerCase().includes('view more'));
                        if (moreBtn) moreBtn.click();
                    }""")
                    await asyncio.sleep(3)
                except:
                    pass
                
                # Extract data from the DOM directly
                items = await page.evaluate("""
                    () => {
                        const results = [];
                        const seen = new Set();
                        // Find all links that contain an ASIN
                        const links = document.querySelectorAll('a[href*="/dp/"]');
                        
                        for (let a of links) {
                            const match = a.href.match(/\\/dp\\/([A-Z0-9]{10})/);
                            if (!match) continue;
                            
                            const asin = match[1];
                            if (seen.has(asin)) continue;
                            
                            // Find the entire product card container for better context
                            const card = a.closest('div[class*="Card"], div[data-testid*="deal"], div[class*="sg-col-inner"], li.a-carousel-card');
                            
                            let title = '';
                            let price = '';
                            
                            if (card) {
                                // 1. Try to find Title inside the card
                                const titleEl = card.querySelector('[class*="title"], h2, [class*="Title"], img[alt]');
                                if (titleEl) {
                                    title = (titleEl.tagName === 'IMG') ? titleEl.alt : titleEl.textContent;
                                }
                                
                                // 2. Try to find Price inside the card
                                const priceSelectors = ['.a-price .a-offscreen', '[class*="price"]', '[class*="Price"]', 'span:not(.a-color-secondary):contains("$")'];
                                for (let sel of priceSelectors) {
                                    try {
                                        const pEl = card.querySelector(sel);
                                        if (pEl && pEl.textContent.includes('$')) {
                                            price = pEl.textContent.trim();
                                            break;
                                        }
                                    } catch(e) {}
                                }
                            }
                            
                            // 3. Fallbacks if Card parsing failed
                            if (!title || title.toLowerCase().includes('product image') || title.length < 10) {
                                title = a.getAttribute('title') || '';
                            }
                            if (!title || title.toLowerCase().includes('product image') || title.length < 10) {
                                const img = a.querySelector('img');
                                if (img && img.alt && !img.alt.toLowerCase().includes('product image')) {
                                    title = img.alt;
                                }
                            }
                            if (!title || title.toLowerCase().includes('product image') || title.length < 10) {
                                title = a.textContent.trim();
                            }
                            
                            // Clean up
                            title = title.replace(/\\n/g, ' ').replace(/\\s{2,}/g, ' ').trim();
                            
                            // Only accept if title is somewhat valid and not just short garbage
                            if (title && title.length > 5 && !title.toLowerCase().includes('product image')) {
                                seen.add(asin);
                                results.push({asin: asin, title: title, price: price});
                            }
                        }
                        return results;
                    }
                """)
                
                if items:
                    import pandas as pd
                    print(f"  > DOM'dan {len(items)} adet ASIN çıkarıldı. Excel oluşturuluyor...")
                    data = []
                    for _ in range(13):
                        data.append([""] * 9)
                        
                    for item in items:
                        row = [""] * 9
                        row[0] = "Line number"
                        row[1] = item['asin']
                        row[6] = "In Stock"
                        row[7] = item['price'] if item['price'] else ""
                        row[8] = item['title']
                        data.append(row)
                        
                    df = pd.DataFrame(data)
                    safe_title = "".join([c for c in deal['name'] if c.isalnum() or c==' ']).strip()
                    safe_title = safe_title.replace(" ", "_").replace("__", "_")
                    filename = f"exportedList_{safe_title}_scraped.xlsx"
                    file_path = os.path.join(DOWNLOAD_DIR, filename)
                    
                    df.to_excel(file_path, index=False, header=False)
                    print(f"✅ Fırsat Excel'i başarıyla oluşturuldu: {file_path}")
                else:
                    print(f"❌ DOM çıkarımı başarısız. ASIN bulunamadı.")
                    
        except Exception as e:
            print(f"❌ Kapatılıyor. Hata Oluştu: {e}")
            return False
        finally:
            await browser.close()
            
    return True

if __name__ == "__main__":
    if not os.path.exists(STATE_FILE):
        print("⚠️ amazon_state.json bulunamadı. Lütfen oturum açın.")
        
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "--upload":
            asyncio.run(upload_amazon_list_background(sys.argv[2]))
        elif sys.argv[1] == "--deals":
            asyncio.run(scrape_amazon_deals_background())
        elif sys.argv[1] == "--download":
            asyncio.run(download_amazon_list_background())
        else:
            print("Geçersiz argüman: --upload, --deals, veya --download kullanın.")
    else:
        # Argüman verilmeden (manuel) çalıştırıldığında direkt Login Ekranını aç
        asyncio.run(login_and_save_session())
