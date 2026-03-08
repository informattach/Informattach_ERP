import time
import json
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta
from database import db
from ebay_core import EbayManager

# Fatih Bey'in ana Store ID'si
STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"

class EbayApiIntegrator:
    def __init__(self):
        self.db = db
        self.ebay = EbayManager(store_id=STORE_ID)
        self.token = self.ebay.get_valid_token()
        self.namespace = "{urn:ebay:apis:eBLBaseComponents}"
        
        # Local Caches for batching
        self.listings_cache = self._load_listings_cache()
        self.categories_to_upsert = {}

    def _load_listings_cache(self):
        """Loads all current listings into a dictionary keyed by channel_sku and channel_item_id for ultra-fast matching."""
        cache = {'by_sku': {}, 'by_item_id': {}}
        print("Mevcut veri tabanı belleğe alınıyor (Cache)...")
        offset = 0
        limit = 1000
        while True:
            res = self.db.client.table('listings').select('id, product_id, channel_sku, channel_item_id').range(offset, offset+limit-1).execute()
            data = res.data
            if not data: break
            
            for row in data:
                if row.get('channel_sku'):
                    cache['by_sku'][row['channel_sku']] = row
                if row.get('channel_item_id'):
                    cache['by_item_id'][row['channel_item_id']] = row
                    
            if len(data) < limit: break
            offset += limit
            
        print(f"Toplam {len(cache['by_sku'])} SKU ve {len(cache['by_item_id'])} ItemID eşleşmesi hazırlandı.")
        return cache

    def xml_get_seller_list(self, page):
        now = datetime.utcnow()
        end_from = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_to = (now + timedelta(days=119)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <DetailLevel>ItemReturnDescription</DetailLevel>
  <Pagination>
    <EntriesPerPage>100</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <EndTimeFrom>{end_from}</EndTimeFrom>
  <EndTimeTo>{end_to}</EndTimeTo>
  <OutputSelector>ItemID</OutputSelector>
  <OutputSelector>SKU</OutputSelector>
  <OutputSelector>SellingStatus</OutputSelector>
  <OutputSelector>Title</OutputSelector>
  <OutputSelector>PrimaryCategory</OutputSelector>
  <OutputSelector>SellerProfiles</OutputSelector>
  <OutputSelector>ItemSpecifics</OutputSelector>
  <OutputSelector>Quantity</OutputSelector>
  <OutputSelector>PaginationResult</OutputSelector>
  <OutputSelector>HasMoreItems</OutputSelector>
</GetSellerListRequest>
"""
        headers = {
            "X-EBAY-API-SITEID": "0",  
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1199",
            "X-EBAY-API-CALL-NAME": "GetSellerList",
            "X-EBAY-API-IAF-TOKEN": self.token, 
            "Content-Type": "text/xml"
        }
        url = "https://api.ebay.com/ws/api.dll"
        res = requests.post(url, data=xml, headers=headers)
        if res.status_code == 200:
            return res.text
        else:
            print(f"HTTP Error {res.status_code}: {res.text[:500]}")
            return None

    def _parse_item_specifics(self, item_node):
        specifics = {}
        spec_node = item_node.find(f"{self.namespace}ItemSpecifics")
        if spec_node is not None:
            for nvl in spec_node.findall(f"{self.namespace}NameValueList"):
                name = nvl.find(f"{self.namespace}Name")
                val = nvl.find(f"{self.namespace}Value")
                if name is not None and val is not None:
                    # Clean the key to avoid JSON key issues if any, though mostly fine
                    specifics[name.text] = val.text
        return specifics

    def sync_catalog(self):
        page = 1
        matched_count = 0
        unmatched_count = 0
        
        # Batch update lists
        listings_updates = []
        product_content_updates = []
        
        print("\neBay API'den katalog çekiliyor ve senkronize ediliyor...")
        while True:
            print(f" Sayfa {page} taranıyor...")
            xml_data = self.xml_get_seller_list(page)
            if not xml_data: break
            
            root = ET.fromstring(xml_data)
            items = root.findall(f".//{self.namespace}Item")
            if not items: break
            
            for item in items:
                # 1. Extract Core Data
                item_id = item.find(f"{self.namespace}ItemID")
                sku_node = item.find(f"{self.namespace}SKU")
                title_node = item.find(f"{self.namespace}Title")
                cat_node = item.find(f"{self.namespace}PrimaryCategory")
                qty_node = item.find(f"{self.namespace}Quantity")
                
                item_id_val = item_id.text if item_id is not None else None
                sku_val = sku_node.text if sku_node is not None else None
                title_val = title_node.text if title_node is not None else None
                qty_val = int(qty_node.text) if qty_node is not None and qty_node.text else 0
                
                cat_id_val, cat_name_val = None, None
                if cat_node is not None:
                    cid = cat_node.find(f"{self.namespace}CategoryID")
                    cname = cat_node.find(f"{self.namespace}CategoryName")
                    cat_id_val = cid.text if cid is not None else None
                    cat_name_val = cname.text if cname is not None else None
                    
                specifics_val = self._parse_item_specifics(item)

                if not item_id_val: continue
                
                # Maintain category dictionary
                if cat_id_val and cat_name_val:
                    self.categories_to_upsert[cat_id_val] = cat_name_val
                
                # 2. Match with Database
                matched_row = None
                if sku_val and sku_val in self.listings_cache['by_sku']:
                    matched_row = self.listings_cache['by_sku'][sku_val]
                elif item_id_val in self.listings_cache['by_item_id']:
                    matched_row = self.listings_cache['by_item_id'][item_id_val]
                
                if matched_row:
                    matched_count += 1
                    # Prepare update payload for listings
                    l_payload = {
                        "id": matched_row['id'],
                        "channel_item_id": item_id_val,
                        "category_id": cat_id_val,
                        "quantity": qty_val,
                        "item_specifics": specifics_val
                    }
                    if sku_val:
                         l_payload["channel_sku"] = sku_val
                    listings_updates.append(l_payload)
                    
                    # Prepare update payload for product_base_content if title exists
                    if title_val and matched_row.get('product_id'):
                        product_content_updates.append({
                            "product_id": matched_row['product_id'],
                            "base_title": title_val
                        })
                else:
                    unmatched_count += 1

            # Pagination check
            has_more = root.find(f".//{self.namespace}HasMoreItems")
            if has_more is None or has_more.text.lower() != 'true':
                break
            page += 1

        print(f"\nTarama Tamamlandı. {matched_count} eşleşen, {unmatched_count} eşleşmeyen ürün.")
        
        # 3. Commit Updates to Supabase in Batches
        print("\nVeritabanı güncellemeleri yapılıyor (Bu işlem birkaç saniye sürebilir)...")
        
        # Upsert Categories
        if self.categories_to_upsert:
            cat_payload = []
            for cid, cname in self.categories_to_upsert.items():
                cat_payload.append({
                    "marketplace": "ebay",
                    "category_id": cid,
                    "category_name": cname,
                    # We leave marketplace_fee_percent as null so user can set it, or default to 15 later
                })
            
            # Batch upsert categories
            for i in range(0, len(cat_payload), 500):
                self.db.client.table('marketplace_categories').upsert(cat_payload[i:i+500], on_conflict='marketplace,category_id').execute()
            print(f"- {len(cat_payload)} Kategori sözlüğe eklendi/güncellendi.")
            
        # Deduplicate the arrays just before upserting!
        unique_listings = list({item['id']: item for item in listings_updates}.values())
        unique_products = list({item['product_id']: item for item in product_content_updates}.values())

        # Update Listings (Needs multiple batched operations)
        if unique_listings:
            for i in range(0, len(unique_listings), 1000):
                try:
                    self.db.client.table('listings').upsert(unique_listings[i:i+1000]).execute()
                except Exception as e:
                    print(f"Listings Upsert Hatası: {e}")
            print(f"- {len(unique_listings)} Listings kaydı (ItemSpecifics, CategoryID, ItemID) güncellendi.")
            
        # Update Product Titles
        if unique_products:
            # Upsert product_base_content mapping product_id to title
            # Since product_id is primary key of product_base_content, upsert works perfectly
            for i in range(0, len(unique_products), 1000):
                try:
                    self.db.client.table('product_base_content').upsert(unique_products[i:i+1000]).execute()
                except Exception as e:
                    print(f"Product Content Upsert Hatası: {e}")
            print(f"- {len(unique_products)} Ürün Başlığı (Product Title) güncellendi.")
            
        print("\n✅ eBay Entegrasyonu ve Zenginleştirme Başarıyla Tamamlandı!")

if __name__ == "__main__":
    integrator = EbayApiIntegrator()
    integrator.sync_catalog()
