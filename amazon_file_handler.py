import os
import asyncio
import re
import random
from playwright.async_api import Page, async_playwright
from amazon_auth import ensure_logged_in, STATE_FILE, USER_AGENTS

DOWNLOAD_DIR = "/Users/fatihozdemir/Desktop/Kodlar/Informattach_ERP/temp_uploads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Amazon Business List URL (Ana shopping list linkiniz)
AMAZON_LIST_URL = "https://www.amazon.com/hz/wishlist/ls/VJV9BTR7JWGH?type=Wishlist&ref=cm_wl_list_create"

async def auto_scroll(page: Page):
    for _ in range(3):
        await page.mouse.wheel(0, random.randint(300, 600))
        await asyncio.sleep(0.5)

async def upload_wishlist(page: Page, file_path: str):
    """DB ASIN'lerinin yüklendiği ve hemen ardından Failed ASIN indirildiği 1. Adım"""
    print(f"🚀 [ADIM 1] Veritabanı ASIN listesi Amazon'a yükleniyor: {file_path}")
    if not os.path.exists(file_path):
        print(f"❌ Yüklenecek dosya bulunamadı: {file_path}")
        return False
        
    await ensure_logged_in(page, AMAZON_LIST_URL)
    
    try:
        await asyncio.sleep(2)
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        
        print("1. 'Edit items in list' butonuna tıklanıyor...")
        await page.locator("a", has_text="Edit items in list").first.click(timeout=15000, force=True)
        await asyncio.sleep(4)
        
        print("2. 'Upload spreadsheet' kutucuğuna tıklanıyor...")
        await page.locator('[aria-label="add-item-using-spreadsheet-upload"]').click(timeout=15000, force=True)
        await asyncio.sleep(4)
        
        print("3. Dosya seçici tetiklenip '.xlsx' yükleniyor...")
        async with page.expect_file_chooser(timeout=15000) as fc_info:
            await page.locator('[data-testid="bulk-file-upload-button"]').click(force=True)
        
        file_chooser = await fc_info.value
        await file_chooser.set_files(file_path)
        await asyncio.sleep(3)
        
        print("4. 'Update list' butonuna basılıp veriler Amazon'a gönderiliyor...")
        await page.locator('[data-testid="bulk-list-upload-upload-button"]').click(timeout=15000)
        
        print("⏳ Amazon'un dosyayı işlemesi bekleniyor (15 saniye)...")
        await asyncio.sleep(15)
        
        print("📥 5. İşlem Raporu / Hatalı ASIN (Failed ASINs) Raporu kontrol ediliyor...")
        try:
            error_report_locator = page.locator("a", has_text=re.compile(r"(download error report|download errors|download failed|download report)", re.IGNORECASE))
            if await error_report_locator.count() > 0:
                print("🚨 Hata Raporu bulundu! İndiriliyor...")
                async with page.expect_download(timeout=15000) as download_info:
                    await error_report_locator.first.click()
                download = await download_info.value
                failed_filename = os.path.join(DOWNLOAD_DIR, "failed_asins_report.xlsx")
                await download.save_as(failed_filename)
                print(f"✅ Hatalı ASIN raporu başarıyla indirildi: {failed_filename}")
            else:
                print("✅ Hata Raporu bağlantısı bulunamadı (Tüm ASIN'ler hatasız yüklenmiş olabilir).")
        except Exception as e:
            print(f"⚠️ Hata Raporu indirme denemesi başarısız oldu: {e}")
            
        print("✅ Yükleme (Upload) işlemi başarıyla tamamlandı!")
        return True
    except Exception as e:
        print(f"❌ Yükleme Sırasında Hata Oluştu: {e}")
        return False

async def download_categorical_lists(page: Page):
    """Taslaklara/DB'ye karşılaştırılmak üzere Amazon'daki Hazır Liste dosyalarını çeker (ADIM 2)"""
    print(f"🚀 [ADIM 2] Amazon'daki Hazır (Kategorik) Listeler aranıp indiriliyor...")
    await ensure_logged_in(page, AMAZON_LIST_URL)
    
    try:
        await auto_scroll(page)
        
        lists_to_download = await page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a'));
                const listLinks = [];
                anchors.forEach(a => {
                    if (a.href && a.href.includes('/hz/wishlist/ls/')) {
                        const cleanUrl = a.href.split('?')[0];
                        const text = a.textContent.trim().replace(/\\n/g, '');
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
        
        downloaded_files = []
        for list_item in lists_to_download:
            print(f"\\n👉 Liste İşleniyor: {list_item['title']} ({list_item['url']})")
            await page.goto(list_item['url'], wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            try:
                async with page.expect_download(timeout=15000) as download_info:
                    await page.evaluate("""
                        let downloadBtn = document.querySelector('a#ure-export-list') || document.querySelector('span#ure-export-list');
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
                safe_title = "".join([c for c in list_item['title'] if c.isalnum() or c==' ']).strip()
                safe_title = safe_title.replace(" ", "_").replace("__", "_")
                filename = f"exportedList_{safe_title}.xlsx"
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                
                await download.save_as(file_path)
                print(f"✅ Orijinal Excel dosyası başarıyla indirildi: {file_path}")
                downloaded_files.append(file_path)
                
            except Exception as e:
                print(f"❗ Orijinal İndirme Butonu Yok: '{list_item['title']}'. Atlanıyor...")
                
        return downloaded_files
    except Exception as e:
        print(f"❌ Kategorik Listeleri İndirirken Hata: {e}")
        return []

async def download_shopping_list(page: Page):
    """Oturum kapanışından hemen önce ana aktif listeyi fiyat/stok güncellemesi için indirir (ADIM 5)"""
    print(f"🚀 [ADIM 5] Güncel Fiyat/Stok tablosu (Ana Liste) indiriliyor...")
    await ensure_logged_in(page, AMAZON_LIST_URL)
    
    try:
        await asyncio.sleep(2)
        async with page.expect_download(timeout=20000) as download_info:
            await page.evaluate("""
                let downloadBtn = document.querySelector('a#ure-export-list') || document.querySelector('span#ure-export-list');
                if (!downloadBtn) {
                    const spans = Array.from(document.querySelectorAll('span'));
                    downloadBtn = spans.find(s => s.textContent.trim() === 'Download');
                }
                if (downloadBtn) {
                    downloadBtn.click();
                } else {
                    throw new Error("Download button not found on the main list.");
                }
            """)
        
        download = await download_info.value
        filename = f"exportedList_Shopping_List_Main.xlsx"
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        
        await download.save_as(file_path)
        print(f"✅ Ana Shopping List başarıyla indirildi: {file_path}")
        return file_path
    except Exception as e:
        print(f"❌ Ana Liste İndirilirken Hata: {e}")
        return None
