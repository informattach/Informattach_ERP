import os
import sys
import asyncio
import time
from datetime import datetime
import pytz
from playwright.async_api import async_playwright
import pandas as pd

from database import db
from amazon_auth import ensure_logged_in, STATE_FILE, USER_AGENTS
import amazon_file_handler
import list_importer

# Albuquerque (Mountain Time) Timer Check
def is_albuquerque_6_oclock():
    mt_tz = pytz.timezone('US/Mountain')
    now_mt = datetime.now(mt_tz)
    
    # Check if hour is exactly 6 or 18 (6 AM / 6 PM)
    if now_mt.hour == 6 or now_mt.hour == 18:
        return True
    return False

def get_session_duration():
    """Starts at 5 mins, increases by 1 min per run up to 30 mins."""
    duration_file = os.path.join(os.path.dirname(__file__), "session_duration.txt")
    if not os.path.exists(duration_file):
        with open(duration_file, "w") as f:
            f.write("5")
        return 5
        
    with open(duration_file, "r") as f:
        try:
            val = int(f.read().strip())
            new_val = min(val + 1, 30)
            with open(duration_file, "w") as fw:
                fw.write(str(new_val))
            return new_val
        except:
            return 5

async def run_orchestrator(headless: bool = True, step_mode: str = "all"):
    print(f"\\n{'='*50}")
    print(f"🤖 Bütünleşik Amazon Orkestratörü Başlıyor (Mod: {step_mode})")
    print(f"📅 Yerel Saat: {datetime.now()} | Headless: {headless}")
    print(f"{'='*50}\\n")
    
    session_minutes = get_session_duration() if step_mode == "all" else 30
    session_seconds = session_minutes * 60
    start_time = time.time()
    
    print(f"⏳ Ayrılan Toplam Oturum Süresi: {session_minutes} Dakika")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context_args = {
            "user_agent": USER_AGENTS[0],
            "viewport": {"width": 1920, "height": 1080},
            "java_script_enabled": True
        }
        if os.path.exists(STATE_FILE):
            context_args["storage_state"] = STATE_FILE
            
        context = await browser.new_context(**context_args)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await context.new_page()
        
        try:
            if step_mode in ["all", "sync"]:
                # ==== ADIM 1: Veritabanından Amazon'a Yükleme (Upload) ====
                export_path = os.path.join(os.path.dirname(__file__), "temp_uploads", "db_export_upload.xlsx")
                if db.generate_amazon_export_file(export_path):
                    print("\\n--- [ADIM 1] WISH_LIST UPLOAD ---")
                    await amazon_file_handler.upload_wishlist(page, export_path)
                else:
                    print("\\n--- [ADIM 1] WISH_LIST UPLOAD ATLANDI (Aktarım listesi boş) ---")
                    
                # ==== ADIM 2: Hazır Liste (Categorical) İndirme ====
                if step_mode == "all":
                    print("\\n--- [ADIM 2] KATEGORİK LİSTELERİ İNDİRME ---")
                    downloaded_files = await amazon_file_handler.download_categorical_lists(page)
                    
                    new_asins = []
                    for file_path in downloaded_files:
                        try:
                            df = pd.read_excel(file_path, header=None, skiprows=12)
                            for index, row in df.iterrows():
                                val_0 = str(row.get(0, ""))
                                if "Example line" in val_0 or "Line number" in val_0: continue
                                asin = str(row.get(1, "")).strip()
                                if not asin or len(asin) < 5: continue
                                
                                exists_core = db.client.table("core_products").select("id").eq("asin", asin).limit(1).execute()
                                exists_draft = db.client.table("draft").select("id").eq("product_id", asin).limit(1).execute()
                                
                                if not exists_core.data and not exists_draft.data:
                                    new_asins.append(asin)
                        except Exception as e:
                            print(f"Hata: Liste okunurken problem yaşandı {file_path}: {e}")
                            
                    new_asins = list(set(new_asins))
                    print(f"📌 Draft ve DB ile kıyaslandı. Toplam {len(new_asins)} adet yeni ASIN tespit edildi.")
                    
                    # ==== ADIM 3: ASIN Filtreleme ve Derin Kazıma ====
                    print("\\n--- [ADIM 3] YENİ ASIN'LERİ DETAYLANDIRMA (DEEP SCRAPE) ---")
                    if new_asins:
                        filtered_asins = []
                        for a in new_asins:
                            if (time.time() - start_time) > (session_seconds - 300):
                                print("⏳ Süre azalıyor! Kalan ASIN'ler taramadan çıkarıldı.")
                                break
                            filtered_asins.append(a)
                        
                        if filtered_asins:
                            await list_importer.scrape_new_asins(page, filtered_asins)
                    else:
                        print("Tarayacak yeni ASIN bulunamadı.")
            
            if step_mode in ["all", "scrape"]:
                # ==== ADIM 4: Boş Zaman Değerlendirmesi (Campaign Harvest) ====
                print("\\n--- [ADIM 4] BOŞ ZAMAN: KAMPANYA HASADI (CAMPAIGN HARVEST) ---")
                remaining_time = session_seconds - (time.time() - start_time)
                if remaining_time > 180 or step_mode == "scrape": 
                    deal_urls = [
                        "https://www.amazon.com/ab/catalogs/?catalog=213428019011&rootCatalog=213428019011&ref_=abn_cs_xshop_ABBIZESS",
                        "https://www.amazon.com/gp/goldbox/?ref_=abn_cs_deals&pd_rd_r=351f9766-f0be-4bf3-9599-340a114a352f&pd_rd_w=NkPUC&pd_rd_wg=oYKQg",
                        "https://www.amazon.com/b?node=202448500011"
                    ]
                    harvested = await list_importer.harvest_campaigns(page, deal_urls)
                    
                    if harvested:
                        diff_asins = []
                        for asin in harvested:
                            exists_draft = db.client.table("draft").select("id").eq("product_id", asin).limit(1).execute()
                            if not exists_draft.data:
                                diff_asins.append(asin)
                        
                        if diff_asins:
                            print(f"📌 Hasat edilen {len(diff_asins)} yeni fırsat ASIN'i taranıyor...")
                            await list_importer.scrape_new_asins(page, diff_asins[:20])
                else:
                    print("⏳ Oturumun sonlarına yaklaşıldı. Kampanya taraması atlanıyor.")
                    
            if step_mode in ["all", "sync"]:
                if step_mode == "all":
                    while (time.time() - start_time) < (session_seconds - 120):
                        await asyncio.sleep(10)
                        
                # ==== ADIM 5: Kapanış ve Fiyat/Stok Senkronizasyonu ====
                print("\\n--- [ADIM 5] KAPANIŞ SENKRONİZASYONU (SHOPPING LIST DOWNLOAD) ---")
                final_file = await amazon_file_handler.download_shopping_list(page)
                if final_file:
                    print(f"🎉 Final senkronizasyon dosyası hazır: {final_file}")
            
        except Exception as e:
            print(f"❌ Orkestratör Hatası: {e}")
        finally:
            elapsed = time.time() - start_time
            print(f"\\n🏁 Oturum Sonlandı. Toplam Geçen Süre: {int(elapsed/60)} Dakika")
            await context.storage_state(path=STATE_FILE)
            await browser.close()
            
def run_scheduled_job():
    if is_albuquerque_6_oclock():
        print("⏰ Saat MT 06:00/18:00 doğrulandı. Zamanlanmış görev başlatılıyor...")
        asyncio.run(run_orchestrator(headless=True, step_mode="all"))
    else:
        print("Sadece Albuquerque saatine göre 6 AM ve 6 PM'de çalışır.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--manual":
            asyncio.run(run_orchestrator(headless=False, step_mode="all"))
        elif sys.argv[1] == "--manual-sync":
            asyncio.run(run_orchestrator(headless=False, step_mode="sync"))
        elif sys.argv[1] == "--manual-scrape":
            asyncio.run(run_orchestrator(headless=False, step_mode="scrape"))
        elif sys.argv[1] == "--scheduled":
            from apscheduler.schedulers.blocking import BlockingScheduler
            scheduler = BlockingScheduler()
            scheduler.add_job(run_scheduled_job, 'cron', minute=0)
            print("🕒 Zamanlanmış Orkestratör Başlatıldı (MT Saat dilimini bekliyor).")
            run_scheduled_job()
            scheduler.start()
    else:
        print("Bağımsız çalıştırmak için '--manual', '--manual-sync', '--manual-scrape' VEYA '--scheduled' kullanın.")
