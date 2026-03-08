import requests
import base64
import time
from datetime import datetime, timedelta

class EbayAuth:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"

    def get_valid_token(self, store_id):
        # 1. Mağaza bilgilerini çek
        response = self.supabase.table("stores").select("api_config").eq("id", store_id).single().execute()
        config = response.data['api_config']

        # 2. Token geçerliliğini kontrol et (5 dk tolerans payı bırak)
        expires_at = datetime.fromisoformat(config.get('expires_at', '2000-01-01'))
        if datetime.now() < (expires_at - timedelta(minutes=5)):
            return config['access_token']

        # 3. Token süresi dolmuşsa yenile (Refresh Token kullanarak)
        return self._refresh_access_token(store_id, config)

    def _refresh_access_token(self, store_id, config):
        app_id = config['ebay_app_id']
        cert_id = config['ebay_cert_id']
        refresh_token = config['refresh_token']
        
        # Basic Auth Header Hazırla
        auth_str = f"{app_id}:{cert_id}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {b64_auth}"
        }

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.marketing"
        }

        res = requests.post(self.auth_url, headers=headers, data=payload)
        
        if res.status_code == 200:
            data = res.json()
            new_access_token = data['access_token']
            # Yeni süreyi hesapla
            new_expiry = (datetime.now() + timedelta(seconds=data['expires_in'])).isoformat()
            
            # 4. Veritabanını Güncelle
            config['access_token'] = new_access_token
            config['expires_at'] = new_expiry
            
            self.supabase.table("stores").update({"api_config": config}).eq("id", store_id).execute()
            return new_access_token
        else:
            raise Exception(f"eBay Token yenileme hatası: {res.text}")