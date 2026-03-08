import streamlit as st
import pandas as pd
from database import db
from datetime import datetime, timezone, timedelta
from ui_pricing_settings import render_pricing_settings

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="Informattach ERP - Çekirdek PIM", layout="wide")
st.title("📦 Çekirdek Ürün Yönetimi (Modül 1)")
st.markdown("Bu modül, ürünlerin pazaryerinden ve stoktan bağımsız evrensel kimliklerini yönetir.")


# --- ANA EKRAN: ÜRÜN PORTFÖYÜ ---
def render_main_table():
    st.subheader("Ürün Portföyü")
    
    try:
        raw_products = db.get_all_core_products()
        
        if not raw_products:
            st.info("Sistemde henüz ürün bulunmuyor.")
            return

        now = datetime.now(timezone.utc)
        table_data = []
        
        for p in raw_products:
            timestamps = [p.get('created_at')]
            
            content = p.get('product_base_content')
            if content is None:
                content = {}
            elif isinstance(content, list):
                content = content[0] if len(content) > 0 else {}
                
            title = content.get('base_title', 'İsimsiz')
            asin = p.get('asin', '')
            timestamps.append(content.get('updated_at'))
            
            sources = p.get('sources')
            base_cost = "-"
            amazon_url = "https://www.amazon.com/#p=-"
            calculated_price = "-"
            
            if sources and isinstance(sources, list) and len(sources) > 0:
                raw_cost = sources[0].get('base_cost', 0)
                if raw_cost:
                    base_cost = f"${raw_cost:.2f}"
                    try:
                        from pricing_engine import PricingEngine
                        calc_val = PricingEngine.calculate_final_price(
                            source_price=float(raw_cost),
                            marketplace="ebay",
                            override_marketplace_fee=15.0
                        )
                        calculated_price = f"${calc_val:.2f}"
                    except:
                        pass
                        
                if asin:
                    amazon_url = f"https://www.amazon.com/dp/{asin}?th=1#p={base_cost}"
                else:
                    amazon_url = f"https://www.amazon.com/#p={base_cost}"
                timestamps.append(sources[0].get('updated_at'))
            
            listings = p.get('listings')
            listed_price_display = "-"
            ebay_url = "https://www.ebay.com/itm/0#p=-"
            quantity = "-"
            channel_sku = "-"
            category_id = "-"
            channel_item_id = None
            ship_prof, ret_prof, pay_prof = "-", "-", "-"
            
            if listings and isinstance(listings, list) and len(listings) > 0:
                raw_price = listings[0].get('listed_price')
                
                if raw_price is not None:
                    listed_price_display = f"${float(raw_price):.2f}"
                else:
                    listed_price_display = calculated_price # Fallback to AI if live price missing
                    
                channel_item_id = listings[0].get('channel_item_id')
                if channel_item_id:
                    ebay_url = f"https://www.ebay.com/itm/{channel_item_id}#p={listed_price_display}"
                else:
                    ebay_url = f"https://www.ebay.com/itm/0#p={listed_price_display}"
                
                # Politika İsimlendirme Haritası
                POLICY_NAMES = {
                    "244347500010": "China Shipping",
                    "251361629010": "USDom2Hand5ShipFree",
                    "255820822010": "USDom0Hand3ShipFree",
                    "255820825010": "USDom2Hand5ShipFree Copy",
                    "255821358010": "USDom10Hand10ShipFree",
                    "255824624010": "USDomInt2HandNOFree",
                    "244347391010": "China Return",
                    "251407823010": "30BuyerINtNo",
                    "255822090010": "NOReturn",
                    "255829832010": "RETURN_PROFILE",
                    "244346933010": "Immediate Pay"
                }
                
                category_id = listings[0].get('category_id', '-') or "-"
                quantity = listings[0].get('quantity', '-')
                channel_sku = listings[0].get('channel_sku', '-')
                
                ship_id = str(listings[0].get('shipping_profile_id', '-'))
                ret_id = str(listings[0].get('return_profile_id', '-'))
                pay_id = str(listings[0].get('payment_profile_id', '-'))
                
                ship_prof = POLICY_NAMES.get(ship_id, ship_id)
                ret_prof = POLICY_NAMES.get(ret_id, ret_id)
                pay_prof = POLICY_NAMES.get(pay_id, pay_id)
                
                timestamps.append(listings[0].get('updated_at'))
                
            latest_time = None
            for ts in timestamps:
                if ts:
                    try:
                        parsed_ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        if not latest_time or parsed_ts > latest_time:
                            latest_time = parsed_ts
                    except:
                        pass
                        
            is_recent = False
            if latest_time and (now - latest_time) < timedelta(hours=2):
                is_recent = True
                
            table_data.append({
                "Seç": False,
                "ID": p.get('id'),
                "Ebay SKU": channel_sku,
                "Ürün Adı": title,
                "Kategori": category_id,
                "Maliyet ($)": amazon_url,
                "eBay Güncel Fiyatı": ebay_url,
                "Otonom Fiyat": calculated_price,
                "Stok": quantity,
                "Kargo Politikası": ship_prof,
                "İade Politikası": ret_prof,
                "_is_recent": is_recent
            })

        df = pd.DataFrame(table_data)
        df.index = df.index + 1
        df.index.name = '#'
        
        display_cols = ["Seç", "Ürün Adı", "Kategori", "Maliyet ($)", "eBay Güncel Fiyatı", "Otonom Fiyat", "Stok", "Kargo Politikası", "İade Politikası", "ID", "Ebay SKU"]
        df = df[display_cols].copy()
        
        # TABLO ÜSTÜ - SÜTUN BAŞLIĞI SİMÜLASYONU
        
        # Policy & Category ID'leri ve formatter func
        SHIPPING_IDS = ["", "244347500010", "251361629010", "255820822010", "255820825010", "255821358010", "255824624010"]
        RETURN_IDS = ["", "244347391010", "251407823010", "255822090010", "255829832010"]
        CATEGORY_IDS = ["", "30120"]
        
        def format_options(val):
            if val == "": return "Değiştirme"
            if val == "30120": return "Genel (30120)"
            return POLICY_NAMES.get(val, val)

        # Tablo Render
        edited_df = st.data_editor(
            df,
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                "Maliyet ($)": st.column_config.LinkColumn("Maliyet ($)", display_text=r"#p=(.*)"),
                "eBay Güncel Fiyatı": st.column_config.LinkColumn(
                    "eBay Güncel Fiyatı", 
                    display_text=r"#p=(.*)"
                ),
                "Kategori": st.column_config.TextColumn("Kategori"),
                "Stok": st.column_config.NumberColumn("Stok", min_value=0),
                "Kargo Politikası": st.column_config.SelectboxColumn("Kargo Politikası", options=[POLICY_NAMES.get(i, i) for i in SHIPPING_IDS if i]),
                "İade Politikası": st.column_config.SelectboxColumn("İade Politikası", options=[POLICY_NAMES.get(i, i) for i in RETURN_IDS if i]),
                "ID": None,
                "Ebay SKU": None
            },
            disabled=["Ürün Adı", "Maliyet ($)", "eBay Güncel Fiyatı", "Otonom Fiyat", "ID", "Ebay SKU"],
            hide_index=True,
            use_container_width=True,
            key="portfolio_table"
        )
        
        # INLINE EDIT KAYDETME (Hücre içi değişiklikleri yakala ve kaydet)
        if "portfolio_table" in st.session_state:
            changes = st.session_state.portfolio_table.get("edited_rows", {})
            if changes:
                REVERSE_POLICY_NAMES = {v: k for k, v in POLICY_NAMES.items()}
                for row_idx_str, edits in changes.items():
                    # Sadece Seç checkbox'ı değiştiyse atla
                    if "Seç" in edits and len(edits) == 1:
                        continue
                        
                    try:
                        # DataFrame indexi 1'den başladığı için, Streamlit'in 0-baslı positional indexini eşleştiriyoruz
                        real_idx = df.index[int(row_idx_str)]
                        prod_id = df.loc[real_idx, "ID"]
                        payload = {"needs_sync": True}
                        
                        if "Stok" in edits: payload["quantity"] = int(edits["Stok"])
                        if "Kategori" in edits: payload["category_id"] = str(edits["Kategori"])
                        
                        if "Kargo Politikası" in edits: 
                            payload["shipping_profile_id"] = REVERSE_POLICY_NAMES.get(edits["Kargo Politikası"], edits["Kargo Politikası"])
                        if "İade Politikası" in edits: 
                            payload["return_profile_id"] = REVERSE_POLICY_NAMES.get(edits["İade Politikası"], edits["İade Politikası"])
                            
                        if len(payload) > 1: # Sadece needs_sync haricinde bir şey varsa kaydet
                            db.client.table('listings').update(payload).eq('product_id', prod_id).execute()
                            # Mesaj gösterimi (Tekrar etmesini engellemek için sadece değişim anında çalışır)
                            st.toast(f"✅ {df.loc[real_idx, 'Ebay SKU']} güncellendi!")
                            
                    except Exception as e:
                        st.toast(f"❌ Güncelleme hatası: {e}")
        
        # Seçili Ürünleri Toplu Düzenleme Paneli
        with st.expander("🛠️ Seçili Ürünleri Toplu Düzenle", expanded=False):
            st.markdown("<span style='font-size:14px; color:gray;'>Aşağıdaki alanları doldurarak tablodan 'Seç' tikini işaretlediğiniz tüm ürünleri tek seferde güncelleyebilirsiniz. Boş bıraktığınız alanlar değişmez.</span>", unsafe_allow_html=True)
            
            e_col1, e_col2, e_col3, e_col4, e_col5 = st.columns(5)
            
            with e_col1:
                bulk_cat = st.selectbox("Yeni Kategori", options=CATEGORY_IDS, format_func=format_options)
            with e_col2:
                bulk_qty = st.text_input("Yeni Stok", placeholder="Stok Sayı (Örn: 5)")
            with e_col3:
                bulk_ship = st.selectbox("Yeni Kargo Pol.", options=SHIPPING_IDS, format_func=format_options)
            with e_col4:
                bulk_ret = st.selectbox("Yeni İade Pol.", options=RETURN_IDS, format_func=format_options)
            with e_col5:
                # Apply button alignment
                st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
                btn_apply = st.button("🚀 Seçililere Uygula", use_container_width=True, type="primary")

        if btn_apply:
            selected_rows = edited_df[edited_df["Seç"] == True]
            if selected_rows.empty:
                st.warning("Değiştirmek istediğiniz ürün(ler)i tablodaki 'Seç' kutucuğundan onaylayın!")
            elif not any([bulk_qty, bulk_ship, bulk_ret, bulk_cat]):
                st.warning("Uygulamak için panelde en az bir yeni değer belirlemelisiniz.")
            else:
                try:
                    product_ids = selected_rows["ID"].tolist()
                    payload = {"needs_sync": True}
                    
                    if bulk_ship: payload["shipping_profile_id"] = bulk_ship
                    if bulk_ret: payload["return_profile_id"] = bulk_ret
                    if bulk_qty and bulk_qty.isdigit(): payload["quantity"] = int(bulk_qty)
                    if bulk_cat: payload["category_id"] = bulk_cat
                            
                    db.client.table('listings').update(payload).in_('product_id', product_ids).execute()
                    
                    st.success(f"{len(product_ids)} ürün başarıyla güncellendi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Toplu Güncelleme Hatası: {e}")

        # TABLO ALTI - SİSTEM SENKRONİZASYONU
        st.markdown("---")
        cols_bottom = st.columns(3)
        
        with cols_bottom[0]:
            st.subheader("🚀 Değişiklikleri eBay'e Gönder (Push)")
            st.caption("Arayüzde veya arka planda değişen (needs_sync=True) ürünleri eBay'e canlı olarak gönderir.")
            if st.button("🚀 Push İşlemini Başlat", use_container_width=True, type="primary"):
                with st.spinner("Değişiklikler eBay'e iletiliyor..."):
                    try:
                        from sync_engine import PushEngine
                        engine = PushEngine()
                        result = engine.push_updates()
                        if result["status"] == "success":
                            st.success(result["message"])
                        elif result["status"] == "info":
                            st.info(result["message"])
                        else:
                            st.warning(result["message"])
                            for log in result["logs"]:
                                st.error(log)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Push Hatası: {e}")

        with cols_bottom[1]:
            st.subheader("🔄 eBay NATIVE API (Toplu Çekim)")
            st.caption("Easync'e gerek kalmadan aktif tüm eBay ilanlarınızı anında ERP'ye çeker.")
            if st.button("🚀 eBay'den Canlı Çek", use_container_width=True):
                with st.spinner("eBay API'ye bağlanılıyor ve veriler doğrudan Supabase'e işleniyor... (Bu işlem biraz sürebilir)"):
                    try:
                        from import_ebay_natively import import_ebay_natively
                        result = import_ebay_natively()
                        st.success(f"İşlem Tamam! Başarılı Çekilen Ürün: {result['success']} | Hata: {result['errors']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"eBay API Çekim Hatası: {e}")

        with cols_bottom[2]:
            st.subheader("📥 Dosyayla Güncelle (Easync CSV)")
            st.caption("Easync verilerinizi ERP katmanına aktarmak için CSV/Excel dosyanızı yükleyin (Maksimum 50MB)")
            uploaded_file = st.file_uploader("CSV veya Excel Yükle (Maks 50MB)", type=["csv", "xlsx"])
            if uploaded_file is not None:
                # 50MB size limit check (Memory Exhaustion DoS Protection)
                if uploaded_file.size > 50 * 1024 * 1024:
                    st.error("CRITICAL: Yüklenen dosya boyutu çok büyük (50MB Sınırı aşıldı). Lütfen dosyayı bölerek yükleyiniz.")
                elif st.button("🚀 ERP'ye Dağıt", use_container_width=True):
                    with st.spinner("Veriler okunuyor ve 5 katmanlı mimariye dağıtılıyor..."):
                        try:
                            if uploaded_file.name.endswith('.csv'):
                                df_imp = pd.read_csv(uploaded_file)
                            else:
                                df_imp = pd.read_excel(uploaded_file)
                                
                            result = db.import_easync_data(df_imp)
                            st.success(f"İşlem Tamam! Başarılı: {result['success']} | Hatalı Satır: {result['errors']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Kritik Dosya Hatası: {e}")

    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")

# --- ÜRÜN ÇEKİM (RESEARCH) MODÜLÜ ---
def render_research_page():
    st.title("🛒 Ürün Araştırma ve Ekleme")
    
    tab1, tab2, tab3 = st.tabs(["➕ Yeni Evrensel Ürün Ekle", "🤖 Otomatik Ürün Tarama", "📥 Amazon Export Yükle"])
    
    with tab1:
        st.markdown("### Sisteme Tekil Ürün Gir")
        with st.form("new_product_form", clear_on_submit=True):
            isku = st.text_input("ISKU (Informattach SKU) *", help="Şirket içi benzersiz ürün kodu. Örn: INF-001")
            base_title = st.text_input("Standart Ürün Adı *", help="Pazaryeri kısıtlamalarından bağımsız ana isim.")
            
            st.divider()
            asin = st.text_input("ASIN", help="Varsa Amazon ASIN kodu")
            upc = st.text_input("UPC / Evrensel Barkod", help="Varsa evrensel barkod")
            
            requires_exp = st.checkbox("Bu ürün SKT takibi gerektirir", value=False)
            
            submitted = st.form_submit_button("Ürünü Veritabanına Kaydet")
            
            if submitted:
                if not isku or not base_title:
                    st.error("ISKU ve Standart Ürün Adı zorunludur!")
                else:
                    try:
                        clean_asin = asin.strip() if asin.strip() else None
                        clean_upc = upc.strip() if upc.strip() else None
                        
                        db.create_core_product(
                            base_title=base_title.strip(),
                            isku=isku.strip(),
                            asin=clean_asin,
                            upc=clean_upc,
                            requires_expiration=requires_exp
                        )
                        st.success(f"'{isku}' başarıyla eklendi!")
                    except Exception as e:
                        st.error(f"Ekleme Hatası: {e}")
                        
    with tab2:
        st.markdown("### 🤖 Amazon Toplu Bağlantı Tarayıcı")
        col1, col2 = st.columns([2, 1])
        with col1:
            target_url = st.text_input("Amazon Kategori / Liste Linki")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Tarayıcıyı Başlat", use_container_width=True):
                import subprocess, os
                st.info("Robot çalışıyor, lütfen bekleyin...")
                script_path = os.path.join(os.path.dirname(__file__), "list_importer.py")
                cmd = ["python3", script_path]
                if target_url.strip(): cmd.append(target_url.strip())
                result = subprocess.run(cmd, capture_output=True, text=True)
                # Sadece teknik hataları görmek isterseniz diye altta print ediyoruz ama UI'ı bozmuyoruz.
                if result.returncode != 0:
                    st.error(f"Tarayıcı Hatası:\n{result.stderr}")
                st.rerun() # Refresh to show new drafts
                
    with tab3:
        st.markdown("### 📥 / 📤 Amazon Export Listesi Yükle ve İndir")
        
        st.info("Önce sistemdeki mevcut ürünlerin Amazon ASIN listesini indirip bottan geçirin, ardından sonuç dosyasını buraya yükleyin.")
        col_dl, col_ul = st.columns([1, 1])
        
        with col_dl:
            st.markdown("**1. Amazon ASIN Listesi Oluştur**")
            st.caption("Tüm ASIN'lerinizi doğrudan Amazon Business (Easync) şablon formatında Excel olarak hazırlayın.")
            
            if st.button("📦 Tüm ASIN'leri Şablona Hazırla", use_container_width=True):
                with st.spinner("2900'den fazla ürününüz için Excel Şablonu oluşturuluyor... (Maks: 10sn)"):
                    try:
                        import io, os, openpyxl
                        
                        asins = []
                        offset = 0
                        chunk = 1000
                        while True:
                            res = db.client.table("core_products").select("asin").not_.is_("asin", "null").range(offset, offset + chunk - 1).execute()
                            data = res.data
                            asins.extend([d['asin'] for d in data if d.get('asin')])
                            if len(data) < chunk:
                                break
                            offset += chunk
                            
                        if asins:
                            template_path = os.path.join(os.path.dirname(__file__), "exportedList.xlsx")
                            wb = openpyxl.load_workbook(template_path)
                            ws = wb.active
                            
                            if ws.max_row >= 14:
                                ws.delete_rows(14, ws.max_row - 13)
                                
                            formula_val = '=_xlfn.LET(_xlpm.A,IF(LEN(TRIM(INDIRECT("B"&ROW())))=0,Data!$B$2,IF(LEN(TRIM(INDIRECT("B"&ROW())))<>10,Data!$B$3,Data!$B$4)),_xlpm.Q,IF(LEN(TRIM(INDIRECT("C"&ROW())))=0,Data!$B$2,IF(AND(ISNUMBER(INDIRECT("C"&ROW())),IFERROR((INT(INDIRECT("C"&ROW()))),FALSE)=INDIRECT("C"&ROW()),INDIRECT("C"&ROW())>0),Data!$B$4,Data!$B$3)),_xlpm.C,IF(LEN(TRIM(INDIRECT("D"&ROW())))=0,Data!$B$2,IF(LEN(TRIM(INDIRECT("D"&ROW())))<251,Data!$B$4,Data!$B$3)),IF(AND(_xlpm.A=Data!$B$2,_xlpm.Q=Data!$B$2,_xlpm.C=Data!$B$2),Data!$B$2,IF(OR(_xlpm.A=Data!$B$3,_xlpm.Q=Data!$B$3,_xlpm.C=Data!$B$3),Data!$B$3,IF(_xlpm.A=Data!$B$2,Data!$B$3,Data!$B$4))))'
                            for i, asin in enumerate(asins, start=14):
                                ws.cell(row=i, column=1, value=i-13)  # Line Number
                                ws.cell(row=i, column=2, value=asin)  # ASIN
                                ws.cell(row=i, column=6, value=formula_val) # Validation Check Formula
                                
                            excel_data = io.BytesIO()
                            wb.save(excel_data)
                            
                            st.session_state['downloadable_amazon_excel'] = excel_data.getvalue()
                            st.rerun()
                        else:
                            st.warning("Veritabanında bulunamadı.")
                    except Exception as e:
                        st.error(f"Excel Oluşturma Hatası: {e}")

            if 'downloadable_amazon_excel' in st.session_state:
                st.download_button(
                    label="⬇️ İndir: amazon_yukleme_listesi.xlsx",
                    data=st.session_state['downloadable_amazon_excel'],
                    file_name='exportedList_AUTO.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True,
                    type="primary"
                )

        with col_ul:
            st.markdown("**2. Fiyatlandırılmış Listeyi Yükle**")
            uploaded_amazon = st.file_uploader("Bot Çıktısı (Excel)", type=["xlsx", "xls"])
            
            if uploaded_amazon is not None:
                if st.button("🚀 Draft Tablosuna Aktar", use_container_width=True):
                    with st.spinner("Dosya işleniyor, Amazon listesi aktarılıyor..."):
                        import pandas as pd
                        try:
                            df_az = pd.read_excel(uploaded_amazon, header=None, skiprows=12)
                            result = db.import_amazon_drafts(df_az)
                            st.success(f"İşlem Tamamlandı! Başarıyla Aktarılan: {result['success']} | Hatalı: {result['errors']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Aktarım Sırasında Hata: {e}")

    # Tabs dışındaki draft listesini ortak alanda gösteriyoruz, sayfa yenilendiğinde herkes görür
    st.markdown("---")
    drafts = db.get_unapproved_drafts()
    if drafts:
        import pandas as pd
        st.markdown(f"**🔍 Tarama Sonuçları ({len(drafts)} Ürün Bulundu)**")
        
        table_data = []
        for d in drafts:
            asin = d.get('product_id')
            raw_price = str(d.get('price', '-')).replace('$', '').strip()
            amazon_url = f"https://www.amazon.com/dp/{asin}?th=1#p={raw_price}" if asin else f"https://www.amazon.com/#p={raw_price}"
            
            table_data.append({
                "Seç": False,
                "ID": d.get('id'),
                "ASIN": asin,
                "Ürün Adı": d.get('title', ''),
                "Maliyet ($)": amazon_url,
                "Satıcı": d.get('merchant_name', ''),
                "Teslimat": d.get('delivery_date', ''),
                "Stok": d.get('stock_quantity', '3')
            })
                
        df_drafts = pd.DataFrame(table_data)
        
        edited_drafts = st.data_editor(
            df_drafts,
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                "Maliyet ($)": st.column_config.LinkColumn("Maliyet ($)", display_text=r"#p=(.*)"),
                "ID": None
            },
            disabled=["ASIN", "Ürün Adı", "Maliyet ($)", "Satıcı", "Teslimat", "ID"],
            hide_index=True,
            use_container_width=True,
            key="drafts_table"
        )
        
        if st.button("🚀 Seçili Ürünleri eBay'de Listele ve Kataloğa Aktar", type="primary", use_container_width=True):
            selected_drafts = edited_drafts[edited_drafts["Seç"] == True]
            if selected_drafts.empty:
                st.warning("Lütfen listelenecek en az bir ürün seçin.")
            else:
                draft_ids = selected_drafts["ID"].tolist()
                progress_text = f"{len(draft_ids)} ürün eBay için hazırlanıyor (Yapay Zeka & Fiyatlandırma Devrede)..."
                my_bar = st.progress(0, text=progress_text)
                
                # Import ListingEngine here to avoid circular dependencies if any
                from listing_engine import ListingEngine
                engine = ListingEngine()
                
                with st.spinner("İşlem sürüyor, ürün başı ortalama 10-20 saniye sürebilir..."):
                    results = engine.process_drafts_to_ebay(draft_ids)
                    
                my_bar.progress(100, text="İşlem Tamamlandı!")
                
                if results["success"] > 0:
                    st.success(f"Tebrikler! {results['success']} ürün eBay'de başarıyla yayına alındı ve ERP'ye kaydedildi.")
                if results["skipped"] > 0:
                    st.info(f"{results['skipped']} ürün zaten eBay'de mevcut olduğu için atlandı (Kota Korundu).")
                if results["failed"] > 0:
                    st.error(f"{results['failed']} ürün işlenirken hata oluştu.")
                    
                with st.expander("Sistem Logları (Detaylı Sonuçlar)"):
                    for detail in results["details"]:
                        if "Başarılı" in detail:
                            st.success(detail)
                        elif "Atlandı" in detail:
                            st.info(detail)
                        else:
                            st.error(detail)
                            
                st.rerun()
    else:
        st.caption("Şu an incelenmeyi bekleyen tarama (taslak) kaydı yok.")
def check_password():
    """Basit şifre koruması (st.secrets["APP_PASSWORD"] üzerine kurulu)"""
    import os
    from dotenv import load_dotenv
    # Streamlit sayfa her yenilendiğinde güncel şifreyi çeksin diye .env'yi okutuyoruz
    load_dotenv()
    correct_password = os.environ.get("APP_PASSWORD", "admin123") # Varsayılan: admin123
    
    def password_entered():
        if st.session_state["password_input"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Sisteme giriş şifresi:", type="password", on_change=password_entered, key="password_input")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Sisteme giriş şifresi:", type="password", on_change=password_entered, key="password_input")
        st.error("❌ Hatalı şifre, tekrar deneyin.")
        return False
    else:
        return True

def main():
    if not check_password():
        return
        
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
    
    page = st.radio("Sistem Menüsü", ["Ürün Portföyü", "Ürün Araştırma ve Ekleme", "Fiyatlandırma Ayarları"], horizontal=True, label_visibility="collapsed")
    st.divider()
    
    if page == "Ürün Portföyü":
        render_main_table()
    elif page == "Ürün Araştırma ve Ekleme":
        render_research_page()
    elif page == "Fiyatlandırma Ayarları":
        render_pricing_settings()

if __name__ == "__main__":
    main()