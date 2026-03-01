import streamlit as st
import pandas as pd
from database import db
from pricing_engine import PricingEngine
from ebay_exporter import EbayExporter

# Sayfa Konfigürasyonu (Her zaman en üstte olmalı)
st.set_page_config(page_title="Informattach ERP", layout="wide")
st.title("🚀 Informattach ERP Sistemi")

def render_sidebar():
    """Navigasyon, Dışa Aktarma ve Veri İçe Aktarma"""
    st.sidebar.header("Yönetim Paneli")
    
    if st.sidebar.button("🔄 Tüm Fiyatları Yeniden Hesapla"):
        try:
            # engine = PricingEngine()
            # engine.process_all_listings(db)
            st.sidebar.info("Pricing Engine motoru sisteme entegre edilecek. (Hazırlanıyor)")
        except Exception as e:
            st.sidebar.error(f"Hesaplama hatası: {e}")
    
    st.sidebar.divider()
    
    # 📤 eBay Operasyonları (Dışa Aktarma)
    st.sidebar.subheader("📤 eBay Operasyonları")
    try:
        # Yeni veritabanı yapısına göre listings tablosunu çek
        raw_listings = db.client.table('listings').select('*, core_products(*), sources(*)').execute().data
        if raw_listings:
            # ebay_exporter'ın eski koda göre hata vermemesi için veriyi düzleştiriyoruz
            export_data = []
            for item in raw_listings:
                export_data.append({
                    'master_sku': item.get('listing_sku', ''),
                    'title': item.get('core_products', {}).get('master_title', ''),
                    'listings': [item],
                    'sources': [item.get('sources', {})] if item.get('sources') else []
                })
            
            csv_data = EbayExporter.generate_ebay_csv(export_data)
            st.sidebar.download_button(
                label="📥 eBay Revize CSV İndir",
                data=csv_data,
                file_name="eBay_Update_Price_Quantity.csv",
                mime="text/csv"
            )
        else:
            st.sidebar.warning("eBay'e gönderilecek ürün yok.")
    except Exception as e:
        st.sidebar.error("eBay export hatası: Veritabanı bağlantısını kontrol edin.")

    st.sidebar.divider()
    
    # 📥 Veri İçe Aktarma (4 Tablolu Normalize Motor)
    st.sidebar.subheader("📥 Veri İçe Aktarma")
    uploaded_file = st.sidebar.file_uploader("Easync / Ana CSV Dosyası Yükle", type=["csv", "xlsx"])
    
    if uploaded_file is not None:
        if st.sidebar.button("🚀 Normalize Veritabanına Bas"):
            with st.spinner("Veriler 4 katmanlı mimariye işleniyor..."):
                try:
                    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                    df = df.fillna('')
                    success_count = 0
                    
                    for _, row in df.iterrows():
                        source_id = str(row.get('Source Product Id', '')).strip() # ASIN
                        if not source_id:
                            continue
                        
                        listing_sku = str(row.get('Target Variant', '')).strip()
                        if not listing_sku:
                            listing_sku = f"A{source_id}" # TİRESİZ SKU
                            
                        title = str(row.get('Title', 'İsimsiz Ürün'))[:150]
                        
                        try:
                            # 1. CORE_PRODUCTS TABLOSU
                            existing_prod = db.client.table('core_products').select('id').eq('universal_id', source_id).execute()
                            if existing_prod.data:
                                product_id = existing_prod.data[0]['id']
                            else:
                                new_prod = db.client.table('core_products').insert({'universal_id': source_id, 'master_title': title}).execute()
                                product_id = new_prod.data[0]['id']
                            
                            # 2. SOURCES TABLOSU
                            cost_price = float(row.get('Source Price', 0)) if row.get('Source Price') else 0.0
                            qty = int(row.get('Quantity', 0)) if row.get('Quantity') else 0
                            source_market = str(row.get('Source Market', 'Amazon'))
                            
                            existing_source = db.client.table('sources').select('id').eq('product_id', product_id).eq('source_market', source_market).execute()
                            if not existing_source.data:
                                db.client.table('sources').insert({
                                    'product_id': product_id,
                                    'supplier_name': 'Amazon',
                                    'source_market': source_market,
                                    'source_sku': source_id,
                                    'cost_price': cost_price,
                                    'stock_quantity': qty
                                }).execute()
                            
                            # 3. LISTINGS TABLOSU
                            listed_price = float(row.get('Target Price', 0)) if row.get('Target Price') else 0.0
                            target_id = str(row.get('Target Product Id', '')).strip()
                            target_market = str(row.get('Target Market', 'eBay'))
                            
                            existing_listing = db.client.table('listings').select('id').eq('product_id', product_id).eq('channel_name', 'eBay').execute()
                            if existing_listing.data:
                                listing_db_id = existing_listing.data[0]['id']
                            else:
                                new_listing = db.client.table('listings').insert({
                                    'product_id': product_id,
                                    'channel_name': 'eBay',
                                    'target_market': target_market,
                                    'listing_sku': listing_sku,
                                    'channel_item_id': target_id,
                                    'listed_price': listed_price
                                }).execute()
                                listing_db_id = new_listing.data[0]['id']
                                
                            # 4. PERFORMANCE_STATS TABLOSU
                            qty_sold = int(row.get('Quantity Sold', 0)) if row.get('Quantity Sold') else 0
                            last_order = str(row.get('Last Order', ''))
                            
                            db.client.table('performance_stats').insert({
                                'listing_id': listing_db_id,
                                'quantity_sold': qty_sold,
                                'last_order_date': last_order
                            }).execute()

                            success_count += 1
                        except Exception as inner_e:
                            continue # Hatalı satırı atla, sistemi çökertme
                            
                    st.sidebar.success(f"İşlem Tamam! {success_count} ürün veritabanına işlendi.")
                except Exception as e:
                    st.sidebar.error(f"Kritik Dosya Hatası: {e}")

