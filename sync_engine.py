import time
from database import db
from ebay_core import EbayManager

STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"

class PushEngine:
    def __init__(self):
        self.db = db
        self.ebay = EbayManager(store_id=STORE_ID)
        
    def get_pending_updates(self):
        """needs_sync=True olan tüm aktif ilanları Supabase'den çeker."""
        response = self.db.client.table('listings').select(
            "product_id, channel_item_id, channel_sku, listed_price, quantity, category_id, shipping_profile_id, return_profile_id, payment_profile_id"
        ).eq("needs_sync", True).eq("is_active", True).execute()
        return response.data

    def push_updates(self):
        """Kuyruktaki güncellemeleri ReviseFixedPriceItem ile eBay'e basar ve başarılı olanları needs_sync=False yapar."""
        items_to_sync = self.get_pending_updates()
        total_items = len(items_to_sync)
        
        if total_items == 0:
            return {"status": "info", "message": "Gönderilecek güncelleme bulunamadı."}
            
        success_count = 0
        error_count = 0
        logs = []
        
        for item in items_to_sync:
            item_id = item.get('channel_item_id')
            if not item_id:
                logs.append(f"❌ HATA: {item.get('channel_sku')} için eBay ItemID bulunamadı.")
                error_count += 1
                continue
                
            payload = {}
            if item.get('listed_price') is not None:
                payload["StartPrice"] = item.get('listed_price')
            if item.get('quantity') is not None:
                payload["Quantity"] = item.get('quantity')
            if item.get('category_id'):
                payload["CategoryID"] = item.get('category_id')
                
            # Politikalar
            profiles = {}
            if item.get('payment_profile_id'): profiles['PaymentProfileID'] = item.get('payment_profile_id')
            if item.get('return_profile_id'): profiles['ReturnProfileID'] = item.get('return_profile_id')
            if item.get('shipping_profile_id'): profiles['ShippingProfileID'] = item.get('shipping_profile_id')
            if profiles:
                payload["SellerProfiles"] = profiles
                
            if not payload:
                # Güncellenecek detay yoksa atla
                self.db.client.table('listings').update({"needs_sync": False}).eq("product_id", item['product_id']).execute()
                continue
                
            # eBay'e XML gönder
            result = self.ebay.revise_item_xml(item_id, payload)
            
            if result['success']:
                success_count += 1
                # Supabase'i güncelle
                self.db.client.table('listings').update({"needs_sync": False}).eq("product_id", item['product_id']).execute()
            else:
                error_count += 1
                logs.append(f"❌ {item.get('channel_sku')}: {result['message']}")
                
        # Özet Dön
        return {
            "status": "success" if error_count == 0 else "warning",
            "message": f"{success_count} ürün başarıyla güncellendi, {error_count} hata.",
            "logs": logs
        }

if __name__ == "__main__":
    engine = PushEngine()
    print("Test Push Çalıştırılıyor...")
    res = engine.push_updates()
    print(res)
