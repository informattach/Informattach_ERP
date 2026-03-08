import os
import sys
import time
import glob
import pandas as pd
import re
import random
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from database import db
from pricing_engine import PricingEngine
from ebay_core import EbayManager

STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"
UPLOAD_DIR = "/Users/fatihozdemir/Desktop/Kodlar/Informattach_ERP/temp_uploads"

# -- Stealth Ayarları (list_importer'dan uyarlandı) --
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

class AmazonSyncBot:
    def __init__(self):
        self.ebay = EbayManager(store_id=STORE_ID)
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)

    # ---------------------------------------------------------
    # YÖNTEM 1: TOPLU (BULK) EXCEL AKTARIMI
    # ---------------------------------------------------------
    def check_for_excel_updates(self):
        """temp_uploads içindeki exportedList excel'leri tarar ve işler."""
        excel_files = glob.glob(os.path.join(UPLOAD_DIR, "*.xlsx"))
        if not excel_files:
            return False

        for file_path in excel_files:
            log(f"Excel Dosyası Tespit Edildi: {file_path}")
            try:
                # 1. Excel'i Oku
                df = pd.read_excel(file_path, header=None, skiprows=12)
                
                # Sadece ASIN ve Fiyat değişimlerini alıyoruz
                updates = []
                for index, row in df.iterrows():
                    val_0 = str(row.get(0, ""))
                    if "Example line" in val_0 or "Line number" in val_0:
                        continue
                        
                    asin = str(row.get(1, "")).strip()
                    if not asin or asin.lower() == "nan" or len(asin) < 5:
                        continue
                        
                    # Stok
                    qty_raw = row.get(2)
                    qty = 3
                    if pd.notna(qty_raw):
                        try:
                            qty = int(float(qty_raw))
                        except Exception as e:
                            log(f"Stok parse hatasi ({qty_raw}): {e}")
                            
                    # Fiyat
                    price_raw = str(row.get(7, ""))
                    price_val = None
                    if pd.notna(row.get(7)) and price_raw.lower() != "nan":
                        match = re.search(r"(\d+\.\d+|\d+)", price_raw.replace(",", ""))
                        if match:
                            price_val = float(match.group(1))

                    if price_val is not None:
                        updates.append({
                            "asin": asin,
                            "price": price_val,
                            "qty": qty
                        })

                log(f"{len(updates)} kalem ürün Excel'den okundu. Güncellemeler başlatılıyor...")
                
                # 2. Veritabanı ve eBay'i Güncelle
                for product in updates:
                    self._process_single_update(product['asin'], product['price'], product['qty'])
                
                # 3. Dosyayı yedekle veya sil
                os.remove(file_path)
                log(f"Excel İşlemi Tamamlandı ve Dosya Silindi: {file_path}")
                
            except Exception as e:
                log(f"Excel İşleme Hatası ({file_path}): {e}")
                
        return True # Excel bulundu ve işlendi

    # ---------------------------------------------------------
    # YÖNTEM 2: OTONOM CANLI YAYIN (SCRAPING)
    # ---------------------------------------------------------
    async def random_sleep(self, min_ms=1000, max_ms=3000):
        await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)

    async def auto_scroll(self, page):
        for _ in range(5):
            await page.mouse.wheel(0, random.randint(300, 600))
    async def set_amazon_zipcode(self, page, zip_code="87110"):
        """Amazon lokasyon kısıtlamalarını (Geo-blocking) aşmak için 
        tarama öncesi ABD Zip Code'unu sayfaya enjekte eder."""
        try:
            log(f"Amazon lokasyonu (Zip Code {zip_code}) olarak ayarlanıyor...")
            await page.goto("https://www.amazon.com/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            # 1. Interstitial (Continue Shopping) sayfasını atla
            continue_btn = page.locator("text=Continue shopping").first
            if await continue_btn.is_visible():
                await continue_btn.click()
                await asyncio.sleep(2)
                
            # 2. Lokasyon Popover'ını aç
            popover_link = page.locator("#nav-global-location-popover-link")
            if await popover_link.is_visible():
                await popover_link.click()
                await asyncio.sleep(2)
                
                # 3. Zip Code gir
                zip_input = page.locator("#GLUXZipUpdateInput")
                if await zip_input.is_visible():
                    await zip_input.fill(zip_code)
                    await asyncio.sleep(1)
                    await page.click("#GLUXZipUpdate")
                    await asyncio.sleep(2)
                    
                    # Sayfayı yenile ki lokasyon çerezleri (cookies) otursun
                    await page.reload(wait_until="domcontentloaded")
                    log("✅ Lokasyon başarıyla ayarlandı (US Fiyatları görünür kılındı).")
                    return True
        except Exception as e:
            log(f"Uyarı: Zip Code ayarlanamadı, varsayılan lokasyonla devam ediliyor. ({e})")
        return False

    async def run_live_scraper(self):
        """Dinamik Öncelik Kuyruklu (Priority Queue) Canlı Amazon Taraması"""
        log("Canlı Amazon Taraması Başlatılıyor...")
        
        try:
            # -------------------------------------------------------------
            # AŞAMA 1: ACİL ÖNCELİKLİ (needs_sync = True) Ürünleri Getir
            # -------------------------------------------------------------
            res_urgent = db.client.table("listings").select("product_id, channel_sku").eq("is_active", True).eq("needs_sync", True).eq("store_id", STORE_ID).execute()
            
            active_product_ids = []
            queue_type = "Hiçbiri"
            
            if res_urgent.data:
                log(f"🚨 DİKKAT: {len(res_urgent.data)} Adet Acil Güncellenmesi Gereken (needs_sync) Ürün Bulundu!")
                active_product_ids = [l["product_id"] for l in res_urgent.data]
                queue_type = "ACİL"
            else:
                # -------------------------------------------------------------
                # AŞAMA 2: NORMAL KUYRUK (updated_at ASC) + Cooldown Kontrolü
                # -------------------------------------------------------------
                # 12 saatlik cooldown threshold
                twelve_hours_ago = (datetime.utcnow() - pd.Timedelta(hours=12)).isoformat()
                
                # updated_at'e göre en eskileri (ASC) getir, son 12 saatte güncellenmişleri atla
                res_normal = db.client.table("listings").select("product_id, channel_sku").eq("is_active", True).eq("store_id", STORE_ID).lt("updated_at", twelve_hours_ago).order("updated_at", desc=False).limit(50).execute()
                
                if res_normal.data:
                    log(f"✅ Normal Tarama Kuyruğu: En eski {len(res_normal.data)} ürün işleme alınıyor.")
                    active_product_ids = [l["product_id"] for l in res_normal.data]
                    queue_type = "NORMAL"
                else:
                    log("💤 Kuyruk Boş. Tüm ürünler son 12 saat içinde taranmış veya aktif ürün yok. Bot beklemede kalacak.")
                    return # Bot tarama yapmadan döngüden çıkar ve uykuya dalar

            # Seçilen id'lerin Amazon ASIN (source_code) karşılıklarını bul:
            res_sources = db.client.table("sources").select("product_id, source_code, base_cost").in_("product_id", active_product_ids).execute()
            
            amazon_sources = []
            for s in res_sources.data:
                # source_code ASIN'dir (10 haneli)
                if len(str(s["source_code"])) == 10: 
                    amazon_sources.append(s)

            log(f"Taranacak {len(amazon_sources)} adet ({queue_type} Öncelikli) Amazon ürünü bulundu.")
            
        except Exception as e:
            log(f"DB Kaynak Çekme Hatası: {e}")
            return

        if not amazon_sources:
            return

        # Ürünleri Playwright ile tara
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            for src in amazon_sources:
                asin = src["source_code"]
                current_cost = float(src["base_cost"])
                url = f"https://www.amazon.com/dp/{asin}"
                
                try:
                    await self.random_sleep(2000, 5000) # Anti-bot bekleme
                    log(f"Taranıyor: {url}")
                    
                    # Sadece ilk taranacak üründen önce zip code ayarlamasını yap
                    if src == amazon_sources[0]:
                        await self.set_amazon_zipcode(page)
                        
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await self.auto_scroll(page)
                    
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # 1. Stok Kontrolü (Out of stock)
                    availability_el = soup.find(id="availability")
                    availability_text = availability_el.get_text(strip=True).lower() if availability_el else ""
                    
                    if "currently unavailable" in availability_text or "out of stock" in availability_text:
                        log(f"[{asin}] Stokta Yok! eBay güncelleniyor (Stock: 0)")
                        self._process_single_update(asin, base_cost=current_cost, qty=0)
                        continue
                        
                    # 2. Fiyat Çekimi
                    price = None
                    price_blocks = soup.select(".priceToPay, #corePriceDisplay_desktop_feature_div, #corePrice_desktop, #priceblock_ourprice")
                    
                    for block in price_blocks:
                        # try to find the standard hidden value first
                        offscreen = block.select_one(".a-price .a-offscreen")
                        pt = ""
                        if offscreen and offscreen.get_text(strip=True):
                            pt = offscreen.get_text(strip=True)
                        else:
                            pt = block.get_text(separator=' ', strip=True)
                        
                        pt = pt.replace("$", "").replace(",", "").replace("€", "").replace("£", "").replace("EUR", "")
                        match = re.search(r"(\d+\.\d+)", pt)
                        if match:
                            price = float(match.group(1))
                            break
                        
                    if price is None:
                        log(f"[{asin}] Uyarı: Fiyat okunamadı. (Amazon lokasyon/stok gizlemesi olabilir)")
                        continue
                        
                    # Fiyat farkı varsa güncelle
                    if abs(price - current_cost) > 0.05:
                        log(f"[{asin}] Fiyat Değişimi: ${current_cost} -> ${price}. eBay güncelleniyor.")
                        self._process_single_update(asin, base_cost=price, qty=3) # Standart 3 stok varsayımı
                    else:
                        log(f"[{asin}] Fiyat Stabil (${price}). İşlem yok.")
                        
                except Exception as e:
                    import traceback
                    log(f"[{asin}] Tarama Hatası: {e}")
                    log(traceback.format_exc())

            await browser.close()


    # ---------------------------------------------------------
    # ORTAK GÜNCELLEME ÇEKİRDEĞİ (Yöntem 1 ve Yöntem 2 kullanır)
    # ---------------------------------------------------------
    def _process_single_update(self, asin: str, base_cost: float, qty: int, channel_sku: str = None):
        """Maliyeti alır, Pricing Engine hesaplar ve Supabase+eBay'e yazar."""
        from pricing_engine import PricingEngine
        
        try:
            # 1. Veritabanından product_id ve eğer gerekliyse SKU'yu al
            p_res = db.client.table("core_products").select("id").eq("asin", asin).execute()
            if not p_res.data:
                log(f"[{asin}] Veritabanında ürün bulunamadı. DB Güncellemesi atlanıyor.")
                return
            p_id = p_res.data[0]["id"]

            if not channel_sku:
                l_res = db.client.table("listings").select("channel_sku, channel_item_id").eq("product_id", p_id).eq("store_id", STORE_ID).execute()
                if l_res.data and l_res.data[0].get("channel_sku"):
                    channel_sku = l_res.data[0]["channel_sku"]
                    item_id = l_res.data[0].get("channel_item_id")
                else:
                    channel_sku = f"A-{asin}" # Standart Easync kalıbı (Fallback)
                    item_id = None
            else:
                # Sku parametreden geldiyse ItemID'yi yine de DB'den al
                l_res = db.client.table("listings").select("channel_item_id").eq("product_id", p_id).eq("store_id", STORE_ID).execute()
                item_id = l_res.data[0].get("channel_item_id") if l_res.data else None
            
            # ERP Satış Fiyatı Hesaplama
            listed_price = PricingEngine.calculate_final_price(
                source_price=base_cost, 
                marketplace="ebay"
            )
            
            if listed_price <= 0 and qty > 0:
                log(f"[{asin}] Uyarı: Maliyet hesabı $0 döndü. Es geçiliyor.")
                return

            # eBay API Güncelleme
            try:
                self.ebay.update_price_and_quantity(sku=channel_sku, new_price=listed_price, new_qty=qty, item_id=item_id)
                log(f"[{asin}] eBay API Başarılı: Stok={qty}, Fiyat=${listed_price}")
            except Exception as e_api:
                log(f"[{asin}] eBay API Hatası: {e_api}")
                # Loglansın ama DB güncellenmeye devam etsin (senkron bozulmasın)

            # DB Güncelleme
            # A) sources'ı güncelle (Maliyet)
            db.client.table("sources").update({"base_cost": base_cost}).eq("product_id", p_id).execute()
            
            # B) listings'ı güncelle (Son Fiyat, Miktar, needs_sync SIFIRLAMA ve updated_at tazeleme)
            db.client.table("listings").update({
                "listed_price": listed_price, 
                "quantity": qty,
                "needs_sync": False, # İşlem bitti, aciliyeti kaldır.
                "updated_at": datetime.utcnow().isoformat()
            }).eq("product_id", p_id).eq("store_id", STORE_ID).execute()
            
        except Exception as e:
            log(f"[{asin}] İşlem Çekirdeği Hatası: {e}")

    # ---------------------------------------------------------
    # ANA ÇALIŞMA DÖNGÜSÜ
    # ---------------------------------------------------------
    def start_sync_loop(self):
        log("=========================================")
        log("Amazon 24/7 Otonom Sync Bot Başlatıldı")
        log("=========================================")
        
        while True:
            try:
                # 1. Önce Klasörde Toplu Excel var mı ona bak (Az kaynak tüketir)
                excel_processed = self.check_for_excel_updates()
                
                if not excel_processed:
                    # 2. Klasörde dosya yoksa ve zamanı da uyguna tarama motorunu çalıştır
                    # Burayı async çalıştırıyoruz
                    asyncio.run(self.run_live_scraper())
                    
                # Aşırı Ban yememek için döngüler arasına dinlenme
                sleep_minutes = random.randint(15, 30)
                log(f"Tur Tamamlandı. Bot {sleep_minutes} dakika uykuya geçiyor...")
                time.sleep(sleep_minutes * 60)
                
            except KeyboardInterrupt:
                log("Bot manuel olarak durduruldu.")
                sys.exit(0)
            except Exception as e:
                import traceback
                log(f"Kritik Bot Döngüsü Hatası: {e}")
                log(traceback.format_exc())
                time.sleep(60)

if __name__ == "__main__":
    bot = AmazonSyncBot()
    bot.start_sync_loop()
