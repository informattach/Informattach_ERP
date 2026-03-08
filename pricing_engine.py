import math
from database import db
from typing import Dict, Any

class PricingEngine:
    """
    Easync tabanlı fiyatlandırma formülünü uygulayan Yapay Zeka Muhasebecisi.
    Kullanıcının ERP vizyonu referans alınarak yazılmıştır.
    Dinamiği doğrudan Supabase'den beslenir.
    """
    
    _rules_cache = {}
    _tiers_cache = {}
    
    @classmethod
    def get_tier_margin_from_db(cls, marketplace: str, cost: float) -> dict:
        """Supabase'den geliş maliyetine karşılık gelen kâr kademesini (Profit Tier) bulur."""
        if marketplace not in cls._tiers_cache:
            try:
                res = db.client.table("profit_tiers").select("*").eq("marketplace", marketplace).execute()
                cls._tiers_cache[marketplace] = res.data if res.data else []
            except Exception as e:
                print(f"[Pricing Engine] Profit tier çekme hatası: {e}")
                cls._tiers_cache[marketplace] = []
                
        tiers = cls._tiers_cache[marketplace]
        
        if tiers:
            for tier in tiers:
                min_p = float(tier.get('min_price', 0))
                max_p = tier.get('max_price')
                max_p = float(max_p) if max_p is not None else float('inf')
                
                if min_p <= cost <= max_p:
                    return {"percent": float(tier['margin_percent']), "fixed": float(tier['margin_fixed'])}
        
        # DB verisi yoksa veya bulamazsa Kullanıcının Hard Kuralı:
        if cost <= 18:
            return {"percent": 0.0, "fixed": 6.0}
        elif cost <= 24:
            return {"percent": 1.0, "fixed": 6.0}
        elif cost <= 30:
            return {"percent": 2.0, "fixed": 6.0}
        elif cost <= 36:
            return {"percent": 3.0, "fixed": 6.0}
        elif cost <= 42:
            return {"percent": 5.0, "fixed": 6.0}
            return {"percent": 7.0, "fixed": 6.0}

    @classmethod
    def get_pricing_rules_from_db(cls, marketplace: str) -> dict:
        """Supabase'den pazar yeri için belirlenmiş ERP Risk tamponlarını çeker."""
        if marketplace not in cls._rules_cache:
            try:
                res = db.client.table("pricing_rules").select("*").eq("marketplace", marketplace).execute()
                if res.data:
                    cls._rules_cache[marketplace] = res.data[0]
                else:
                    cls._rules_cache[marketplace] = None
            except Exception as e:
                print(f"[Pricing Engine] Pricing rules çekme hatası: {e}")
                cls._rules_cache[marketplace] = None
                
        if cls._rules_cache[marketplace]:
            return cls._rules_cache[marketplace]
            
        # Default fallback (Eğer veritabanında tablolar henüz oluşmadıysa kod patlamasın)
        return {
            "return_allowance_percent": 0.1,
            "damage_allowance_percent": 0.1,
            "overhead_allowance_percent": 0.1,
            "ad_spend_percent": 0.0,
            "sales_tax_allowance_percent": 3.0,
            "additional_logistics_fee": 0.0,
            "min_profit_absolute": 0.0
        }

    @staticmethod
    def apply_psychological_rounding(raw_price: float) -> float:
        """
        Gelişmiş Psikolojik Fiyatlandırma (.49 ve .98 Yuvarlaması)
        - küsurat < .49 ise X.49 yapılır.
        - küsurat >= .49 ise X.98 yapılır.
        """
        integer_part = math.floor(raw_price)
        decimal_part = raw_price - integer_part
        
        if decimal_part < 0.49:
            return round(integer_part + 0.49, 2)
        else:
            return round(integer_part + 0.98, 2)

    @staticmethod
    def calculate_final_price(
        source_price: float, 
        marketplace: str = "ebay",
        category_id: str = None,
        override_marketplace_fee: float = None
    ) -> float:
        """Nihai Vitrin Satış Fiyatını Tüm Tamponlarla Birlikte Hesaplar"""
        if source_price <= 0:
            return 0.0
            
        # 1. DB'den Verileri / Kuralları Çek
        tier = PricingEngine.get_tier_margin_from_db(marketplace, source_price)
        rules = PricingEngine.get_pricing_rules_from_db(marketplace)
        
        # 2. Efektif Kaynak Maliyeti (Vergi Tamponu Eklenmiş = Checkout tax compensation)
        sales_tax_allowance_pct = float(rules.get('sales_tax_allowance_percent', 0.0))
        effective_source_price = source_price * (1.0 + (sales_tax_allowance_pct * 0.01))
        
        # 3. Kâr (Profit) Hesaplama
        margin_percent = tier['percent']
        margin_fixed = tier['fixed']
        
        profit = (effective_source_price * margin_percent * 0.01) + margin_fixed
        min_profit = float(rules.get('min_profit_absolute', 0.0))
        
        if profit < min_profit:
            profit = min_profit
            
        # 4. Pazar Yeri Kategorik Komisyon
        marketplace_fee_percent = override_marketplace_fee if override_marketplace_fee is not None else 15.0
            
        # 5. Toplam İşletme Yükü (Bölen Payda)
        ad_spend = float(rules.get('ad_spend_percent', 0.0))
        return_allowance = float(rules.get('return_allowance_percent', 0.1))
        damage_allowance = float(rules.get('damage_allowance_percent', 0.1))
        overhead_allowance = float(rules.get('overhead_allowance_percent', 0.1))
        
        total_burden_percent = marketplace_fee_percent + ad_spend + return_allowance + damage_allowance + overhead_allowance
        denominator = 1.0 - (total_burden_percent * 0.01)
        
        # Olası bölme hatalarını koru
        if denominator <= 0:
            denominator = 0.05 
            
        # 6. Lojistik ve Alt Toplam
        additional_logistics_fee = float(rules.get('additional_logistics_fee', 0.0))
        numerator = effective_source_price + profit + additional_logistics_fee
        
        # 7. Nihai Fiyat İlk Hesap (İlk Sabit Ücret $0.40 baz alınır)
        marketplace_fixed_fee = 0.40
        raw_price = (numerator / denominator) + marketplace_fixed_fee
        
        # 8. Kural Kontrolü: 10 Dolar Altı Sabit Ücret Düşüşü (.30)
        if raw_price < 10.00:
            marketplace_fixed_fee = 0.30
            raw_price = (numerator / denominator) + marketplace_fixed_fee
            
        # 9. Gelişmiş .49 / .98 Psikolojik Yuvarlama
        final_price = PricingEngine.apply_psychological_rounding(raw_price)
            
        return final_price

if __name__ == "__main__":
    # Test Senaryosu: $10.00'lık ürün (Easync Kuralı 0-18 = %0)
    print("--- 10$ KAYNAK TESTI ---")
    test_price = 10.00
    final = PricingEngine.calculate_final_price(test_price)
    print(f"Efektif Sonuc (Yuvarlamali): {final}")
    
    print("\n--- 20$ KAYNAK TESTI ---")
    final20 = PricingEngine.calculate_final_price(20.00)
    print(f"Efektif Sonuc: {final20}")