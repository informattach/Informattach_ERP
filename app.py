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
    st.subheader("📦 Ana Çekirdek (Core DB) Ürün Portföyü")
    
    try:
        categories_map = db.get_all_categories()
        suppliers_map = db.get_all_suppliers()
        stores_map = db.get_all_stores()
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            selected_suppliers = st.multiselect("Kaynak (Source) Filtresi", options=list(suppliers_map.values()), default=list(suppliers_map.values()))
        with col_f2:
            selected_stores = st.multiselect("Hedef (Store) Filtresi", options=list(stores_map.values()), default=list(stores_map.values()))
            
        raw_products = db.get_all_core_products()
        
        if not raw_products:
            st.info("Sistemde henüz ürün bulunmuyor.")
            return

        now = datetime.now(timezone.utc)
        table_data = []
        
        # State management for Select All logic
        if "select_all_core" not in st.session_state:
            st.session_state.select_all_core = False
        if "core_table_key" not in st.session_state:
            st.session_state.core_table_key = 0

        # 1. Hızlı Ön Filtreleme
        filtered_products = []
        for p in raw_products:
            sources = p.get('sources')
            listings = p.get('listings')
            supplier_id = sources[0].get('supplier_id') if sources and len(sources) > 0 else None
            store_id = listings[0].get('store_id') if listings and len(listings) > 0 else None
            
            sup_name = suppliers_map.get(supplier_id, "Bilinmeyen Kaynak")
            channel_sku = listings[0].get('channel_sku', '-') if listings and len(listings) > 0 else "-"
            
            if channel_sku and channel_sku.upper().startswith("CJ"):
                sup_name = "CJ Dropshipping"
                if "CJ Dropshipping" not in list(suppliers_map.values()):
                    suppliers_map["temp_cj"] = "CJ Dropshipping"
                    
            store_name = stores_map.get(store_id, "Bilinmeyen Hedef")
            
            if sup_name in selected_suppliers and store_name in selected_stores:
                filtered_products.append(p)

        # 2. Sayfalama (Pagination - 50 ürün/sayfa optimizasyonu ile Streamlit Kopma hatasını çözer)
        ITEMS_PER_PAGE = 50
        total_items = len(filtered_products)
        total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        
        if "core_page" not in st.session_state:
            st.session_state.core_page = 1
        if st.session_state.core_page > total_pages:
            st.session_state.core_page = total_pages
            
        start_idx = (st.session_state.core_page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_products = filtered_products[start_idx:end_idx]

        st.markdown(f"**📦 Ana Ürün Kataloğu ({total_items} Toplam | Sayfa: {st.session_state.core_page}/{total_pages})**")
        
        c_csel1, c_csel2, c_prev, c_page, c_next = st.columns([2, 2, 2, 2, 2])
        with c_csel1:
            if st.button("✅ Sayfadaki Tümünü Seç", use_container_width=True):
                st.session_state.select_all_core = True
                st.session_state.core_table_key += 1
                st.rerun()
        with c_csel2:
            if st.button("❌ Seçimi Kaldır", key="clear_core_selections", use_container_width=True):
                st.session_state.select_all_core = False
                st.session_state.core_table_key += 1
                st.rerun()
        with c_prev:
            if st.button("◀ Önceki Sayfa", disabled=st.session_state.core_page <= 1, use_container_width=True):
                st.session_state.core_page -= 1
                st.rerun()
        with c_page:
            st.markdown(f"<div style='text-align: center; padding-top: 8px;'><b>Sayfa {st.session_state.core_page} / {total_pages}</b></div>", unsafe_allow_html=True)
        with c_next:
            if st.button("Sonraki Sayfa ▶", disabled=st.session_state.core_page >= total_pages, use_container_width=True):
                st.session_state.core_page += 1
                st.rerun()

        # 3. Yalnızca sayfaya özgü ürünleri işle (Ağır hesaplamalar ve DataFrame'in şişmesini engeller)
        for p in page_products:
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
                
            # Get Image
            product_media = p.get('product_media', [])
            media_url = "https://via.placeholder.com/150?text=G%C3%B6rsel+Yok"
            if product_media and isinstance(product_media, list) and len(product_media) > 0:
                media_url = product_media[0].get('media_url') or media_url
                
            formatted_category = categories_map.get(category_id, category_id)
            
            table_data.append({
                "Seç": st.session_state.select_all_core,
                "Foto": media_url,
                "Ürün Adı": title,
                "Maliyet ($)": amazon_url,
                "eBay Güncel Fiyatı": ebay_url,
                "Otonom Fiyat": calculated_price,
                "Stok": quantity,
                "Kargo Politikası": ship_prof,
                "İade Politikası": ret_prof,
                "Kategori": formatted_category,
                "IID": channel_sku,
                "ID": p.get('id'),
                "Ebay SKU": channel_sku,
                "itemID": channel_item_id or "-",
                "_is_recent": is_recent
            })

        if not table_data:
            st.warning("Seçilen filtrelere uygun ürün bulunamadı.")
            return

        df = pd.DataFrame(table_data)
        df.index = df.index + 1
        df.index.name = '#'
        
        display_cols = ["Seç", "Foto", "Ürün Adı", "Maliyet ($)", "eBay Güncel Fiyatı", "Otonom Fiyat", "Stok", "Kargo Politikası", "İade Politikası", "Kategori", "IID", "ID", "Ebay SKU", "itemID"]
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
                "Seç": st.column_config.CheckboxColumn("Seç"),
                "Foto": st.column_config.ImageColumn("Foto", help="Ürünün Cloud'daki Görseli"),
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
                "Ebay SKU": None,
                "itemID": None
            },
            disabled=["Foto", "Ürün Adı", "Maliyet ($)", "eBay Güncel Fiyatı", "Otonom Fiyat", "Kategori", "IID", "ID", "Ebay SKU", "itemID"],
            hide_index=True,
            use_container_width=True,
            key=f"portfolio_table_{st.session_state.core_table_key}"
        )
        
        # INLINE EDIT KAYDETME (Hücre içi değişiklikleri yakala ve kaydet)
        current_table_state_key = f"portfolio_table_{st.session_state.core_table_key}"
        if current_table_state_key in st.session_state:
            changes = st.session_state[current_table_state_key].get("edited_rows", {})
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
        
        # Seçili Ürünleri Toplu Düzenleme / Silme Paneli
        c_action1, c_action2 = st.columns([3, 1])
        with c_action1:
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
                        st.error(f"Toplu güncelleme sırasında hata: {e}")
                        
        with c_action2:
            if st.button("🚨 Seçili Core (Ana) Ürünleri Veritabanından Sil", type="secondary", use_container_width=True):
                selected_rows = edited_df[edited_df["Seç"] == True]
                if selected_rows.empty:
                    st.warning("Lütfen silinecek ürün(ler)i tablodan seçin!")
                else:
                    with st.spinner("Katmanlı silme işlemi (Listings, Sources, Media) sürüyor..."):
                        try:
                            product_ids = selected_rows["ID"].tolist()
                            chunck_size = 500
                            for i in range(0, len(product_ids), chunck_size):
                                chunk = product_ids[i:i + chunck_size]
                                db.client.table('core_products').delete().in_('id', chunk).execute()
                                
                            st.toast(f"✅ {len(product_ids)} adet ürün tamamen silindi!", icon="🚨")
                            import time
                            time.sleep(1)
                            st.session_state.select_all_core = False
                            st.session_state.core_table_key += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Silme sırasında hata: {e}")

        # --- EBAY API TABLO ALTI İŞLEMLERİ ---
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚡ eBay API ve Liste İşlemleri", expanded=False):
            api_c1, api_c2, api_c3, api_c4 = st.columns(4)
            with api_c1:
                st.info("🛒 **Yeni Ürünleri Satışa Aç**\nTablodan seçtiğiniz ürünleri eBay'de listeler.")
                if st.button("🚀 Seçili Ürünleri Listele", use_container_width=True, type="primary"):
                    selected_rows = edited_df[edited_df["Seç"] == True]
                    if selected_rows.empty:
                        st.warning("Lütfen yayına alınacak en az bir ürün seçin.")
                    else:
                        prod_ids = selected_rows["ID"].tolist()
                        with st.spinner("Seçili ürünler eBay'de listeleniyor..."):
                            try:
                                from listing_engine import ListingEngine
                                eng = ListingEngine()
                                res = eng.publish_core_products_to_ebay(prod_ids)
                                st.success(f"Tamam! Başarılı: {res['success']} | Atlanan/Hata: {res['skipped'] + res['failed']}")
                            except Exception as e:
                                st.error(f"Listeleme hatası: {e}")

            with api_c2:
                st.info("🎯 **Değişiklikleri Gönder**\nAcil senkronizasyon bekleyenleri anında basar.")
                if st.button("🔄 Push İşlemini Başlat", use_container_width=True):
                    with st.spinner("eBay'e iletiliyor..."):
                        try:
                            from sync_engine import PushEngine
                            result = PushEngine().push_updates()
                            st.success(result["message"])
                        except Exception as e:
                            st.error(f"Hata: {e}")

            with api_c3:
                st.info("📡 **eBay NATIVE Pull**\neBay'deki tüm ürünleri satır satır ERP'ye çeker.")
                if st.button("📥 Canlı Çek (Pull)", use_container_width=True):
                    with st.spinner("Katmanlar oluşturuluyor..."):
                        try:
                            from import_ebay_natively import import_ebay_natively
                            result = import_ebay_natively()
                            st.success(f"Başarılı: {result['success']} | Hata: {result['errors']}")
                        except Exception as e:
                            st.error(f"Çekim Hatası: {e}")
                            
            with api_c4:
                st.info("📷 **Amazon Görsel Botu**\nResmi olmayan ürünleri çeker ve yükler.")
                scrape_lim = st.number_input("Taranacak Adet", min_value=1, max_value=100, value=10, step=5)
                if st.button("🖼️ Görselleri Bul", use_container_width=True):
                    with st.spinner("Amazon'a bağlanılıyor..."):
                        try:
                            import asyncio
                            from amazon_image_scraper import AmazonImageScraper
                            asyncio.run(AmazonImageScraper().scrape_images(limit=scrape_lim))
                            st.success(f"{scrape_lim} ürün taraması tetiklendi.")
                        except Exception as e:
                            st.error(f"Görsel Botu Hatası: {e}")

        # --- YENİ EKLENEN DB ALTI (SENKRONİZASYON VE İÇE AKTARIM) YERLEŞİMİ ---
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔄 Toplu İçe Aktarım ve Senkronizasyon (CSV / Amazon)", expanded=False):
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.markdown("**📦 Easync (veya eBay) Toplu CSV Yükleme**")
                st.info("Pano'dan dışarı aktarılan devasa (Maks: 50MB) yedek tablolarını içeri aktarır.")
                uploaded_easync = st.file_uploader("Easync Ürün Listesi (.csv, .xlsx)", type=["csv", "xlsx"], help="Aktif listing'i tam formatında yükleyin.")
                if uploaded_easync is not None:
                    if uploaded_easync.size > 50 * 1024 * 1024:
                        st.error("Kritik Hata: Dosya 50 MB sınırını aştı.")
                    elif st.button("🚀 Katmanlara Dağıt (DB'ye Yaz)", use_container_width=True):
                        with st.spinner("Veriler parçalanıyor..."):
                            try:
                                df_imp = pd.read_csv(uploaded_easync) if uploaded_easync.name.endswith('.csv') else pd.read_excel(uploaded_easync)
                                result = db.import_easync_data(df_imp)
                                st.success(f"Dağıtım Tamam! Başarılı: {result['success']} | Hata: {result['errors']}")
                            except Exception as e:
                                st.error(f"Dosya Hatası: {e}")
            
            with t_col2:
                st.markdown("**🤖 Amazon'dan Güncelle (Otonom Orkestratör)**")
                st.info("Amazon arkaplan oturumunu zorla açar, DB'nizi yükleyip hatalı ASIN'leri temizler ve final durumunu/stokunu senkronize eder.")
                if st.button("🔄 Otonom Senkronizasyonu Başlat (Görünür Tarayıcı)", use_container_width=True, type="primary"):
                    try:
                        import subprocess, os
                        script_path = os.path.join(os.path.dirname(__file__), "orchestrator.py")
                        subprocess.Popen(["python3", script_path, "--manual-sync"], start_new_session=True)
                        st.success("🚀 Otonom Zincir çalıştırıldı! (Upload -> Download). Lütfen arkaplanda/yeni pencerede tamamlanmasını bekleyin.")
                    except Exception as e:
                        st.error(f"Başlatma Hatası: {e}")

    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")

