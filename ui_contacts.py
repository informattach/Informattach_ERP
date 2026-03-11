import streamlit as st
import pandas as pd
from database import db
from contact_parser import detect_parser_and_parse, ContactDBManager

def get_all_contacts():
    # Fetch contacts from database
    response = db.client.table("contacts").select("*, contact_addresses(*)").order("created_at", desc=True).execute()
    return response.data if response.data else []

def render_contacts_page():
    st.subheader("👥 Kişiler ve Müşteri Veritabanı")
    st.markdown("Farklı platformlardan gelen müşteri, tedarikçi ve diğer kişi verilerini tek bir yerde toplayın.")
    
    tab_list, tab_upload = st.tabs(["📋 Tüm Kişiler", "📤 Yeni Dosya Yükle"])
    
    with tab_upload:
        st.markdown("### 📥 Toplu Kişi/Müşteri İçe Aktar (CSV/Excel)")
        st.info("Amazon Seller (Fulfillment Raporları), eBay Müşteri Çıktıları, Walmart Raporları veya Apple Kişileri (CSV) formatındaki dosyaları yükleyin. Sistem formatı otomatik algılar ve sütunları eşleştirir.")
        
        uploaded_file = st.file_uploader("Dosya Seçiniz (.csv, .xlsx)", type=["csv", "xlsx", "xls"])
        
        if uploaded_file is not None:
            if st.button("🚀 Verileri Ayrıştır ve Veritabanına Aktar", type="primary"):
                with st.spinner("Dosya analiz ediliyor..."):
                    try:
                        # Dosya tipi kontrolü
                        if uploaded_file.name.endswith('.csv'):
                            # Apple Contacts baştaki bazı satırları bozabiliyor, genel bir read
                            df = pd.read_csv(uploaded_file, low_memory=False)
                        else:
                            df = pd.read_excel(uploaded_file)
                            
                        # Parser'ı algıla ve parse et
                        format_name, parsed_records = detect_parser_and_parse(df)
                        
                        st.write(f"**Algılanan Format:** `{format_name}`")
                        st.write(f"**Bulunan Geçerli Kayıt Sayısı:** `{len(parsed_records)}`")
                        
                        if len(parsed_records) > 0:
                            with st.spinner("Veritabanına kaydediliyor (Mükerrer kontrolü devrede)..."):
                                result = ContactDBManager.save_records(parsed_records)
                                
                            st.success(f"İşlem Başarılı! \n- Yeni eklenen / Güncellenen Kişi: **{result['contacts_processed']}**\n- Eklenen Adres: **{result['addresses_processed']}**")
                            import time
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("Bu dosyada ayrıştırılabilir bir isim veya iletişim bilgisi bulunamadı. Lütfen dosya içeriğini kontrol edin.")
                            
                    except Exception as e:
                        st.error(f"İçe aktarım sırasında bir hata oluştu: {str(e)}")

    with tab_list:
        contacts = get_all_contacts()
        if not contacts:
            st.info("Veritabanında henüz kayıtlı kimse bulunmuyor.")
            return
            
        st.markdown(f"**Toplam Kayıt:** {len(contacts)}")
        
        table_data = []
        for c in contacts:
            addresses = c.get('contact_addresses', [])
            addr_str = "-"
            if addresses:
                first_addr = addresses[0]
                parts = [first_addr.get('address_line_1', ''), first_addr.get('city', ''), first_addr.get('country_code', '')]
                addr_str = ", ".join([p for p in parts if p])
                if len(addresses) > 1:
                    addr_str += f" (+{len(addresses)-1} adres)"
                    
            source_color = {
                "amazon": "🟠 Amazon",
                "ebay": "🔵 eBay",
                "walmart": "🟡 Walmart",
                "apple": "🍏 Apple",
                "manual": "⚙️ Manuel"
            }
                
            table_data.append({
                "ID": c.get("id"),
                "Ad": c.get("first_name", ""),
                "Soyad": c.get("last_name", ""),
                "Şirket": c.get("company_name", ""),
                "E-Posta": c.get("email", ""),
                "Telefon": c.get("phone", ""),
                "Tür": c.get("contact_type", "").capitalize(),
                "Kaynak": source_color.get(c.get("source_platform", ""), c.get("source_platform", "")),
                "Adres": addr_str
            })
            
        df_contacts = pd.DataFrame(table_data)
        
        st.dataframe(
            df_contacts,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": None # ID sütununu gizliyoruz
            }
        )
        
        # Basit veritabanı silme butonu
        if st.checkbox("Tehlikeli İşlemler / Veri Temizliği", value=False):
            if st.button("🚨 Tüm Kişi Veritabanını Temizle", type="secondary"):
                try:
                    db.client.table("contacts").delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
                    st.toast("Veritabanı sıfırlandı!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Silme hatası: {e}")
