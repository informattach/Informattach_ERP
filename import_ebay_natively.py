import sys
import xml.etree.ElementTree as ET
from database import db
from ebay_api_integrator import EbayApiIntegrator

def get_or_create_supplier_store():
    # Load marketplace cache
    mp_data = db.client.table('marketplaces').select('id, name, region').execute().data
    mp_cache = {f"{m['name']}_{m['region']}": m['id'] for m in mp_data}
    
    # Load Supplier Cache (Amazon US)
    sup_data = db.client.table('suppliers').select('id, name').execute().data
    supplier_cache = {s['name']: s['id'] for s in sup_data}
    
    # Load Store Cache (eBay US)
    store_data = db.client.table('stores').select('id, store_name').execute().data
    store_cache = {s['store_name']: s['id'] for s in store_data}
    
    source_market_raw = 'Amazon US'
    target_market_raw = 'eBay US'
    
    supplier_id = supplier_cache.get(source_market_raw)
    if not supplier_id:
        mp_id = mp_cache.get(f"{source_market_raw.split()[0]}_US", list(mp_cache.values())[0] if mp_cache else None)
        res = db.client.table('suppliers').insert({'marketplace_id': mp_id, 'supplier_type': 'Marketplace_Account', 'name': source_market_raw}).execute()
        supplier_id = res.data[0]['id']
        
    store_id = store_cache.get(target_market_raw)
    if not store_id:
        mp_id = mp_cache.get(f"{target_market_raw.split()[0]}_US", list(mp_cache.values())[0] if mp_cache else None)
        res = db.client.table('stores').insert({'marketplace_id': mp_id, 'store_name': target_market_raw}).execute()
        store_id = res.data[0]['id']
        
    return supplier_id, store_id

