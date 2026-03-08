import requests
import base64
import json
import urllib.parse

import os
from dotenv import load_dotenv

load_dotenv()
# 1. Kendi anahtarlarını gir
app_id = os.environ.get("EBAY_APP_ID")
cert_id = os.environ.get("EBAY_CERT_ID")
ru_name = os.environ.get("EBAY_RU_NAME")

if not all([app_id, cert_id, ru_name]):
    print("HATA: .env dosyasında EBAY_APP_ID, EBAY_CERT_ID veya EBAY_RU_NAME eksik!")
    exit(1)

# 2. Adres çubuğundan aldığın % işaretli YENİ kodu buraya yapıştır
raw_auth_code = "v%5E1.1%23i%5E1%23f%5E0%23p%5E3%23I%5E3%23r%5E1%23t%5EUl41XzA6QTdDQTVBNDFBODFENzVENzQwQTk1RDc2Q0VBM0ZDOEJfMV8xI0VeMjYw"

# % işaretlerini orijinal ^ ve # karakterlerine otomatik çevirir
auth_code = urllib.parse.unquote(raw_auth_code)

def get_tokens():
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    
    auth_str = f"{app_id}:{cert_id}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {b64_auth}"
    }

    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": ru_name
    }

    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code == 200:
        print("BAŞARILI! JSON Çıktısı:\n")
        print(json.dumps(response.json(), indent=4))
    else:
        print("HATA OLUŞTU:")
        print(response.text)

if __name__ == "__main__":
    get_tokens()