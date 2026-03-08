import csv
import os

from pricing_engine import PricingEngine

def calculate_new_price(cost):
    if not cost or cost <= 0:
        return None
        
    # Yeni PricingEngine sınıfını çağır
    return PricingEngine.calculate_final_price(cost)

def run_cerrahi_operasyon():
    easync_map = {}
    easync_file = "easync.csv"
    ebay_file = "ebay_all_listings.csv"

    print("1. Easync haritası okunuyor (ASIN ve Maliyetler)...")
    if not os.path.exists(easync_file):
        print(f"HATA: {easync_file} klasörde bulunamadı!")
        return

    with open(easync_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row.get('Target Product Id', '').strip()
            asin = row.get('Source Product Id', '').strip()
            cost_str = row.get('Source Price', '').replace('$', '').strip()
            try:
                cost = float(cost_str) if cost_str else 0.0
            except:
                cost = 0.0

            if item_id:
                easync_map[item_id] = {'asin': asin, 'cost': cost}

    print("2. eBay canlı ilanları okunuyor...")
    if not os.path.exists(ebay_file):
        print(f"HATA: {ebay_file} klasörde bulunamadı!")
        return

    csv_data = []
    guncellenen_isku = 0
    guncellenen_fiyat = 0
    guncellenen_stok = 0
    toplam_islenen = 0

    print("3. Fiyatlandırma ve Stok kuralları 3000 ürüne uygulanıyor...")
    with open(ebay_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_id = row.get('Item number', '').strip()
            if not item_id:
                continue
                
            isku = row.get('Custom label (SKU)', '').strip()
            
            # Fiyatı al
            price_str = row.get('Current price', '').strip() or row.get('Start price', '').strip()
            try:
                current_price = float(price_str.replace('$', '').replace(',', '').strip()) if price_str else 0.0
            except:
                current_price = 0.0

            # Stoğu al
            try:
                qty = int(row.get('Available quantity', 0))
            except:
                qty = 0

            toplam_islenen += 1
            new_qty = qty
            new_isku = isku
            new_price = current_price

            # KURAL 1: Stok 5 ise 3 yap
            if qty == 5:
                new_qty = 3
                guncellenen_stok += 1

            # Easync'te bu ürüne dair ASIN/Maliyet verisi varsa
            if item_id in easync_map:
                asin = easync_map[item_id]['asin']
                cost = easync_map[item_id]['cost']

                # KURAL 2: ISKU boşsa ASIN'i A- formatında ekle
                if not new_isku and asin:
                    new_isku = f"A-{asin}"
                    guncellenen_isku += 1

                # KURAL 3: Fiyat formülünü uygula
                if cost > 0:
                    calculated = calculate_new_price(cost)
                    if calculated and calculated != current_price:
                        new_price = calculated
                        guncellenen_fiyat += 1

            # eBay File Exchange yükleme formatı
            csv_data.append({
                "Action": "Revise",
                "ItemID": item_id,
                "CustomLabel": new_isku,
                "StartPrice": new_price,
                "Quantity": new_qty
            })

    print("4. eBay Toplu Güncelleme (Bulk Upload) dosyası oluşturuluyor...")
    output_file = "ebay_toplu_guncelleme.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Action", "ItemID", "CustomLabel", "StartPrice", "Quantity"])
        writer.writeheader()
        writer.writerows(csv_data)

    print(f"\nCERRAHİ MÜDAHALE TAMAMLANDI!")
    print(f"- İşlenen Toplam Ürün: {toplam_islenen}")
    print(f"- Yeni ISKU Üretilen: {guncellenen_isku}")
    print(f"- Formülle Fiyatı Güncellenen: {guncellenen_fiyat}")
    print(f"- Stoğu (5'ten 3'e) İndirilen: {guncellenen_stok}")
    print(f"\nSON ADIM: Lütfen '{output_file}' dosyasını eBay Seller Hub -> Reports -> Uploads ekranından yükle.")

if __name__ == "__main__":
    run_cerrahi_operasyon()