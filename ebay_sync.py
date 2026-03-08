import requests
from ebay_core import EbayManager, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_ebay_inventory(store_id):
    manager = EbayManager(store_id=store_id)
    token = manager.get_valid_token()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    # eBay Inventory API - Tüm ürünleri çekme endpoint'i
    base_url = "https://api.ebay.com/sell/inventory/v1/inventory_item"
    limit = 100
    offset = 0
    total_synced = 0
    
    print("eBay envanteri taranıyor. Bu işlem ürün sayısına göre birkaç dakika sürebilir...\n")
    
    while True:
        url = f"{base_url}?limit={limit}&offset={offset}"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"HATA OLUŞTU ({response.status_code}): {response.text}")
            break
            
        data = response.json()
        items = data.get('inventoryItems', [])
        
        if not items:
            break # Çekilecek ürün kalmadı
            
        for item in items:
            sku = item.get('sku')
            product = item.get('product', {})
            title = product.get('title', 'Başlık Yok')
            
            # Şimdilik sadece terminale basıyoruz, sonra Supabase'e yazacağız
            print(f"SKU: {sku} | Başlık: {title[:50]}...")
            total_synced += 1
            
        # Sayfalama: Sonraki 100 ürüne geç
        offset += limit
        
        # eBay'in toplam ürün sayısına ulaştıysak döngüyü bitir
        if offset >= data.get('total', 0):
            break

    print(f"\nTARAMA TAMAMLANDI. Toplam {total_synced} benzersiz ürün SKU'su eBay'den çekildi.")

if __name__ == "__main__":
    # Kendi mağaza UUID'ni buraya gir
    STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee" 
    sync_ebay_inventory(STORE_ID)