# --- ÜRÜN ÇEKİM (RESEARCH) MODÜLÜ ---
def render_research_page():
    st.subheader("🛒 Ürün Araştırma ve Ekleme")
    
    st.markdown("### Sisteme Tekil Ürün Gir")
    with st.form("new_product_form", clear_on_submit=True):
        isku = st.text_input("ISKU (Informattach SKU) *", help="Şirket içi benzersiz ürün kodu. Örn: 001")
        base_title = st.text_input("Standart Ürün Adı *", help="Pazaryeri kısıtlamalarından bağımsız ana isim.")
        
        st.divider()
        asin = st.text_input("ASIN", help="Varsa Amazon ASIN kodu")
        upc = st.text_input("UPC / Evrensel Barkod", help="Varsa evrensel barkod")
        
        requires_exp = st.checkbox("Bu ürün SKT takibi gerektirir", value=False)
        
        st.markdown("**📁 Ürün Belgesi (Opsiyonel)**")
        doc_col1, doc_col2 = st.columns([1, 2])
        with doc_col1:
            doc_type = st.selectbox("Belge Türü", options=["", "SDS", "MANUAL", "WARRANTY", "CERTIFICATE"], format_func=lambda x: "Seçiniz..." if x == "" else x)
        with doc_col2:
            doc_url = st.text_input("Belge Linki (PDF vs)", help="Müşteriye otomatik gönderilecek belgenin web bağlantısı.")
            
        submitted = st.form_submit_button("Ürünü Veritabanına Kaydet")
        
        if submitted:
            if not isku or not base_title:
                st.error("ISKU ve Standart Ürün Adı zorunludur!")
            else:
                try:
                    clean_asin = asin.strip() if asin.strip() else None
                    clean_upc = upc.strip() if upc.strip() else None
                    
                    new_product = db.create_core_product(
                        base_title=base_title.strip(),
                        isku=isku.strip(),
                        asin=clean_asin,
                        upc=clean_upc,
                        requires_expiration=requires_exp
                    )
                    
                    if doc_type and doc_url.strip():
                        db.add_product_document(
                            product_id=new_product['id'],
                            document_type=doc_type,
                            document_url=doc_url.strip()
                        )
                    
                    st.success(f"'{isku}' başarıyla eklendi!")
                except Exception as e:
                    st.error(f"Ekleme Hatası: {e}")
                    
    st.markdown("---")
    drafts = db.get_unapproved_drafts()
    if drafts:
        
        # State management for Select All logic
        if "select_all_drafts" not in st.session_state:
            st.session_state.select_all_drafts = False
        if "drafts_table_key" not in st.session_state:
            st.session_state.drafts_table_key = 0

        st.markdown(f"**🔍 Tarama Sonuçları ({len(drafts)} Ürün Bulundu)**")
        
        c_sel1, c_sel2, c_gap = st.columns([2, 2, 6])
        with c_sel1:
            if st.button("✅ Tümünü Seç / Gösterilen", use_container_width=True):
                st.session_state.select_all_drafts = True
                st.session_state.drafts_table_key += 1
                st.rerun()
        with c_sel2:
            if st.button("❌ Seçimi Kaldır", key="clear_draft_selections", use_container_width=True):
                st.session_state.select_all_drafts = False
                st.session_state.drafts_table_key += 1
                st.rerun()
        
        table_data = []
        for d in drafts:
            asin = d.get('product_id')
            raw_price = str(d.get('price', '-')).replace('$', '').strip()
            amazon_url = f"https://www.amazon.com/dp/{asin}?th=1#p={raw_price}" if asin else f"https://www.amazon.com/#p={raw_price}"
            amazon_img = f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg" if asin else "https://via.placeholder.com/150?text=Yok"
            
            table_data.append({
                "Seç": st.session_state.select_all_drafts,
                "Foto": amazon_img,
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
                "Seç": st.column_config.CheckboxColumn("Seç"),
                "Foto": st.column_config.ImageColumn("Foto", help="Amazon Ham Görseli"),
                "Maliyet ($)": st.column_config.LinkColumn("Maliyet ($)", display_text=r"#p=(.*)"),
                "ID": None
            },
            disabled=["Foto", "ASIN", "Ürün Adı", "Maliyet ($)", "Satıcı", "Teslimat", "ID"],
            hide_index=True,
            use_container_width=True,
            key=f"drafts_table_editor_{st.session_state.drafts_table_key}"
        )
        
        if st.button("🚀 Seçili Ürünleri Kataloğa (Ana Tabloya) Aktar", type="primary", use_container_width=True):
            selected_drafts = edited_drafts[edited_drafts["Seç"] == True]
            if selected_drafts.empty:
                st.warning("Lütfen listelenecek en az bir ürün seçin.")
            else:
                draft_ids = selected_drafts["ID"].tolist()
                progress_text = f"{len(draft_ids)} ürün ana veri tabanı için hazırlanıyor (Yapay Zeka & Fiyatlandırma Devrede)..."
                my_bar = st.progress(0, text=progress_text)
                
                # Import ListingEngine here to avoid circular dependencies if any
                from listing_engine import ListingEngine
                engine = ListingEngine()
                
                with st.spinner("İşlem sürüyor, ürün başı ortalama 10-20 saniye sürebilir..."):
                    results = engine.process_drafts_to_db(draft_ids)
                    
                my_bar.progress(100, text="İşlem Tamamlandı!")
                
                if results["success"] > 0:
                    st.success(f"Tebrikler! {results['success']} ürün Ana Veritabanına (Kataloğa) başarıyla eklendi.")
                if results["skipped"] > 0:
                    st.info(f"{results['skipped']} ürün zaten veritabanında olduğu için atlandı.")
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

        if st.button("🗑️ Seçili Taslakları Sil", type="secondary", use_container_width=True):
            selected_drafts = edited_drafts[edited_drafts["Seç"] == True]
            if selected_drafts.empty:
                st.warning("Lütfen silinecek taslağı seçin.")
            else:
                with st.spinner("Siliniyor... Lütfen bekleyin"):
                    draft_ids = selected_drafts["ID"].tolist()
                    try:
                        # Toplu silme islemi (1 seferde veritabanina yolla)
                        chunck_size = 500
                        for i in range(0, len(draft_ids), chunck_size):
                            chunk = draft_ids[i:i + chunck_size]
                            db.client.table('draft').delete().in_('id', chunk).execute()
                        st.toast(f"✅ {len(draft_ids)} adet taslak başarıyla silindi!", icon="🗑️")
                        import time
                        time.sleep(1)
                        st.session_state.select_all_drafts = False
                        st.session_state.drafts_table_key += 1
                    except Exception as e:
                        st.error(f"Silme sırasında kod hatası: {e}")
                        
    else:
        st.caption("Şu an incelenmeyi bekleyen tarama (taslak) kaydı yok.")

    # DAİMA GÖRÜNSÜN DİYE IF DRAFTS: BLOĞUNUN DIŞINA ÇIKARILDI
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🤖 Yeni Ürün Bul (Kampanya / Fırsat Harvester)")
    st.info("Amazon fırsat sayfalarını ziyaret eder, yeni kampanyalı ürünleri bulur ve otonom şekilde sadece bu Taslak tablosuna aktarır.")
    if st.button("⚙️ Yeni Kampanyalı Ürünleri Tarayıp Getir", type="primary", use_container_width=True):
        try:
            import subprocess, os
            script_path = os.path.join(os.path.dirname(__file__), "orchestrator.py")
            subprocess.Popen(["python3", script_path, "--manual-scrape"], start_new_session=True)
            st.success("🚀 Fırsat Sömürücü başlatıldı! Lütfen arkaplanda tamamlanmasını bekleyin, 5-10 dk sonra sayfayı veya tabloyu yenileyin.")
        except Exception as e:
            st.error(f"Başlatma Hatası: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🕒 Tam Otonom Süreç (Zamanlanmış Test)")
    st.info("Bu buton, normalde saat 06:00 ve 18:00'de tetiklenen 'Tüm zinciri baştan sona çalıştır' sürecini manuel test etmek içindir. (Uçtan uca ürün çeker, fiyatlar, fiyat günceller, dosya indirir).")
    
    with st.expander("🤖 Bütünleşik Amazon Orkestratör Botu", expanded=False):
        import os, subprocess, signal
        status_col, action_col = st.columns([2,1])
        
        is_running = False
        bot_pid = None
        
        try:
            # Sadece argüman olarak --scheduled veya --manual ile çalışan ana orkestratörü ara
            result = subprocess.run(["pgrep", "-f", "orchestrator.py"], capture_output=True, text=True)
            pids = result.stdout.strip().split('\n')
            if result.returncode == 0 and pids and pids[0]:
                bot_pid = int(pids[0])
                is_running = True
        except Exception:
            pass

        with status_col:
            if is_running:
                st.success(f"✅ **Aktif ve Çalışıyor:** Amazon Orkestratör şu an arka planda otonom zinciri işletiyor. (PID: {bot_pid})")
            else:
                st.warning("⚠️ **Bot Duraklatıldı:** Amazon Orkestratör şu an çalışmıyor. Zamanlanmış görev dışındayız.")
                
        with action_col:
            if is_running:
                if st.button("⏹️ Botu Durdur", use_container_width=True, type="secondary"):
                    try:
                        import os
                        os.kill(bot_pid, signal.SIGTERM)
                        st.success("Durdurma sinyali gönderildi...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Durdurulamadı: {e}")
            else:
                if st.button("▶️ Test İçin Botu Başlat (Limitsiz)", use_container_width=True, type="primary"):
                    try:
                        base_dir = os.path.dirname(__file__)
                        script_path = os.path.join(base_dir, "orchestrator.py")
                        
                        subprocess.Popen(
                            ["python3", script_path, "--manual"], 
                            cwd=base_dir,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        st.success("🚀 Otonom Uçtan Uca Zincir Arkaplanda Başlatıldı!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Başlatılamadı: {e}")

def check_password():
    """Basit şifre koruması (st.secrets["APP_PASSWORD"] üzerine kurulu)"""
    import os
    import streamlit as st
    
    try:
        # Önce Streamlit Cloud Gizli Ayarlarına (Secrets) bak
        correct_password = st.secrets["APP_PASSWORD"]
    except (FileNotFoundError, KeyError, Exception):
        # Bulamazsa yerel .env dosyasına bak
        from dotenv import load_dotenv
        load_dotenv()
        correct_password = os.environ.get("APP_PASSWORD", "admin123") # Varsayılan: admin123
    
    def password_entered():
        if st.session_state.get("password_input", "") == correct_password:
            st.session_state["password_correct"] = True
            st.session_state["password_input"] = ""
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

def render_sync_page():
    st.subheader("🔄 Senkronizasyon ve Dosyalar")
    st.markdown("Bot durumları, eBay push/pull API işlemleri ve toplu veri ithalat/ihracat merkezi.")
    st.info("Amazon Bot kontrolleri, daha iyi bir erişilebilirlik için 'Araştırma ve Ekleme' menüsünün altına taşınmıştır.")

def main():
    if not check_password():
        return
        
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
    
    page = st.radio("Sistem Menüsü", ["📦 Ürün Yönetimi", "👥 Kişiler / Müşteriler", "⚙️ Fiyatlandırma Ayarları"], horizontal=True, label_visibility="collapsed")
    st.divider()
    
    if page == "📦 Ürün Yönetimi":
        tab_port, tab_rsch, tab_sync = st.tabs(["📊 Ürün Portföyü", "🛒 Araştırma ve Ekleme", "🔄 Senkronizasyon ve Dosyalar"])
        with tab_port:
            render_main_table()
        with tab_rsch:
            render_research_page()
        with tab_sync:
            render_sync_page()
            
    elif page == "👥 Kişiler / Müşteriler":
        import ui_contacts
        ui_contacts.render_contacts_page()
            
    elif page == "⚙️ Fiyatlandırma Ayarları":
        render_pricing_settings()

if __name__ == "__main__":
    main()