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
        """Easync DataFrame'ini okur ve 5 tablolu normalize mimariye dağıtır."""
        success = 0
        errors = 0
        
        # Pandas NaN değerlerini boş string'e çevir
        df = df.fillna('')
        
        for index, row in df.iterrows():
            try:
                # 1. Temel Değişkenleri Yakala
                title = str(row.get('Title', 'İsimsiz Ürün'))[:200]
                source_id = str(row.get('Source Product Id', '')).strip() # ASIN
                isku = str(row.get('Target Variant', '')).strip()
                if not isku:
                    isku = f"INF-{source_id}" if source_id else f"INF-UNK-{index}"
                
                source_market_raw = str(row.get('Source Market', 'Amazon US'))
                target_market_raw = str(row.get('Target Market', 'eBay US'))
                
                source_price = float(row.get('Source Price', 0)) if row.get('Source Price') else 0.0
                target_price = float(row.get('Target Price', 0)) if row.get('Target Price') else 0.0
                target_item_id = str(row.get('Target Product Id', '')).strip()
                media_url = str(row.get('Target Picture', '')).strip()

                # 2. PAZARYERLERİ (Get or Create)
                s_parts = source_market_raw.split()
                s_name, s_region = s_parts[0], s_parts[-1] if len(s_parts) > 1 else "US"
                
                t_parts = target_market_raw.split()
                t_name, t_region = t_parts[0], t_parts[-1] if len(t_parts) > 1 else "US"

                # Kaynak Pazaryeri
                mp_source = self.client.table('marketplaces').select('id').eq('name', s_name).eq('region', s_region).execute()
                if not mp_source.data:
                    mp_source = self.client.table('marketplaces').insert({'name': s_name, 'region': s_region}).execute()
                mp_source_id = mp_source.data[0]['id']

                # Hedef Pazaryeri
                mp_target = self.client.table('marketplaces').select('id').eq('name', t_name).eq('region', t_region).execute()
                if not mp_target.data:
                    mp_target = self.client.table('marketplaces').insert({'name': t_name, 'region': t_region}).execute()
                mp_target_id = mp_target.data[0]['id']

                # 3. TEDARİKÇİ VE MAĞAZA (Get or Create)
                supplier = self.client.table('suppliers').select('id').eq('name', source_market_raw).execute()
                if not supplier.data:
                    supplier = self.client.table('suppliers').insert({
                        'marketplace_id': mp_source_id, 'supplier_type': 'Marketplace_Account', 'name': source_market_raw
                    }).execute()
                supplier_id = supplier.data[0]['id']

                store = self.client.table('stores').select('id').eq('store_name', target_market_raw).execute()
                if not store.data:
                    store = self.client.table('stores').insert({
                        'marketplace_id': mp_target_id, 'store_name': target_market_raw
                    }).execute()
                store_id = store.data[0]['id']

                # 4. ÇEKİRDEK ÜRÜN VE İÇERİK (Get or Create)
                product = self.client.table('core_products').select('id').eq('isku', isku).execute()
                if not product.data:
                    prod_ins = self.client.table('core_products').insert({'isku': isku, 'asin': source_id}).execute()
                    product_id = prod_ins.data[0]['id']
                    
                    self.client.table('product_base_content').insert({'product_id': product_id, 'base_title': title}).execute()
                    if media_url:
                        self.client.table('product_media').insert({'product_id': product_id, 'media_url': media_url, 'is_main': True}).execute()
                else:
                    product_id = product.data[0]['id']

                # 5. KAVŞAKLAR: SOURCES VE LISTINGS (Upsert mantığı)
                # Tedarik Ağı (Sources)
                source_check = self.client.table('sources').select('id').eq('product_id', product_id).eq('supplier_id', supplier_id).execute()
                if not source_check.data:
                    self.client.table('sources').insert({
                        'product_id': product_id, 'supplier_id': supplier_id, 'source_code': source_id, 'base_cost': source_price
                    }).execute()

                # Satış Ağı (Listings)
                listing_check = self.client.table('listings').select('id').eq('product_id', product_id).eq('store_id', store_id).execute()
                if not listing_check.data:
                    self.client.table('listings').insert({
                        'product_id': product_id, 'store_id': store_id, 'channel_item_id': target_item_id, 'listed_price': target_price
                    }).execute()

                success += 1
            except Exception as e:
                # Hatayı yutmak yerine artık ekranda kırmızı kırmızı gösterecek
                st.error(f"Satır {index} Hatası: {str(e)}") 
                errors += 1
                continue
                
        return {"success": success, "errors": errors}
db = DatabaseManager()