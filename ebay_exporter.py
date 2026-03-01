import pandas as pd
from typing import List, Dict

class EbayExporter:
    @staticmethod
    def generate_ebay_csv(products: List[Dict]) -> str:
        """
        Supabase'den gelen ürün listesini eBay File Exchange CSV formatına dönüştürür.
        """
        ebay_rows = []
        
        for p in products:
            # Listeleme ve kaynak verilerini güvenli bir şekilde al
            listing = p.get('listings', [{}])[0] if p.get('listings') else {}
            source = p.get('sources', [{}])[0] if p.get('sources') else {}
            
            # Eğer satış fiyatı hesaplanmamışsa veya ürün listelenmeyecekse atla
            if not listing.get('listed_price'):
                continue
                
            # eBay'in zorunlu sütun haritalaması
            row = {
                "*Action(SiteID=US|Country=US|Currency=USD|Version=1193)": "Add",
                "CustomLabel": p.get('master_sku', ''), # Senin A, M, C prefixli SKU'ların
                "*Title": p.get('title', '')[:80], # eBay başlık sınırı 80 karakterdir
                "*Quantity": 2 if source.get('stock_status') else 0,
                "*Format": "FixedPrice",
                "*StartPrice": listing.get('listed_price', 0),
                "*ConditionID": 1000, # 1000 = New
                "PicURL": "", # İleride eklenecek
                "*Category": "1" # Varsayılan kategori, dinamik hale getirilebilir
            }
            ebay_rows.append(row)
            
        df = pd.DataFrame(ebay_rows)
        # Excel'de Türkçe sistemlerde bozulmaması için virgül ile ayırıyoruz
        return df.to_csv(index=False, sep=",")