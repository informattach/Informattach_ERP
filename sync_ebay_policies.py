import os
import requests
from dotenv import load_dotenv
from ebay_core import EbayManager

load_dotenv()

def fetch_business_policies():
    """
    Fetches the eBay Account Business Policies (Shipping, Return, Payment)
    without modifying any live data.
    """
    # Assuming the first active store or providing the known store ID. 
    # Hardcoding the store ID exactly as it is in `app.py` debugger for consistency
    store_id = "197bd215-3bec-4f43-aa40-f2fb4d204eee"
    
    print("eBay'den mağazanıza ait İş Politikaları (Business Policies) çekiliyor...\n")
    manager = EbayManager(store_id=store_id)
    token = manager.get_valid_token()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    base_url = "https://api.ebay.com/sell/account/v1"
    marketplace_id = "EBAY_US"

    endpoints = {
        "📦 Kargo Politikaları (Fulfillment/Shipping)": f"{base_url}/fulfillment_policy?marketplace_id={marketplace_id}",
        "↩️ İade Politikaları (Return)": f"{base_url}/return_policy?marketplace_id={marketplace_id}",
        "💳 Ödeme Politikaları (Payment)": f"{base_url}/payment_policy?marketplace_id={marketplace_id}"
    }

    results = {}

    for name, url in endpoints.items():
        print(f"Çekiliyor: {name}")
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            
            # Print cleanly
            policies = []
            if "fulfillmentPolicies" in data:
                policies = data["fulfillmentPolicies"]
            elif "returnPolicies" in data:
                policies = data["returnPolicies"]
            elif "paymentPolicies" in data:
                policies = data["paymentPolicies"]
            
            total = data.get('total', len(policies))
            print(f"✅ {total} adet politika bulundu.")
            
            for pol in policies:
                pol_name = pol.get('name', 'Bilinmeyen İsim')
                pol_id = pol.get('fulfillmentPolicyId') or pol.get('returnPolicyId') or pol.get('paymentPolicyId')
                print(f"   -> İsim: {pol_name:<30} | ID: {pol_id}")
            
            results[name] = policies
        else:
            print(f"❌ Hata: API yanıtı başarısız ({response.status_code}) - {response.text}")
        print("-" * 60)

if __name__ == "__main__":
    fetch_business_policies()
