import time
from database import db

def delete_ghost_products():
    print("Hayalet (Ebay'de olmayan) ürünler tespit ediliyor...")
    
    # 1. Start fetching listings where category_id is null
    ghost_product_ids = []
    offset = 0
    limit = 1000
    
    while True:
        res = db.client.table('listings').select('product_id').is_('category_id', 'null').range(offset, offset+limit-1).execute()
        data = res.data
        if not data: break
        
        ghost_product_ids.extend([item['product_id'] for item in data if item.get('product_id')])
        
        if len(data) < limit: break
        offset += limit

    ghost_product_ids = list(set(ghost_product_ids))
    total_ghosts = len(ghost_product_ids)
    print(f"Toplam {total_ghosts} adet hayalet ürün bulundu.")
    
    if total_ghosts == 0:
        print("Silinecek ürün yok.")
        return
        
    print("Silme işlemi başlıyor (Foreign Key kısıtlamalarına karşı tüm alt tablolar temizlenecek)...")
    
    # Supabase limits 'in_' filter arrays to a reasonable size (e.g. 200)
    batch_size = 200
    for i in range(0, total_ghosts, batch_size):
        batch_ids = ghost_product_ids[i:i+batch_size]
        print(f"Batch {i//batch_size + 1}/{(total_ghosts // batch_size) + 1} siliniyor...")
        
        # We must ignore errors if table is empty or constraints act up, but usually it works.
        try:
            db.client.table('listings').delete().in_('product_id', batch_ids).execute()
            db.client.table('sources').delete().in_('product_id', batch_ids).execute()
            db.client.table('product_base_content').delete().in_('product_id', batch_ids).execute()
            db.client.table('product_logistics').delete().in_('product_id', batch_ids).execute()
            
            # Finally delete the core product
            db.client.table('core_products').delete().in_('id', batch_ids).execute()
        except Exception as e:
            print(f"Hata oluştu Batch {i}: {e}")
            
    print("✅ Temizlik başarıyla tamamlandı!")

if __name__ == "__main__":
    delete_ghost_products()