def render_product_table():
    """Yeni 4 tablolu mimariye uygun ürün portföyü"""
    st.subheader("📦 Ürün Portföyü")
    try:
        # Yeni yapıya göre core_products üzerinden diğer tabloları join yapıyoruz
        products_res = db.client.table('core_products').select('*, sources(*), listings(*)').execute()
        raw_data = products_res.data
        
        if not raw_data:
            st.info("Veritabanı şu an boş. Lütfen CSV/Excel yükleyin.")
            return

        flattened_data = []
        for p in raw_data:
            source = p.get('sources', [{}])[0] if p.get('sources') else {}
            listing = p.get('listings', [{}])[0] if p.get('listings') else {}
            
            flattened_data.append({
                "Evrensel ID (ASIN)": p.get('universal_id', 'N/A'),
                "Liste SKU": listing.get('listing_sku', '-'),
                "Ürün Adı": p.get('master_title', 'İsimsiz'),
                "Tedarik": f"{source.get('supplier_name', '-')} ({source.get('source_market', '')})",
                "Maliyet": source.get('cost_price', 0),
                "Satış Kanalı": f"{listing.get('channel_name', '-')} ({listing.get('target_market', '')})",
                "Satış Fiyatı": listing.get('listed_price', 0),
                "Stok": "Var" if source.get('stock_quantity', 0) > 0 else "Yok"
            })
        st.dataframe(pd.DataFrame(flattened_data), use_container_width=True)
    except Exception as e:
        st.error(f"Veri çekme hatası: Supabase tabloları henüz kurulmamış olabilir. Hata: {e}")

def render_pricing_rules():
    """Fiyatlandırma Kurallarını Düzenleme Alanı"""
    with st.expander("⚙️ Fiyatlandırma Kurallarını Yönet"):
        st.write("Mevcut kurallar Supabase 'pricing_rules' tablosundan çekiliyor.")
        try:
            rules_data = db.client.table("pricing_rules").select("*").execute().data
            if rules_data:
                st.table(rules_data)
            else:
                st.info("Sistemde tanımlı kural bulunamadı.")
        except:
            st.warning("pricing_rules tablosu henüz oluşturulmadı. Pricing Engine adımında eklenecek.")

# Ana Çalıştırma Döngüsü
def main():
    render_sidebar()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        render_product_table()
    
    with col2:
        st.subheader("Hızlı İşlemler")
        sku_to_find = st.text_input("SKU veya ASIN ile Ara")
        if sku_to_find:
            try:
                # Önce ASIN ile ara
                product = db.client.table('core_products').select('*, sources(*), listings(*)').eq('universal_id', sku_to_find).execute().data
                if not product:
                    # Bulamazsa Listing SKU ile ara
                    product = db.client.table('listings').select('*, core_products(*), sources(*)').eq('listing_sku', sku_to_find).execute().data
                
                if product:
                    st.json(product[0])
                else:
                    st.error("Ürün bulunamadı.")
            except Exception as e:
                st.error("Arama sırasında hata oluştu.")
        
        render_pricing_rules()

if __name__ == "__main__":
    main()