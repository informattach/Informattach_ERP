import os
from dotenv import load_dotenv
from supabase import create_client, Client
import streamlit as st
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self):
        try:
            url: str = st.secrets["SUPABASE_URL"]
            key: str = st.secrets["SUPABASE_KEY"]
        except (FileNotFoundError, KeyError):
            load_dotenv()
            url: str = os.environ.get("SUPABASE_URL")
            key: str = os.environ.get("SUPABASE_KEY")
            
        if not url or not key:
            raise ValueError("SUPABASE_URL ve SUPABASE_KEY bulunamadı!")
        
        self.client: Client = create_client(url, key)

    def create_core_product(self, isku: str, base_title: str, asin: str = None, upc: str = None, requires_expiration: bool = False) -> Dict:
        prod_data = {
            "isku": isku, 
            "asin": asin, 
            "upc": upc, 
            "requires_expiration": requires_expiration
        }
        prod_data = {k: v for k, v in prod_data.items() if v is not None} 
        
        new_prod = self.client.table("core_products").insert(prod_data).execute()
        product_id = new_prod.data[0]['id']
        
        self.client.table("product_base_content").insert({
            "product_id": product_id,
            "base_title": base_title
        }).execute()
        
        self.client.table("product_logistics").insert({
            "product_id": product_id
        }).execute()
        
        return new_prod.data[0]

    def get_product_by_isku(self, isku: str) -> Optional[Dict]:
        response = self.client.table("core_products").select(
            "*, product_base_content(*), product_logistics(*), product_media(*)"
        ).eq("isku", isku).execute()
        
        if response.data:
            return response.data[0]
        return None

    def get_all_core_products(self) -> List[Dict]:
        """Ana ürünleri listeleme ekranı için temel bilgilerle getirir."""
        # select sorgusuna upc eklendi
        response = self.client.table("core_products").select(
            "id, isku, asin, upc, product_base_content(base_title), requires_expiration"
        ).execute()
        return response.data
    def import_easync_data(self, df) -> dict:
        """Tüm veritabanını RAM'e çekerek sıfır ağ gecikmesiyle içe aktarım yapar."""
        st.info("🚀 Veritabanı önbelleğe alınıyor, lütfen bekleyin...")
        success = 0
        errors = 0
        df = df.fillna('')
        
        # --- 1. KALDIRAÇ: TÜM VERİYİ TEK SEFERDE RAM'E ÇEK ---
        # Ağa 4000 kez gitmek yerine, 5 kez gidip her şeyi sözlüklere (dict) alıyoruz.
        mp_data = self.client.table('marketplaces').select('id, name, region').execute().data
        mp_cache = {f"{m['name']}_{m['region']}": m['id'] for m in mp_data}
        
        sup_data = self.client.table('suppliers').select('id, name').execute().data
        supplier_cache = {s['name']: s['id'] for s in sup_data}
        
        store_data = self.client.table('stores').select('id, store_name').execute().data
        store_cache = {s['store_name']: s['id'] for s in store_data}
        
        prod_data = self.client.table('core_products').select('id, isku').execute().data
        prod_cache = {p['isku']: p['id'] for p in prod_data}
        
        list_data = self.client.table('listings').select('product_id, store_id').execute().data
        listing_cache = {f"{l['product_id']}_{l['store_id']}": True for l in list_data}
        
        src_data = self.client.table('sources').select('product_id, supplier_id').execute().data
        source_cache = {f"{s['product_id']}_{s['supplier_id']}": True for s in src_data}

        progress_text = st.empty()
        total_rows = len(df)

        # --- 2. IŞIK HIZINDA DÖNGÜ (Sadece yenileri yazar) ---
        for index, row in df.iterrows():
            if index % 20 == 0 or index == total_rows - 1:
                progress_text.text(f"⚡ RAM Üzerinden İşleniyor: {index + 1} / {total_rows} satır...")

            try:
                # Değişkenler
                title = str(row.get('Title', 'İsimsiz Ürün'))[:200]
                source_id = str(row.get('Source Product Id', '')).strip()
                isku = str(row.get('Target Variant', '')).strip()
                if not isku:
                    isku = f"INF-{source_id}" if source_id else f"INF-UNK-{index}"
                
                clean_asin = source_id if source_id != "" else None
                source_market_raw = str(row.get('Source Market', 'Amazon US'))
                target_market_raw = str(row.get('Target Market', 'eBay US'))
                
                source_price_raw = str(row.get('Source Price', '0')).replace('$', '').replace(',', '').strip()
                source_price = float(source_price_raw) if source_price_raw else 0.0

                target_price_raw = str(row.get('Target Price', '0')).replace('$', '').replace(',', '').strip()
                target_price = float(target_price_raw) if target_price_raw else 0.0
                
                target_item_id = str(row.get('Target Product Id', '')).strip()
                media_url = str(row.get('Target Picture', '')).strip()

                # Pazaryerleri
                s_parts = source_market_raw.split()
                s_name, s_region = s_parts[0], s_parts[-1] if len(s_parts) > 1 else "US"
                s_mp_key = f"{s_name}_{s_region}"
                if s_mp_key not in mp_cache:
                    res = self.client.table('marketplaces').insert({'name': s_name, 'region': s_region}).execute()
                    mp_cache[s_mp_key] = res.data[0]['id']
                mp_source_id = mp_cache[s_mp_key]

                t_parts = target_market_raw.split()
                t_name, t_region = t_parts[0], t_parts[-1] if len(t_parts) > 1 else "US"
                t_mp_key = f"{t_name}_{t_region}"
                if t_mp_key not in mp_cache:
                    res = self.client.table('marketplaces').insert({'name': t_name, 'region': t_region}).execute()
                    mp_cache[t_mp_key] = res.data[0]['id']
                mp_target_id = mp_cache[t_mp_key]

                # Tedarikçi ve Mağaza
                if source_market_raw not in supplier_cache:
                    res = self.client.table('suppliers').insert({'marketplace_id': mp_source_id, 'supplier_type': 'Marketplace_Account', 'name': source_market_raw}).execute()
                    supplier_cache[source_market_raw] = res.data[0]['id']
                supplier_id = supplier_cache[source_market_raw]

                if target_market_raw not in store_cache:
                    res = self.client.table('stores').insert({'marketplace_id': mp_target_id, 'store_name': target_market_raw}).execute()
                    store_cache[target_market_raw] = res.data[0]['id']
                store_id = store_cache[target_market_raw]

                # Çekirdek Ürün (Eksik olan else bloğu eklendi)
                if isku not in prod_cache:
                    res = self.client.table('core_products').insert({'isku': isku, 'asin': clean_asin}).execute()
                    product_id = res.data[0]['id']
                    prod_cache[isku] = product_id # RAM'i de güncelle
                    
                    self.client.table('product_base_content').insert({'product_id': product_id, 'base_title': title}).execute()
                    if media_url:
                        self.client.table('product_media').insert({'product_id': product_id, 'media_url': media_url, 'is_main': True}).execute()
                else:
                    product_id = prod_cache[isku] # Hatanın çözümü tam olarak burası

                # Kavşaklar (Sources ve Listings)
                src_key = f"{product_id}_{supplier_id}"
                if src_key not in source_cache:
                    self.client.table('sources').insert({'product_id': product_id, 'supplier_id': supplier_id, 'source_code': source_id, 'base_cost': source_price}).execute()
                    source_cache[src_key] = True

                lst_key = f"{product_id}_{store_id}"
                if lst_key not in listing_cache:
                    self.client.table('listings').insert({'product_id': product_id, 'store_id': store_id, 'channel_item_id': target_item_id, 'listed_price': target_price}).execute()
                    listing_cache[lst_key] = True

                success += 1
            except Exception as e:
                st.error(f"Satır {index} Hatası: {str(e)}")
                errors += 1
                continue
                
        progress_text.empty()
        return {"success": success, "errors": errors}
db = DatabaseManager()