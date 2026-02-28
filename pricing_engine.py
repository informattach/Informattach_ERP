from typing import Dict

class PricingEngine:
    @staticmethod
    def calculate_final_price(cost: float, rule: Dict) -> float:
        """
        Girdi: Ham maliyet ve veritabanından gelen kural sözlüğü.
        Çıktı: Nihai satış fiyatı.
        """
        # 1. Komisyon ve Sabit Ücretler
        commission = cost * (rule['commission_rate'] / 100)
        fixed_fee = rule['fixed_fee']
        
        # 2. Vergi (KDV vb.)
        tax = cost * (rule['tax_rate'] / 100)
        
        # 3. Kar Marjı (Tier bazlı mantık buraya eklenebilir)
        # Örn: 0-50$ arası %30, 50$+ %20 kar gibi. 
        # Şimdilik genel kuralı uyguluyoruz.
        profit_margin = cost * (rule['profit_margin_tiers'] / 100)
        
        # Toplam Fiyat
        final_price = cost + commission + fixed_fee + tax + profit_margin
        
        # Psikolojik fiyatlandırma (Örn: .99 ile bitirme) - Opsiyonel
        return round(final_price, 2)

    def process_all_listings(self, db_manager):
        """
        Tüm ürünleri gezip fiyatları güncelleyen ana döngü.
        """
        products = db_manager.get_all_products()
        
        for product in products:
            # Her ürünün en az bir kaynağı ve kuralı olmalı
            if not product['sources'] or not product['listings']:
                continue
                
            cost = product['sources'][0]['cost_price']
            marketplace = product['listings'][0]['marketplace']
            
            # Marketplace'e göre kuralı getir (Bu sorguyu db_manager'a ekleyeceğiz)
            rule = db_manager.get_pricing_rule(marketplace)
            
            if rule:
                new_price = self.calculate_final_price(cost, rule)
                db_manager.update_listing_price(product['listings'][0]['id'], new_price)