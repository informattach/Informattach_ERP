import streamlit as st
import pandas as pd
from database import db
from pricing_engine import PricingEngine

# Sayfa Konfigürasyonu
st.set_page_config(page_title="Informattach PIM", layout="wide")
st.title("🚀 Merkezi Ürün Yönetim Sistemi (PIM)")

def render_sidebar():
    """Navigasyon ve Genel İstatistikler"""
    st.sidebar.header("Yönetim Paneli")
    if st.sidebar.button("🔄 Tüm Fiyatları Yeniden Hesapla"):
        engine = PricingEngine()
        engine.process_all_listings(db)
        st.sidebar.success("Tüm fiyatlar güncellendi!")
    
    st.sidebar.divider()
    st.sidebar.info("Lokasyon: Hollanda | Hedef: İspanya")

def render_product_table():
    """Ürünleri, Kaynakları ve Satış Fiyatlarını Tek Tabloda Gösterir"""
    st.subheader("Ürün Portföyü")
    
    # Database'den ilişkisel veriyi çek
    raw_data = db.get_all_products()
    
    if not raw_data:
        st.warning("Veritabanında ürün bulunamadı.")
        return

    # Veriyi tabloya uygun hale getir (Flattening)
    flattened_data = []
    for p in raw_data:
        source = p['sources'][0] if p['sources'] else {}
        listing = p['listings'][0] if p['listings'] else {}
        
        flattened_data.append({
            "SKU": p['master_sku'],
            "Ürün Adı": p['title'],
            "Tedarik Platformu": source.get('platform', '-'),
            "Maliyet": source.get('cost_price', 0),
            "Pazar Yeri": listing.get('marketplace', '-'),
            "Satış Fiyatı": listing.get('listed_price', 0),
            "Stok Durumu": "✅" if source.get('stock_status') else "❌"
        })

    df = pd.DataFrame(flattened_data)
    
    # İnteraktif Tablo
    st.dataframe(df, use_container_width=True, hide_index=True)

def render_pricing_rules():
    """Fiyatlandırma Kurallarını Düzenleme Alanı"""
    with st.expander("⚙️ Fiyatlandırma Kurallarını Yönet"):
        # Not: Buraya ileride her pazar yeri için input alanları eklenecek
        st.write("Mevcut kurallar Supabase 'pricing_rules' tablosundan çekiliyor.")
        # Örnek statik tablo (Geliştirilecek)
        rules_data = db.supabase.table("pricing_rules").select("*").execute().data
        st.table(rules_data)

# Ana Çalıştırma Döngüsü
def main():
    render_sidebar()
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        render_product_table()
    
    with col2:
        st.subheader("Hızlı İşlemler")
        sku_to_find = st.text_input("SKU ile Ara")
        if sku_to_find:
            product = db.get_product_by_sku(sku_to_find)
            if product:
                st.json(product)
            else:
                st.error("Ürün bulunamadı.")
        
        render_pricing_rules()

if __name__ == "__main__":
    main()