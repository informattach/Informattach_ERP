import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timedelta
from ebay_core import EbayManager

STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee"
namespace = "{urn:ebay:apis:eBLBaseComponents}"

def get_all_skus():
    ebay = EbayManager(store_id=STORE_ID)
    token = ebay.get_valid_token()
    
    page = 1
    all_asins = []
    
    print("eBay API'den tüm aktif SKU'lar doğrudan çekiliyor...")
    
    while True:
        now = datetime.utcnow()
        end_from = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_to = (now + timedelta(days=119)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <DetailLevel>ItemReturnDescription</DetailLevel>
  <Pagination>
    <EntriesPerPage>100</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <EndTimeFrom>{end_from}</EndTimeFrom>
  <EndTimeTo>{end_to}</EndTimeTo>
  <OutputSelector>SKU</OutputSelector>
  <OutputSelector>PaginationResult</OutputSelector>
  <OutputSelector>HasMoreItems</OutputSelector>
</GetSellerListRequest>
"""
        headers = {
            "X-EBAY-API-SITEID": "0",  
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1199",
            "X-EBAY-API-CALL-NAME": "GetSellerList",
            "X-EBAY-API-IAF-TOKEN": token, 
            "Content-Type": "text/xml"
        }
        
        import requests
        res = requests.post("https://api.ebay.com/ws/api.dll", data=xml, headers=headers)
        if res.status_code != 200:
            print(f"Hata: {res.text}")
            break
            
        root = ET.fromstring(res.text)
        items = root.findall(f".//{namespace}Item")
        
        for item in items:
            sku_node = item.find(f"{namespace}SKU")
            if sku_node is not None and sku_node.text:
                sku = sku_node.text.strip().upper()
                if sku.startswith("A-"):
                    sku = sku[2:]
                elif sku.startswith("INF-"):
                    sku = sku[4:]
                elif len(sku) == 11 and sku[0] in ['A', 'B', 'C', 'D', 'E', 'M']:
                    sku = sku[1:]
                
                # Check if basic Amazon B0... signature matches or fallback
                all_asins.append(sku)
                
        has_more = root.find(f".//{namespace}HasMoreItems")
        if has_more is None or has_more.text.lower() != 'true':
            break
        page += 1
        
    df = pd.DataFrame({'ASIN': list(set(all_asins))})
    df.to_csv('tum_aktif_asinler_ebay_api.csv', index=False)
    print(f"Bitti! eBay'de anlık olarak satışta olan {len(df)} benzersiz ASIN 'tum_aktif_asinler_ebay_api.csv' dosyasına kaydedildi.")

if __name__ == "__main__":
    get_all_skus()
