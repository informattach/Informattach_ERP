import streamlit as st
import pandas as pd
from database import db

def render_pricing_settings():
    st.title("⚙️ Fiyatlandırma Yönetimi (ERP)")
    st.markdown("E-Ticaret deponuzun kârlılık, risk ve komisyon oranlarını buradan dinamik olarak yönetebilirsiniz. Otonom fiyatlandırma motoru her işlemde bu kurallara bakar.")
    
    # 1. PAZAR YERİ SEÇİMİ (KAYNAK VE HEDEF)
    col_mp1, col_mp2 = st.columns(2)
    with col_mp1:
        source_marketplace = st.selectbox("📥 Kaynak Pazaryeri (Tedarikçi)", ["amazon_us", "aliexpress", "cj_dropshipping"], index=0, help="Bu platforma özel maliyet ve vergi kuralları hesaplanır.")
    with col_mp2:
        target_marketplace = st.selectbox("📤 Hedef Pazaryeri (Vitrin)", ["ebay", "amazon", "shopify"], index=0, help="Bu platforma özel kategorik komisyonlar ve risk bütçeleri uygulanır.")
    
    st.markdown("---")
    
    # --- VERİTABANINDAN MEVCUT AYARLARI ÇEKME ---
    try:
        rules_res = db.client.table("pricing_rules").select("*").eq("marketplace", target_marketplace).execute()
        current_rules = rules_res.data[0] if rules_res.data else {
            "return_allowance_percent": 0.10,
            "damage_allowance_percent": 0.10,
            "overhead_allowance_percent": 0.10,
            "ad_spend_percent": 0.00,
            "sales_tax_allowance_percent": 3.00,
            "additional_logistics_fee": 0.00,
            "min_profit_absolute": 0.00
        }
    except Exception as e:
        st.error(f"Veritabanı bağlantı hatası: {e}")
        return

    # 2. ERP RİSK VE İŞLETME ÖDENEKLERİ YÖNETİMİ
    st.subheader("🛡️ Risk ve İşletme Giderleri (Risk Buffers)")
    st.caption("Fiyatlandırma anında ürün maliyetinin üzerine eklenecek görünmez sigorta fonları. (Girilen değerler Yüzde '%' cinsindendir!)")
    
    with st.form("pricing_buffer_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            ret_allowance = st.number_input("İade Sigortası Payı (%)", min_value=0.0, max_value=20.0, value=float(current_rules.get("return_allowance_percent", 0.10)), step=0.1)
            ad_spend = st.number_input("Reklam / Promoted Listings (%)", min_value=0.0, max_value=30.0, value=float(current_rules.get("ad_spend_percent", 0.00)), step=0.1, help="İlanı öne çıkarmak için harcanacak bütçe")
            
        with col2:
            dmg_allowance = st.number_input("Zayi/Kırılma Sigortası (%)", min_value=0.0, max_value=20.0, value=float(current_rules.get("damage_allowance_percent", 0.10)), step=0.1)
            overhead_allowance = st.number_input("Aylık Yazılım/Gider Payı (%)", min_value=0.0, max_value=20.0, value=float(current_rules.get("overhead_allowance_percent", 0.10)), step=0.1)
            
        with col3:
            tax_allowance = st.number_input("Amazon Kaynak Vergi Tamponu (%)", min_value=0.0, max_value=15.0, value=float(current_rules.get("sales_tax_allowance_percent", 3.00)), step=0.1, help="Amazon State Tax sürprizlerine karşı")
            additional_fee = st.number_input("Ek Lojistik Ücreti ($ / Sabit)", min_value=0.0, max_value=50.0, value=float(current_rules.get("additional_logistics_fee", 0.00)), step=0.5, help="3PL depo taşıması gibi sabit ek masraflar")

        min_profit = st.number_input("Minimum Mutlak Kâr ($)", min_value=0.0, max_value=100.0, value=float(current_rules.get("min_profit_absolute", 0.00)), step=0.5, help="Fiyat rekabeti algoritması kârı asla bunun altına düşüremez.")
            
        submit_buffers = st.form_submit_button("🛡️ Risk Tamponlarını Güncelle", use_container_width=True)
        if submit_buffers:
            payload = {
                "marketplace": target_marketplace,
                "return_allowance_percent": ret_allowance,
                "damage_allowance_percent": dmg_allowance,
                "overhead_allowance_percent": overhead_allowance,
                "ad_spend_percent": ad_spend,
                "sales_tax_allowance_percent": tax_allowance,
                "additional_logistics_fee": additional_fee,
                "min_profit_absolute": min_profit
            }
            try:
                db.client.table("pricing_rules").upsert(payload, on_conflict="marketplace").execute()
                st.success("Tüm risk tamponları ve güvenlik kalkanları başarıyla güncellendi!")
                st.rerun()
            except Exception as e:
                st.error(f"Güncelleme yapılamadı: {e}")

    st.markdown("---")

    # 3. KÂR KADEMELERİ (PROFIT TIERS) YÖNETİMİ
    st.subheader("📈 Kâr Kademeleri (Profit Tiers)")
    st.caption("Ürün geliş fiyatına göre kademeli (Tiered) artan kâr planları. (Örn: 0-18Dolar arasına %0 ve 6$ Sabit Kâr)")
    
    try:
        tiers_res = db.client.table("profit_tiers").select("*").eq("marketplace", target_marketplace).order("min_price").execute()
        tiers_data = tiers_res.data
    except Exception as e:
        tiers_data = []

    if tiers_data:
        df_tiers = pd.DataFrame(tiers_data)
        # Display editable dataframe
        display_df = df_tiers[["id", "min_price", "max_price", "margin_percent", "margin_fixed"]].copy()
        
        st.markdown("**Mevcut Kademeler:**")
        edited_tiers = st.data_editor(
            display_df,
            column_config={
                "id": None, # Gizli tut
                "min_price": st.column_config.NumberColumn("Min Maliyet ($)", format="%.2f"),
                "max_price": st.column_config.NumberColumn("Max Maliyet ($)", format="%.2f"),
                "margin_percent": st.column_config.NumberColumn("Kâr Yüzdesi (%)", format="%.2f"),
                "margin_fixed": st.column_config.NumberColumn("Sabit Kâr ($)", format="%.2f"),
            },
            num_rows="dynamic",
            use_container_width=True
        )
        
        if st.button("💾 Tier Tablosunu Kaydet / Güncelle"):
            # Update changes to DB
            for idx, row in edited_tiers.iterrows():
                try:
                    payload = {
                        "marketplace": target_marketplace,
                        "min_price": float(row["min_price"]),
                        "max_price": float(row["max_price"]) if pd.notnull(row["max_price"]) else None,
                        "margin_percent": float(row["margin_percent"]),
                        "margin_fixed": float(row["margin_fixed"])
                    }
                    if "id" in row and pd.notnull(row["id"]):
                        payload["id"] = row["id"]
                    
                    if "id" in payload:
                        db.client.table("profit_tiers").update(payload).eq("id", payload["id"]).execute()
                    else:
                        db.client.table("profit_tiers").insert(payload).execute()
                except Exception as e:
                    st.error(f"Tier güncelleme hatası: {e}")
                    
            st.success("Kâr kademeleri veritabanına işlendi!")
            st.rerun()
    else:
        st.info("Bu pazar yeri için kâr kademesi tanımlanmamış.")

    st.markdown("---")
    
    # 5. TEST MOTORU (CANLI SİMÜLATÖR)
    st.subheader("🧪 Canlı Fiyatlandırma Simülatörü")
    st.caption("Yukarıdaki tüm veritabanı kurallarınızı test etmek için bir kaynak maliyeti girin veya gerçek bir ürünü veritabanından çağırın.")
    
    with st.expander("Fiyat Motorunu (Pricing Engine) Test Et", expanded=True):
        tab1, tab2 = st.tabs(["✍️ Manuel Veri ile Test", "🔍 Kayıtlı Ürün (ASIN) ile Test"])
        
        with tab1:
            col_test1, col_test2 = st.columns([1, 2])
            with col_test1:
                test_source_cost = st.number_input("Amazon/Kaynak Ürün Maliyeti ($)", min_value=0.1, value=10.00, step=0.5)
                test_category_fee = st.number_input("Test: Özel eBay Kategori Kesintisi (%)", min_value=0.0, max_value=30.0, value=15.0, step=0.5)
                
            with col_test2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🧮 Manuel Değerlerle Hesapla", use_container_width=True):
                    from pricing_engine import PricingEngine
                    try:
                        final_price = PricingEngine.calculate_final_price(
                            source_price=test_source_cost,
                            marketplace=target_marketplace,
                            override_marketplace_fee=test_category_fee
                        )
                        st.success(f"**Tahmini Vitrin Fiyatı ({target_marketplace.upper()}): ${final_price:.2f}**")
                    except Exception as e:
                        st.error(f"Simülasyon Hatası: {e}")
                        
        with tab2:
            col_asin1, col_asin2 = st.columns([1, 2])
            with col_asin1:
                test_asin = st.text_input("Ürün ASIN Kodu Girin", placeholder="Örn: B08XYZZ")
            with col_asin2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔍 Veritabanından Bul ve Hesapla", use_container_width=True):
                    if test_asin:
                        try:
                            # If user accidentally pastes an A-ASIN or INF-ISKU, strip it
                            search_term = test_asin.strip().upper()
                            if search_term.startswith("A-"):
                                search_term = search_term[2:]
                            elif search_term.startswith("INF-"):
                                search_term = search_term[4:]
                            
                            # 1. Product'ı bul
                            raw_product = db.get_product_by_asin(search_term)
                            if not raw_product:
                                st.warning(f"'{search_term}' sistemde bulunamadı. Easync dosyanızdaki fiyat-maliyet sütunları boş olabilir veya bu ürün 'ghost' bir kayıt olabilir.")
                            else:
                                # 2. Sources'tan base_cost bul
                                sources = raw_product.get('sources', [])
                                if not sources:
                                    st.warning("Bu ürünün 'sources' tablosunda bir maliyet (base_cost) kaydı yok.")
                                else:
                                    db_cost = float(sources[0].get('base_cost', 0))
                                    if db_cost <= 0:
                                        st.warning("Bu ürünün veritabanındaki maliyeti $0.00 (veya girilmemiş). Hesaplama yapılamaz.")
                                    else:
                                        # 3. Kategori bilgisi varsa kullan, yoksa 15% varsay
                                        cat_fee = 15.0 # Fallback
                                        listings = raw_product.get('listings', [])
                                        if listings:
                                            cat_id = listings[0].get('category_id')
                                            if cat_id:
                                                # Kategori sözlüğünden kesintiyi bulmaya çalış
                                                c_res = db.client.table('marketplace_categories').select("marketplace_fee_percent").eq('marketplace', target_marketplace).eq('category_id', cat_id).execute()
                                                if c_res.data:
                                                    cat_fee = float(c_res.data[0]['marketplace_fee_percent'])
                                        
                                        from pricing_engine import PricingEngine
                                        final_price = PricingEngine.calculate_final_price(
                                            source_price=db_cost,
                                            marketplace=target_marketplace,
                                            override_marketplace_fee=cat_fee
                                        )
                                        
                                        st.success(f"**Ürün Bulundu:** {raw_product.get('product_base_content', [{}])[0].get('base_title', 'İsimsiz')}")
                                        st.info(f"**Veritabanı Maliyeti:** ${db_cost:.2f} | **Uygulanan eBay Kesintisi:** %{cat_fee}")
                                        st.success(f"**🔥 Otonom Yansıyacak Vitrin Fiyatı: ${final_price:.2f}**")
                                        
                        except Exception as e:
                            st.error(f"Sorgu veya Hesaplama Hatası: {e}")
                    else:
                        st.warning("Lütfen bir ASIN girin.")
