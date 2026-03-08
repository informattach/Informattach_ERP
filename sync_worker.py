import time
import os
from dotenv import load_dotenv
from supabase import create_client
from ebay_core import EbayManager

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Kendi mağaza UUID'ni buraya gir
STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee" 

def run_sync_worker():
    print("SİSTEM KİLİTLENDİ: Hasar tespiti ve güvenlik nedeniyle eBay'e veri gönderimi tamamen durdurulmuş ve mühürlenmiştir.")
    return # ACİL DURUM: Veri gönderimi devredışı bırakıldı.
    
    print("Otomasyon Motoru Başladı. Değişiklik bekleyen ürünler taranıyor...")
    manager = EbayManager(store_id=STORE_ID)
    
    while True:
        try:
            # Sadece 'needs_sync' şalteri TRUE olan (değişmiş) ürünleri çek
            response = supabase.table("listings").select("*").eq("needs_sync", True).execute()
            changed_items = response.data
            
            if not changed_items:
                print("Değişiklik yok. 60 saniye bekleniyor...", end="\r")
                time.sleep(60)
                continue
                
            print(f"\n[{len(changed_items)}] adet güncellenecek ürün bulundu. API'ye gönderiliyor...")
            
            for item in changed_items:
                isku = item.get('channel_sku')
                new_price = item.get('listed_price')
                new_qty = item.get('quantity', 0)
                db_id = item.get('id') # Supabase'deki primary key
                
                if not isku:
                    print(f"HATA: {db_id} ID'li ürünün ISKU'su yok, atlanıyor.")
                    continue
                    
                # 1. ebay_core.py içindeki API metodumuzu ateşle
                print(f"-> {isku} eBay'e basılıyor (Fiyat: ${new_price}, Stok: {new_qty})...")
                manager.update_price_and_quantity(isku, new_price, new_qty)
                
                # 2. İşlem bittikten sonra şalteri geri indir (FALSE yap) ki bir daha göndermesin
                supabase.table("listings").update({"needs_sync": False}).eq("id", db_id).execute()
                print(f"-> {isku} başarıyla senkronize edildi ve şalter kapatıldı.")
                
            print("Kuyruk temizlendi. Yeni değişiklikler bekleniyor...\n")
            
        except Exception as e:
            print(f"Kritik Döngü Hatası: {e}")
            time.sleep(60) # Hata olursa 1 dakika bekle, sistemi çökertme

if __name__ == "__main__":
    run_sync_worker()