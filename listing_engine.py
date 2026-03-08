import os
import time
from typing import Dict, Any, List

from database import db
from pricing_engine import PricingEngine
from gemini_assistant import GeminiAssistant
from ebay_core import EbayManager

# Genel Kategoriler (Eğer CSV'de yoksa Fallback)
DEFAULT_CATEGORY = "30120"
# Mağaza ID (Şimdilik Sabit - Informattach Main Store)
STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"


class ListingEngine:
    def __init__(self):
        self.ai = GeminiAssistant()
        self.ebay = EbayManager(store_id=STORE_ID)

    def process_drafts_to_ebay(self, draft_ids: List[int]) -> Dict[str, Any]:
        """
        Draft tablosundan seçilen kimlikleri sırasıyla okur ve eBay'e postalar.
        """
        results = {"success": 0, "failed": 0, "skipped": 0, "details": []}
        
        for draft_id in draft_ids:
            try:
                # 1. Draft bilgisini çek
                draft_res = db.client.table("draft").select("*").eq("id", draft_id).execute()
                if not draft_res.data:
                    results["failed"] += 1
                    results["details"].append(f"Draft {draft_id} bulunamadı.")
                    continue
                    
                draft_data = draft_res.data[0]
                asin = draft_data.get("product_id")
                
                # 2. [KRİTİK GEREKSİNİM] Benzersizlik Kontrolü (Daha önce eklendi mi?)
                if self._is_asin_already_listed(asin):
                    # Kayıtlı ürünü atla (Kota İsrafını Önleme)
                    results["skipped"] += 1
                    results["details"].append(f"[{asin}] Zaten Listelenmiş (Atlandı).")
                    
                    # Draft'ı sync olarak işaretle, listeden düşsün.
                    db.client.table("draft").update({"needs_sync": False}).eq("id", draft_id).execute()
                    continue
                
                print(f"[{asin}] İşlem başlatılıyor...")
                
                # 3. Fiyatlandırma ve Özellikler
                raw_price = float(draft_data.get("price", 0))
                calc_price = PricingEngine.calculate_final_price(
                    source_price=raw_price,
                    marketplace="ebay"
                )
                
                # Minimum satılabilirlik kontrolü
                if calc_price <= 0:
                    results["failed"] += 1
                    results["details"].append(f"[{asin}] Maliyet hesaplanamadı veya $0.")
                    continue
                
                qty = int(draft_data.get("stock_quantity", 3))
                title = draft_data.get("title", f"Product {asin}")
                
                # Ekstra özellikler (Eğer varsa)
                features = []
                extra = draft_data.get("extra_data", {})
                if extra:
                    for k, v in extra.items():
                        features.append(f"{k}: {v}")
                
                # 4. Yapay Zeka SEO Açıklaması
                print(f"[{asin}] Gemini SEO Açıklama üretiliyor...")
                html_desc = self.ai.generate_ebay_html(title=title, features=features)
                
                # 5. eBay REST/XML Hibrit Yayına Alma
                # Store'un varsayılan kargo politikalarını DB'den veya config'den çekmeliyiz.
                # Şimdilik store_id'ye ait sabit profilleri mockluyoruz. (İlerde veritabanından dinamik alınır)
                policies = {
                    "fulfillment_id": "251361629010", 
                    "payment_id": "244346933010",     
                    "return_id": "251407823010"       
                }
                
                isku = f"INF-{asin}"
                images = [] # İleride Amazon Scraping ile buraya eklenecek
                
                print(f"[{asin}] eBay'e gönderiliyor... (Otonom Fiyat: ${calc_price})")
                
                # Önce REST Inventory API denenir, hata verirse XML'e düşer.
                ebay_result = ""
                try:
                    ebay_result = self.ebay.create_and_publish_offer(isku, policies)
                    # Hata mesajı dönmüşse exception fırlatalım ki fallback çalışsın
                    if "Hatası" in ebay_result:
                        raise Exception(ebay_result)
                except Exception as rest_e:
                    print(f"[{asin}] REST API Başarısız: {rest_e}. XML Fallback deneniyor...")
                    # XML Fallback
                    try:
                        ebay_result = self.ebay.create_and_publish_offer_xml_fallback(
                            sku=isku,
                            title=title,
                            description_html=html_desc,
                            price=calc_price,
                            quantity=qty,
                            policies=policies,
                            category_id=DEFAULT_CATEGORY,
                            image_urls=images
                        )
                        if "Hatası" in ebay_result:
                            raise Exception(ebay_result)
                    except Exception as xml_e:
                        raise Exception(f"Ebay Yayına Alım Tamamen Başarısız. REST: {rest_e} | XML: {xml_e}")

                # 6. Başarılı ise Ana Veritabanına (core_products ve listings) Kaydet
                print(f"[{asin}] Veritabanına işleniyor... Sonuç: {ebay_result}")
                self._save_to_core_db(asin, isku, title, draft_id, raw_price, calc_price, qty)
                
                results["success"] += 1
                results["details"].append(f"[{asin}] Başarılı: {ebay_result}")
                
            except Exception as e:
                results["failed"] += 1
                results["details"].append(f"[{draft_data.get('product_id', 'Unk')}] Hata: {str(e)}")
                
        return results

    def _is_asin_already_listed(self, asin: str) -> bool:
        """
        Kritik Benzersizlik Kontrolü:
        core_products tablosunda bu asin var mı ve listings tablosunda bu ürün aktif mi?
        """
        res = db.client.table("core_products").select("id").eq("asin", asin).execute()
        if not res.data:
            return False
            
        product_id = res.data[0]["id"]
        
        # Sadece ürünü tanımak yetmez, eBay'de aktif bir ilanı var mı diye de bakalım:
        l_res = db.client.table("listings").select("id").eq("product_id", product_id).eq("store_id", STORE_ID).execute()
        
        return len(l_res.data) > 0

    def _save_to_core_db(self, asin, isku, title, draft_id, base_cost, listed_price, qty):
        # 1. Core Product Insert
        p_res = db.client.table("core_products").upsert({"asin": asin}).execute()
        p_id = p_res.data[0]["id"]
        
        # 2. Ürün İçeriği
        db.client.table("product_base_content").upsert({
            "product_id": p_id,
            "base_title": title[:255]
        }).execute()
        
        # 3. Source Insert (Amazon'dan geldiği varsayımıyla)
        # Supplier ID'sini bulalım (Yoksa oluşturalım)
        sup_res = db.client.table("suppliers").select("id").eq("name", "Amazon US").execute()
        sup_id = sup_res.data[0]["id"] if sup_res.data else None
        
        if sup_id:
            db.client.table("sources").upsert({
                "product_id": p_id,
                "supplier_id": sup_id,
                "source_code": asin,
                "base_cost": base_cost
            }).execute()
            
        # 4. eBay İlanını Listelere Ekle
        db.client.table("listings").upsert({
            "product_id": p_id,
            "store_id": STORE_ID,
            "channel_sku": isku,
            "listed_price": listed_price,
            "quantity": qty,
            "is_active": True,
            "needs_sync": False
        }).execute()
        
        # 5. Draft tablosundan düş
        db.client.table("draft").update({"needs_sync": False}).eq("id", draft_id).execute()

if __name__ == "__main__":
    engine = ListingEngine()
    print("Listing Engine Hazır!")
