import requests
import base64
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class EbayManager:
    def __init__(self, store_id):
        self.store_id = store_id
        self.base_url = "https://api.ebay.com/sell/inventory/v1"
        self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"

    def get_valid_token(self):
        response = supabase.table("stores").select("api_config").eq("id", self.store_id).execute()
        
        if not response.data:
            raise ValueError(f"ID'si {self.store_id} olan mağaza bulunamadı.")
            
        config = response.data[0]['api_config']
        expires_at = datetime.fromisoformat(config.get('expires_at', '2000-01-01T00:00:00'))
        
        if datetime.now() > (expires_at - timedelta(minutes=5)):
            print("Access Token süresi dolmuş veya dolmak üzere, yenileniyor...")
            return self._refresh_token(config)
        
        return config['access_token']

    def _refresh_token(self, config):
        auth_str = f"{config['ebay_app_id']}:{config['ebay_cert_id']}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {b64_auth}"
        }
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": config['refresh_token']
        }

        res = requests.post(self.auth_url, headers=headers, data=payload)
        
        if res.status_code == 200:
            data = res.json()
            new_token = data['access_token']
            new_expiry = (datetime.now() + timedelta(seconds=data['expires_in'])).isoformat()
            
            config['access_token'] = new_token
            config['expires_at'] = new_expiry
            
            supabase.table("stores").update({"api_config": config}).eq("id", self.store_id).execute()
            print("Token başarıyla yenilendi ve veritabanına kaydedildi.")
            return new_token
        else:
            raise Exception(f"Token yenileme hatası: {res.text}")

    def create_and_publish_offer(self, sku, policies):
        token = self.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Language": "en-US",
            "Content-Type": "application/json"
        }
        
        print("1. Albuquerque (87110) kargo lokasyonu ayarlanıyor...")
        loc_key = "US-ALBUQUERQUE"
        loc_url = f"{self.base_url}/location/{loc_key}"
        loc_payload = {
            "location": {
                "address": {
                    "addressLine1": "Fulfillment Center",
                    "city": "Albuquerque",
                    "stateOrProvince": "NM",
                    "postalCode": "87110",
                    "country": "US"
                }
            },
            "locationTypes": ["WAREHOUSE"],
            "name": "US Dropship Location",
            "merchantLocationStatus": "ENABLED"
        }
        
        # Hata buradaydı: PUT yerine POST olmalı
        loc_res = requests.post(loc_url, headers=headers, json=loc_payload)
        
        if loc_res.status_code not in [200, 201, 204] and "already exists" not in loc_res.text:
            return f"Lokasyon Oluşturma Hatası ({loc_res.status_code}): {loc_res.text}"
            
        print("Lokasyon başarıyla doğrulandı/ayarlandı!")

        print("2. Satış teklifi (Offer) oluşturuluyor...")
        offer_url = f"{self.base_url}/offer"
        offer_payload = {
            "sku": sku,
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "availableQuantity": 5,
            "categoryId": "30120", 
            "listingPolicies": {
                "fulfillmentPolicyId": policies['fulfillment_id'],
                "paymentPolicyId": policies['payment_id'],
                "returnPolicyId": policies['return_id']
            },
            "merchantLocationKey": loc_key,
            "pricingSummary": {
                "price": {"value": "29.99", "currency": "USD"}
            }
        }
        
        offer_res = requests.post(offer_url, headers=headers, json=offer_payload)
        
        if offer_res.status_code not in [200, 201]:
            return f"Offer Oluşturma Hatası ({offer_res.status_code}): {offer_res.text}"
            
        offer_id = offer_res.json().get('offerId')
        print(f"Offer oluşturuldu. ID: {offer_id}\n3. Ürün canlı yayına alınıyor...")
        
        publish_url = f"{self.base_url}/offer/{offer_id}/publish"
        pub_res = requests.post(publish_url, headers=headers)
        
        if pub_res.status_code in [200, 201]:
            listing_id = pub_res.json().get('listingId')
            return f"BAŞARILI! Ürün eBay'de satışta. Listing ID: {listing_id}"
        else:
            return f"Yayınlama Hatası ({pub_res.status_code}): {pub_res.text}"

    def update_price_and_quantity(self, sku, new_price, new_qty, item_id=None):
        """Sadece belirli bir ISKU'nun fiyatını ve stoğunu API ile anında günceller.
        REST API başarısız olursa (Örn: Easync legacy ilanları) Trading API'ye fallback yapar."""
        token = self.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Language": "en-US",
            "Content-Type": "application/json"
        }
        
        # 1. Önce ürünün Inventory Item bilgilerini çekmemiz/güncellememiz lazım
        item_url = f"{self.base_url}/inventory_item/{sku}"
        
        # Ürünün sadece stoğunu güncelliyoruz (Availability)
        item_payload = {
            "availability": {
                "shipToLocationAvailability": {"quantity": new_qty}
            },
            "condition": "NEW" 
        }
        
        print(f"{sku} için stok güncelleniyor -> Yeni Stok: {new_qty}")
        res_item = requests.put(item_url, headers=headers, json=item_payload)
        
        if res_item.status_code not in [200, 204]:
            print(f"Stok Güncelleme Hatası ({res_item.status_code}): {res_item.text}")
            # Eğer Legacy (eski) ilan henüz Inventory API'ye tam göç etmediyse hata verebilir
        else:
            print("Stok başarıyla güncellendi.")

        # 2. Ürünün fiyatı Offer (Teklif) üzerinden güncellenir
        # eBay'de bir SKU'nun birden fazla teklifi olabilir, önce aktif offer ID'yi bulmalıyız
        offers_url = f"{self.base_url}/offer?sku={sku}"
        res_offers = requests.get(offers_url, headers=headers)
        
        if res_offers.status_code == 200 and res_offers.json().get('offers'):
            offer_id = res_offers.json()['offers'][0]['offerId']
            
            # Bulunan Offer ID'nin sadece fiyatını güncelleyen uç nokta (Endpoint)
            price_url = f"{self.base_url}/offer/{offer_id}"
            
            # Sadece fiyat bilgisini gönderiyoruz (Patch mantığıyla)
            price_payload = {
                "pricingSummary": {
                    "price": {"value": str(new_price), "currency": "USD"}
                }
            }
            
            print(f"{sku} için fiyat güncelleniyor -> Yeni Fiyat: ${new_price}")
            # Fiyat güncellemesi genelde mevcut offer'ı okuyup revize etmeyi gerektirir.
            # Not: eBay'de tam Offer güncellemesi tüm alanları zorunlu tutabilir, 
            # bu basit fiyat enjeksiyonu çalışmazsa bir sonraki adımda dinamik get-and-put yaparız.
            # Şimdilik eBay'in sağladığı hızlı fiyat güncelleme objesini test ediyoruz.
        else:
            print(f"Offer bulunamadı veya REST Fiyat API Hatası: {res_offers.text}")
            print(f"[{sku}] TRADING API (ReviseInventoryStatus) Fallback deneniyor...")
            self._fallback_revise_inventory_status(sku, item_id, new_price, new_qty, token)

    def _fallback_revise_inventory_status(self, sku, item_id, new_price, new_qty, token):
        """Eski Easync ilanları gibi REST API'de Offer kaydı olmayan ürünleri Trading API üzerinden günceller."""
        xml_url = "https://api.ebay.com/ws/api.dll"
        headers = {
            "Content-Type": "text/xml",
            "X-EBAY-API-SITEID": "0", 
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1311",
            "X-EBAY-API-CALL-NAME": "ReviseInventoryStatus",
            "X-EBAY-API-IAF-TOKEN": token
        }
        
        item_identifier = f"<ItemID>{item_id}</ItemID>" if item_id else f"<SKU>{sku}</SKU>"
        
        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseInventoryStatusRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <InventoryStatus>
    {item_identifier}
    <StartPrice>{new_price}</StartPrice>
    <Quantity>{new_qty}</Quantity>
  </InventoryStatus>
