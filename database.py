import os
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import List, Dict, Optional

# Yapılandırmayı yükle
load_dotenv()

class DatabaseManager:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL ve SUPABASE_KEY ortam değişkenleri eksik!")
        self.supabase: Client = create_client(url, key)

    # --- Ürün İşlemleri ---
    def get_all_products(self) -> List[Dict]:
        """Tüm ürünleri ve bunlara bağlı kaynak/listeleme bilgilerini çeker."""
        # PostgreSQL ilişkilerini kullanarak tek sorguda join işlemi yapar
        response = self.supabase.table("products").select("*, sources(*), listings(*)").execute()
        return response.data

    def get_product_by_sku(self, master_sku: str) -> Optional[Dict]:
        """Belirli bir Master SKU'ya ait detaylı veriyi getirir."""
        response = self.supabase.table("products").select("*, sources(*), listings(*)").eq("master_sku", master_sku).single().execute()
        return response.data

    def create_product(self, master_sku: str, title: str) -> Dict:
        """Ana ürün havuzuna yeni ürün ekler."""
        data = {"master_sku": master_sku, "title": title}
        response = self.supabase.table("products").insert(data).execute()
        return response.data[0]

    # --- Kaynak (Source) İşlemleri ---
    def upsert_source_data(self, product_id: str, platform: str, cost: float, stock: bool):
        """Tedarikçi verisini günceller veya yoksa ekler."""
        payload = {
            "product_id": product_id,
            "platform": platform,
            "cost_price": cost,
            "stock_status": stock
        }
        # product_id ve platform bileşik anahtar gibi davranıyorsa upsert kullanılabilir
        response = self.supabase.table("sources").upsert(payload).execute()
        return response.data

    # --- Listeleme (Listing) İşlemleri ---
    def update_listing_price(self, listing_id: str, new_price: float):
        """Belirli bir listelemenin fiyatını günceller."""
        response = self.supabase.table("listings").update({"listed_price": new_price}).eq("id", listing_id).execute()
        return response.data
    def get_pricing_rule(self, marketplace: str) -> Optional[Dict]:
        """Pazar yerine özel fiyatlandırma kurallarını getirir."""
        response = self.supabase.table("pricing_rules").select("*").eq("marketplace", marketplace).single().execute()
        return response.data
# Singleton pattern için hazır instance
db = DatabaseManager()