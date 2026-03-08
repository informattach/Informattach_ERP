import pandas as pd
import glob
import os
import asyncio
import aiohttp
from datetime import datetime
from database import db
from pricing_engine import PricingEngine

async def update_item(session, url, headers, item):
    product_id = item['product_id']
    try:
        # Check if exists
        get_url = f"{url}?product_id=eq.{product_id}&select=id"
        async with session.get(get_url, headers=headers) as resp:
            data = await resp.json()
            
        if data and len(data) > 0:
            # Update (Patch)
            patch_url = f"{url}?product_id=eq.{product_id}"
            payload = {"base_cost": item['base_cost'], "updated_at": item['updated_at']}
            async with session.patch(patch_url, headers=headers, json=payload) as resp:
                if resp.status not in [200, 204]:
                    print(f"PATCH Error {product_id}: {await resp.text()}")
                return resp.status in [200, 204]
        else:
            # Insert (Post)
            async with session.post(url, headers=headers, json=item) as resp:
                    if resp.status in [200, 201, 204]:
                        return True
                    else:
                        print(f"Hata ({product_id}): HTTP Code {resp.status} - {await resp.text()}")
                        return False
    except Exception as e:
        print(f"Local Error in HTTP update {product_id}: {e}")
        return False

async def update_listing_item(session, url, headers, item):
    product_id = item['product_id']
    try:
        get_url = f"{url}?product_id=eq.{product_id}&select=id"
        async with session.get(get_url, headers=headers) as resp:
            data = await resp.json()
            
        if data and len(data) > 0:
            patch_url = f"{url}?product_id=eq.{product_id}"
            payload = {"listed_price": item['listed_price'], "updated_at": item['updated_at'], "needs_sync": True}
            async with session.patch(patch_url, headers=headers, json=payload) as resp:
                return resp.status in [200, 204]
        # We don't insert here, listings should exist
        return True 
    except Exception as e:
        return False

async def bulk_push(sources_updates, listings_updates):
    print(f"Büyük veri paketi {len(sources_updates)} gönderime hazırlanıyor (Asenkron İşlem)...")
    success_count = 0
    listings_count = 0
    
    from dotenv import load_dotenv
    load_dotenv()
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    sources_url = f"{SUPABASE_URL}/rest/v1/sources"
    listings_url = f"{SUPABASE_URL}/rest/v1/listings"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        # Push to sources table
        tasks_s = [update_item(session, sources_url, headers, item) for item in sources_updates]
        results_s = await asyncio.gather(*tasks_s)
        success_count = sum(1 for r in results_s if r)
        
        # Push to listings table
        print(f"Satış Fiyatları da ({len(listings_updates)}) listelere hesaplanıp yükleniyor...")
        tasks_l = [update_listing_item(session, listings_url, headers, item) for item in listings_updates]
        results_l = await asyncio.gather(*tasks_l)
        listings_count = sum(1 for r in results_l if r)
        
    return success_count, listings_count

def run_import():
    print("Amazon Wishlist Sonuç Dosyası (Fiyatlar) taranıyor...")
    
    xlsx_files = [f for f in glob.glob("*.xlsx") if "amazon_y" not in f.lower() and f != "exportedList.xlsx" and f != "exportedList_1ZJ8ON753X26T.xlsx" and not f.startswith("~$")]
    
    if not xlsx_files:
        print("HATA: Amazon'dan inen 'Fiyatlı' yeni sonuç dosyası bulunamadı!")
        return
        
    latest_file = max(xlsx_files, key=os.path.getmtime)
    print(f"✅ Amazon listesi bulundu: {latest_file}")
    
    try:
        df = pd.read_excel(latest_file, header=None, skiprows=13)
        valid_rows = df[df[1] != 'EMPTY'].dropna(subset=[1])
        print(f"Toplam {len(valid_rows)} adet geçerli ürün barındırıyor.")
        
        missing_count = 0
        
        print("Supabase'den Ürün ID haritası alınıyor...")
        all_products = []
        offset = 0
        limit_size = 1000
        while True:
            res_chunk = db.client.table('core_products').select('id, asin').range(offset, offset + limit_size - 1).execute()
            if not res_chunk.data:
                break
            all_products.extend(res_chunk.data)
            offset += limit_size
            if len(res_chunk.data) < limit_size:
                break
                
        asin_to_id = {row['asin']: row['id'] for row in all_products if row.get('asin')}
        
        sources_updates = []
        listings_updates = []
        for _, row in valid_rows.iterrows():
            asin = str(row[1]).strip().upper()
            raw_price = str(row[7]).strip()
            
            if raw_price.lower() in ['nan', 'none', '', 'currently unavailable.']:
                missing_count += 1
                continue
                
            clean_price_str = raw_price.replace('$', '').replace(',', '').strip()
            try:
                price_val = float(clean_price_str)
            except:
                missing_count += 1
                continue
                
            product_id = asin_to_id.get(asin)
            
            if product_id:
                sources_updates.append({
                    "product_id": product_id,
                    "supplier_id": "c71e8609-0d19-450c-b258-20a2e379b183",
                    "base_cost": price_val,
                    "source_url": f"https://www.amazon.com/dp/{asin}",
                    "updated_at": datetime.utcnow().isoformat()
                })
                
                # Fiyatı hesapla ve Listelere bas (ebay store ID si filan girmeyiz, zaten patch ediyoruz)
                final_listed_price = PricingEngine.calculate_final_price(price_val, marketplace="ebay")
                listings_updates.append({
                    "product_id": product_id,
                    "listed_price": final_listed_price,
                    "updated_at": datetime.utcnow().isoformat()
                })
                
        if sources_updates:
            s_count, l_count = asyncio.run(bulk_push(sources_updates, listings_updates))
            print(f"🎯 GÜNCELLEME TAMAMLANDI! {s_count} Maliyet, {l_count} Satış Fiyatı işlendi (Geri kalan {missing_count} tanesi stokta yok).")
        else:
            print("Güncellenecek geçerli fiyat bulunamadı.")
            
    except Exception as e:
        print(f"Hata: {e}")

if __name__ == "__main__":
    run_import()