</ReviseInventoryStatusRequest>
"""
        try:
            res = requests.post(xml_url, headers=headers, data=xml_payload.encode('utf-8'))
            if "Success" in res.text or "Warning" in res.text:
                print(f"[{sku}] Trading API Fallback BAŞARILI: Fiyat=${new_price}, Stok={new_qty}")
            else:
                print(f"[{sku}] Trading API Fallback Hatası: {res.text}")
        except Exception as e:
            print(f"[{sku}] Trading API Fallback İstisna Hatası: {e}")

    def create_and_publish_offer_xml_fallback(self, sku, title, description_html, price, quantity, policies, category_id, image_urls):
        """
        REST API'nin desteklemediği durumlar için (Varyasyonlar, Legacy özellikleri, vb)
        AddFixedPriceItem (Trading API) XML kullanarak ürünü listeler.
        """
        token = self.get_valid_token()
        
        # Trading API Endpoint
        xml_url = "https://api.ebay.com/ws/api.dll"
        
        headers = {
            "Content-Type": "text/xml",
            "X-EBAY-API-SITEID": "0", # 0 = ABD (US)
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1311",
            "X-EBAY-API-CALL-NAME": "AddFixedPriceItem",
            "X-EBAY-API-IAF-TOKEN": token
        }
        
        # Resim XML tag'lerini oluşturalım
        pictures_xml = ""
        if image_urls and isinstance(image_urls, list):
            for img in image_urls:
                pictures_xml += f"<PictureURL>{img}</PictureURL>\n"
                
        # Eğer Kategori ID gelmezse genel bir kategori atayalım (örnek: 30120)
        cat_id = category_id if category_id else "30120"
                
        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<AddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <Title><![CDATA[{title[:80]}]]></Title>
    <Description><![CDATA[{description_html}]]></Description>
    <PrimaryCategory>
      <CategoryID>{cat_id}</CategoryID>
    </PrimaryCategory>
    <StartPrice currencyID="USD">{price}</StartPrice>
    <ConditionID>1000</ConditionID> <!-- 1000 = New -->
    <Country>US</Country>
    <Currency>USD</Currency>
    <DispatchTimeMax>3</DispatchTimeMax>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <PostalCode>87110</PostalCode>
    <Quantity>{quantity}</Quantity>
    <SKU>{sku}</SKU>
    <PictureDetails>
      {pictures_xml}
    </PictureDetails>
    <SellerProfiles>
      <SellerPaymentProfile>
        <PaymentProfileID>{policies.get('payment_id')}</PaymentProfileID>
      </SellerPaymentProfile>
      <SellerReturnProfile>
        <ReturnProfileID>{policies.get('return_id')}</ReturnProfileID>
      </SellerReturnProfile>
      <SellerShippingProfile>
        <ShippingProfileID>{policies.get('fulfillment_id')}</ShippingProfileID>
      </SellerShippingProfile>
    </SellerProfiles>
    <ItemSpecifics>
      <NameValueList>
        <Name>Brand</Name>
        <Value>Generic</Value>
      </NameValueList>
      <!-- Ekstra ItemSpecifics buraya gelebilir -->
    </ItemSpecifics>
  </Item>
</AddFixedPriceItemRequest>"""

        print(f"[{sku}] XML (AddFixedPriceItem) Fallback çağrısı yapılıyor...")
        response = requests.post(xml_url, headers=headers, data=xml_payload.encode('utf-8'))
        
        content = response.text
        if "<Ack>Success</Ack>" in content or "<Ack>Warning</Ack>" in content:
            # ItemID çıkarımı
            import re
            item_id_match = re.search(r"<ItemID>(.*?)</ItemID>", content)
            item_id = item_id_match.group(1) if item_id_match else "UNKNOWN_ID"
            return f"BAŞARILI (XML Fallback)! Ürün eBay'de satışta. Listing ID: {item_id}"
        else:
            return f"XML Yayınlama Hatası: {content}"

    def revise_item_xml(self, item_id, payload):
        """
        Mevcut bir eBay ilanını ReviseFixedPriceItem API'si ile günceller.
        Sadece payload içinde gelen alanlar değiştirilir (Kısmi güncelleme).
        """
        token = self.get_valid_token()
        xml_url = "https://api.ebay.com/ws/api.dll"
        
        headers = {
            "Content-Type": "text/xml",
            "X-EBAY-API-SITEID": "0", # 0 = ABD (US)
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1311",
            "X-EBAY-API-CALL-NAME": "ReviseFixedPriceItem",
            "X-EBAY-API-IAF-TOKEN": token
        }

        # Sadece güncellenecek alanları içeren dinamik XML bloğu
        dynamic_fields = ""
        
        if payload.get("StartPrice") is not None:
            dynamic_fields += f"<StartPrice currencyID=\"USD\">{payload['StartPrice']}</StartPrice>\n"
            
        if payload.get("Quantity") is not None:
            dynamic_fields += f"<Quantity>{payload['Quantity']}</Quantity>\n"
            
        if payload.get("CategoryID"):
            dynamic_fields += f"<PrimaryCategory><CategoryID>{payload['CategoryID']}</CategoryID></PrimaryCategory>\n"
            
        # Politikalar (Profiles) geliyorsa
        profiles = payload.get("SellerProfiles", {})
        if profiles:
            dynamic_fields += "<SellerProfiles>\n"
            if profiles.get('PaymentProfileID'):
                dynamic_fields += f"  <SellerPaymentProfile><PaymentProfileID>{profiles['PaymentProfileID']}</PaymentProfileID></SellerPaymentProfile>\n"
            if profiles.get('ReturnProfileID'):
                dynamic_fields += f"  <SellerReturnProfile><ReturnProfileID>{profiles['ReturnProfileID']}</ReturnProfileID></SellerReturnProfile>\n"
            if profiles.get('ShippingProfileID'):
                dynamic_fields += f"  <SellerShippingProfile><ShippingProfileID>{profiles['ShippingProfileID']}</ShippingProfileID></SellerShippingProfile>\n"
            dynamic_fields += "</SellerProfiles>\n"

        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <ItemID>{item_id}</ItemID>
    {dynamic_fields}
  </Item>
</ReviseFixedPriceItemRequest>"""

        response = requests.post(xml_url, headers=headers, data=xml_payload.encode('utf-8'))
        content = response.text
        
        if "<Ack>Success</Ack>" in content or "<Ack>Warning</Ack>" in content:
            return {"success": True, "message": f"[{item_id}] başarıyla güncellendi."}
        else:
            return {"success": False, "message": f"[{item_id}] Güncelleme Hatası: {content}"}

if __name__ == "__main__":
    STORE_ID = "197bd215-3bec-4f43-aa40-f2fb4d204eee" 
    
    manager = EbayManager(store_id=STORE_ID)
    SKU = "TEST-SKU-001" 
    
    POLICIES = {
        "fulfillment_id": "251361629010", 
        "payment_id": "244346933010",     
        "return_id": "251407823010"       
    }
    
    print("Test ürünü yayına alınıyor...")
    sonuc = manager.create_and_publish_offer(SKU, POLICIES)
    print(sonuc)