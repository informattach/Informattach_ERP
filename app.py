import streamlit as st
import pandas as pd
from database import db

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="Informattach ERP - Çekirdek PIM", layout="wide")
st.title("📦 Çekirdek Ürün Yönetimi (Modül 1)")
st.markdown("Bu modül, ürünlerin pazaryerinden ve stoktan bağımsız evrensel kimliklerini yönetir.")

# --- SOL MENÜ: YENİ ÜRÜN EKLEME ---
def render_sidebar():
    st.sidebar.header("➕ Yeni Evrensel Ürün Ekle")
    
    with st.sidebar.form("new_product_form", clear_on_submit=True):
        isku = st.text_input("ISKU (Informattach SKU) *", help="Şirket içi benzersiz ürün kodu. Örn: INF-001")
        base_title = st.text_input("Standart Ürün Adı *", help="Pazaryeri kısıtlamalarından bağımsız ana isim.")
        
        st.divider()
        asin = st.text_input("ASIN (Amazon)", help="Varsa Amazon ASIN kodu")
        upc = st.text_input("UPC / Evrensel Barkod", help="Varsa evrensel barkod")
        
        requires_exp = st.checkbox("Bu ürün SKT takibi gerektirir", value=False)
        
        submitted = st.form_submit_button("Ürünü Veritabanına Kaydet")
        
        if submitted:
            if not isku or not base_title:
                st.error("ISKU ve Standart Ürün Adı zorunludur!")
            else:
                try:
                    # Boş stringleri None'a çevir (Unique constraint hatası almamak için)
                    clean_asin = asin.strip() if asin.strip() else None
                    clean_upc = upc.strip() if upc.strip() else None
                    
                    db.create_core_product(
                        isku=isku.strip(),
                        base_title=base_title.strip(),
                        asin=clean_asin,
                        upc=clean_upc,
                        requires_expiration=requires_exp
                    )
                    st.success(f"'{isku}' başarıyla eklendi!")
                    st.rerun() # Tabloyu anında güncellemek için sayfayı yenile
                except Exception as e:
                    # Muhtemelen aynı ISKU veya ASIN eklenmeye çalışıldı
                    st.error(f"Ekleme Hatası: {e}")

# --- ANA EKRAN: ÜRÜN PORTFÖYÜ ---
def render_main_table():
    st.subheader("Ürün Portföyü")
    
    try:
        raw_products = db.get_all_core_products()
        
        if not raw_products:
            st.info("Sistemde henüz ürün bulunmuyor. Sol menüden ilk ürününüzü ekleyin.")
            return

        # Veritabanından gelen veriyi düzleştirip (flatten) tabloya uygun hale getir
        table_data = []
        for p in raw_products:
            # 1'e 1 ilişkide Supabase dict döndürebilir, yoksa boş dict al
            content = p.get('product_base_content', {})
            # Eğer liste olarak dönerse ilk elemanı al
            if isinstance(content, list):
                content = content[0] if len(content) > 0 else {}
                
            title = content.get('base_title', 'İsimsiz')
            
            table_data.append({
                "ISKU": p.get('isku', '-'),
                "Ürün Adı": title,
                "ASIN": p.get('asin', '-'),
                "UPC": p.get('upc', '-'),
                "SKT Takibi": "Evet" if p.get('requires_expiration') else "Hayır",
                "Sistem ID": p.get('id')
            })

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"Veri çekme hatası (Tablolar kurulmamış olabilir): {e}")

# --- UYGULAMA DÖNGÜSÜ ---
if __name__ == "__main__":
    render_sidebar()
    render_main_table()