def import_ebay_natively(limit_pages=None):
    integrator = EbayApiIntegrator()
    ns = integrator.namespace
    
    print("🚀 Veriler eBay API'den çekilip paketleniyor (Native Bulk İşlem)...")
    
    supplier_id, store_id = get_or_create_supplier_store()
    
    page = 1
    api_items = []
    
    while True:
        print(f"Sayfa {page} taranıyor...")
        xml_data = integrator.xml_get_seller_list(page)
        if not xml_data:
            break
            
        root = ET.fromstring(xml_data)
        items = root.findall(f".//{ns}Item")
        if not items:
            break
            
        for item in items:
            item_id = item.find(f"{ns}ItemID")
            sku_node = item.find(f"{ns}SKU")
            title_node = item.find(f"{ns}Title")
            qty_node = item.find(f"{ns}Quantity")
            selling_status = item.find(f"{ns}SellingStatus")
            price_node = None
            if selling_status is not None:
                price_node = selling_status.find(f"{ns}CurrentPrice")
                
            cat_node = item.find(f"{ns}PrimaryCategory")
            cat_id_val = None
            cat_name_val = None
            if cat_node is not None:
                cid = cat_node.find(f"{ns}CategoryID")
                cname = cat_node.find(f"{ns}CategoryName")
                cat_id_val = cid.text if cid is not None else None
                cat_name_val = cname.text if cname is not None else None

            seller_profiles = item.find(f"{ns}SellerProfiles")
            ship_prof_id, ret_prof_id, pay_prof_id = None, None, None
            if seller_profiles is not None:
                ship_prof = seller_profiles.find(f"{ns}SellerShippingProfile")
                if ship_prof is not None:
                    s_id = ship_prof.find(f"{ns}ShippingProfileID")
                    ship_prof_id = s_id.text if s_id is not None else None
                ret_prof = seller_profiles.find(f"{ns}SellerReturnProfile")
                if ret_prof is not None:
                    r_id = ret_prof.find(f"{ns}ReturnProfileID")
                    ret_prof_id = r_id.text if r_id is not None else None
                pay_prof = seller_profiles.find(f"{ns}SellerPaymentProfile")
                if pay_prof is not None:
                    p_id = pay_prof.find(f"{ns}PaymentProfileID")
                    pay_prof_id = p_id.text if p_id is not None else None
                
            item_id_val = item_id.text if item_id is not None else None
            sku_val = sku_node.text if sku_node is not None else None
            title_val = title_node.text if title_node is not None else "İsimsiz Ürün"
            qty_val = int(qty_node.text) if qty_node is not None and qty_node.text else 0
            price_val = float(price_node.text) if price_node is not None and price_node.text else 0.0
            
            if not item_id_val:
                continue
                
            asin = sku_val
            if sku_val:
                if sku_val.startswith("A-"):
                    asin = sku_val[2:]
                elif sku_val.startswith("A") and len(sku_val) == 11:
                    asin = sku_val[1:]
            if not asin:
                asin = f"UNKNOWN-{item_id_val}"
                
            print(f"DEBUG: Cat: {cat_id_val}, Ship: {ship_prof_id}, Ret: {ret_prof_id}, Pay: {pay_prof_id}"); api_items.append({
                "source_id": asin, 
                "marketplace_sku": sku_val, 
                "item_id": item_id_val,
                "title": title_val[:200],
                "qty": qty_val,
                "price": price_val,
                "category_id": cat_id_val,
                "category_name": cat_name_val,
                "shipping_profile_id": ship_prof_id,
                "return_profile_id": ret_prof_id,
                "payment_profile_id": pay_prof_id
            })
            
        has_more = root.find(f".//{ns}HasMoreItems")
        if has_more is None or has_more.text.lower() != 'true':
            break
            
        if limit_pages and page >= limit_pages:
            break
            
        page += 1
        
    print(f"Toplam {len(api_items)} adet ürün eBay'den çekildi.")
    
    if not api_items:
        return {"success": 0, "errors": 0}

    # API'den çektiğimiz source_id (ASIN) listesi
    source_ids_in_api = list({item['source_id'] for item in api_items})
    
    prod_data = []
    chunk_sz = 200
    for i in range(0, len(source_ids_in_api), chunk_sz):
        chunk_asins = source_ids_in_api[i:i+chunk_sz]
        res = db.client.table('core_products').select('id, asin').in_('asin', chunk_asins).execute()
        prod_data.extend(res.data)
        
    prod_cache = {p['asin']: p['id'] for p in prod_data}
    
    existing_p_ids = [p['id'] for p in prod_data]
    list_data = []
    src_data = []
    if existing_p_ids:
        for i in range(0, len(existing_p_ids), chunk_sz):
            p_chunk = existing_p_ids[i:i+chunk_sz]
            l_res = db.client.table('listings').select('id, product_id, store_id').in_('product_id', p_chunk).execute()
            list_data.extend(l_res.data)
            
            s_res = db.client.table('sources').select('id, product_id, supplier_id').in_('product_id', p_chunk).execute()
            src_data.extend(s_res.data)

    listing_cache = {f"{l['product_id']}_{l['store_id']}": l['id'] for l in list_data}
    source_cache = {f"{s['product_id']}_{s['supplier_id']}": s['id'] for s in src_data}
    
    new_products_payload = []
    new_contents_payload = []
    new_sources_payload = []
    new_listings_payload = []
    
    for item in api_items:
        source_id = item['source_id']
        
        if source_id not in prod_cache and not any(p['asin'] == source_id for p in new_products_payload):
            new_products_payload.append({'asin': source_id})

    if new_products_payload:
        chunk_size = 500
        for i in range(0, len(new_products_payload), chunk_size):
            chunk = new_products_payload[i:i+chunk_size]
            res = db.client.table('core_products').upsert(chunk, on_conflict='asin').execute()
            for p in res.data:
                prod_cache[p['asin']] = p['id']

    for item in api_items:
        source_id = item['source_id']
        product_id = prod_cache.get(source_id)
        if product_id:
            if not any(c['product_id'] == product_id for c in new_contents_payload):
                new_contents_payload.append({'product_id': product_id, 'base_title': item['title']})
                
    if new_contents_payload:
        chunk_size = 500
        for i in range(0, len(new_contents_payload), chunk_size):
            db.client.table('product_base_content').upsert(new_contents_payload[i:i+chunk_size], on_conflict='product_id').execute()

    for item in api_items:
        source_id = item['source_id']
        product_id = prod_cache.get(source_id)
        if not product_id:
            continue
            
        src_key = f"{product_id}_{supplier_id}"
        if not any(s['product_id'] == product_id and s['supplier_id'] == supplier_id for s in new_sources_payload):
            s_payload = {
                'product_id': product_id, 'supplier_id': supplier_id, 
                'source_code': source_id, 'base_cost': 0.0 # Bize asıl maliyet Amazon'dan gelecek, şimdilik 0
            }
            if src_key in source_cache:
                s_payload['id'] = source_cache[src_key]
            new_sources_payload.append(s_payload)

        lst_key = f"{product_id}_{store_id}"
        if not any(l['product_id'] == product_id and l['store_id'] == store_id for l in new_listings_payload):
            l_payload = {
                'product_id': product_id, 'store_id': store_id, 
                'channel_item_id': item['item_id'], 
                'channel_sku': item['marketplace_sku'], 
                'listed_price': item['price'], 
                'quantity': item['qty'],
                'category_id': item['category_id'],
                'shipping_profile_id': item['shipping_profile_id'],
                'return_profile_id': item['return_profile_id'],
                'payment_profile_id': item['payment_profile_id'],
                'is_active': True,
                'needs_sync': False
            }
            if lst_key in listing_cache:
                l_payload['id'] = listing_cache[lst_key]
            new_listings_payload.append(l_payload)
            
    chunk_size = 1000
    
    categories_to_upsert = {}
    for item in api_items:
        if item['category_id'] and item['category_name']:
            categories_to_upsert[item['category_id']] = item['category_name']
            
    if categories_to_upsert:
        cat_payload = []
        for cid, cname in categories_to_upsert.items():
            cat_payload.append({
                "marketplace": "ebay",
                "category_id": cid,
                "category_name": cname
            })
        for i in range(0, len(cat_payload), 500):
            db.client.table('marketplace_categories').upsert(cat_payload[i:i+500], on_conflict='marketplace,category_id').execute()

    if new_sources_payload:
        sources_with_id = [item for item in new_sources_payload if 'id' in item]
        sources_without_id = [item for item in new_sources_payload if 'id' not in item]
        
        for sublist in [sources_with_id, sources_without_id]:
            if not sublist: continue
            for i in range(0, len(sublist), chunk_size):
                try:
                    db.client.table('sources').upsert(sublist[i:i+chunk_size]).execute()
                except Exception as e:
                    print(f"Source upsert hatası: {e}")

    if new_listings_payload:
        listings_with_id = [item for item in new_listings_payload if 'id' in item]
        listings_without_id = [item for item in new_listings_payload if 'id' not in item]
        
        for sublist in [listings_with_id, listings_without_id]:
            if not sublist: continue
            for i in range(0, len(sublist), chunk_size):
                try:
                    db.client.table('listings').upsert(sublist[i:i+chunk_size]).execute()
                except Exception as e:
                    print(f"Listings upsert hatası: {e}")

    print("\n✅ eBay Native Pull İşlemi Başarıyla Tamamlandı!")
    return {"success": len(api_items), "errors": 0}

if __name__ == "__main__":
    import_ebay_natively()
