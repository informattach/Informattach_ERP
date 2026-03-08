import csv
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# eBay Mağaza ID'n
STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"

def extract_true_asin(ebay_sku):
    """eBay üzerindeki A-ASIN veya M-ASIN formatından asıl kaynak anahtarını (ASIN) bul"""
    if not ebay_sku: return None
    if ebay_sku.startswith('A-') or ebay_sku.startswith('M-'): return ebay_sku[2:]
    elif (ebay_sku.startswith('A') or ebay_sku.startswith('M')) and len(ebay_sku) > 10: return ebay_sku[1:]
    return ebay_sku

def defteri_tamamen_esitle():
    file_path = "ebay_toplu_guncelleme.csv"
    print(f"{file_path} okunuyor. Eksik 2009 ürün sadece kimlikleriyle (ASIN/CJ-SKU) Core tabloya ekleniyor...\n")
    
    core_eklenen = 0
    liste_guncellenen = 0
    liste_eklenen = 0
    toplam = 0
    
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            item_id = row.get("ItemID", "").strip()
            ebay_sku = row.get("CustomLabel", "").strip()
            price_str = row.get("StartPrice", "")
            qty_str = row.get("Quantity", "")
            toplam += 1
            
            if not item_id or not ebay_sku:
                continue
                
            price_val = float(price_str) if price_str else 0.0
            qty_val = int(qty_str) if qty_str else 0
            
            # eBay'deki vitrin SKU'sundan gerçek core ID'yi türet
            true_isku = extract_true_asin(ebay_sku)
            
            # 1. Product ID'yi bul
            res_prod = supabase.table("core_products").select("id").eq("isku", true_isku).execute()
            
            if not res_prod.data:
                # Ürün merkezde yok, asıl kimlikle (ASIN) oluştur.
                try:
                    yeni_urun = supabase.table("core_products").insert({
                        "isku": true_isku,
                        "asin": true_isku
                    }).execute()
                    
                    if yeni_urun.data:
                        product_id = yeni_urun.data[0]['id']
                        core_eklenen += 1
                    else:
                        continue 
                except Exception:
                    continue 
            else:
                product_id = res_prod.data[0]['id']
                
            # 2. Ürün artık merkezde var, şimdi Listings tablosunu GÜNCELLE veya EKLE
            res_upd = supabase.table("listings").update({
                "channel_item_id": item_id,
                "channel_sku": ebay_sku,
                "listed_price": price_val,
                "quantity": qty_val,
                "is_active": True,
                "needs_sync": False
            }).eq("product_id", product_id).eq("store_id", STORE_ID).execute()
            
            if res_upd.data:
                liste_guncellenen += 1
            else:
                try:
                    supabase.table("listings").insert({
                        "product_id": product_id,
                        "store_id": STORE_ID,
                        "channel_item_id": item_id,
                        "channel_sku": ebay_sku,
                        "listed_price": price_val,
                        "quantity": qty_val,
                        "is_active": True,
                        "needs_sync": False
                    }).execute()
                    liste_eklenen += 1
                except Exception:
                    pass

            if toplam % 100 == 0:
                print(f"İşlenen: {toplam} | Core Yeni: {core_eklenen} | Liste Güncel: {liste_guncellenen} | Liste Yeni: {liste_eklenen}", end="\r")

    print(f"\n\nSİSTEM TAMAMEN ONARILDI VE EŞİTLENDİ!")
    print(f"- Merkez (Core) Tabloya Eklenen Kayıp Ürün: {core_eklenen}")
    print(f"- Fiyatı/Satusu/Stoğu Güncellenen Mevcut İlan: {liste_guncellenen}")
    print(f"- Vitrine (Listings) Yeni Bağlanan İlan: {liste_eklenen}")

if __name__ == "__main__":
    defteri_tamamen_esitle()