import os
import json
import requests
from typing import List, Dict, Any, Optional

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class GeminiAssistant:
    def __init__(self):
        # API anahtarını st.secrets veya çevresel değişkenlerden alıyoruz.
        try:
            import streamlit as st
            self.api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
            self.claude_key = st.secrets.get("CLAUDE_API_KEY", os.environ.get("CLAUDE_API_KEY", ""))
        except Exception:
            self.api_key = os.environ.get("GEMINI_API_KEY", "")
            self.claude_key = os.environ.get("CLAUDE_API_KEY", "")
            
        if self.api_key and GEMINI_AVAILABLE:
            self.client = genai.Client(api_key=self.api_key)
            
        # Kullanıcının Ultra abonelikle eriştiği model adı "Gemini 3.1 Pro (High)" olarak
        # sistem tarafında henüz gemini-1.5-pro / gemini-2.0-pro alias'larına denk gelebilir, 
        # ancak API tarafındaki "gemini-1.5-pro" en gelişmiş yetenekleri sunan güncel stable string'dir.
        # İlerde 3.1_pro eklendiğinde string burdan değiştirilebilir.
        self.primary_model_name = "gemini-2.5-flash" # Fallback to stable Pro model
        self.fallback_model_name = "claude-3-5-sonnet-20241022"
        
        # System Instructions to guide the AI
        self.system_instruction = """
        Sen uzman bir E-ticaret ve SEO danışmanısın. Amacın, verilen ürün özelliklerini, başlığı ve fotoğrafları analiz ederek,
        eBay ABD (eBay.com) platformuna %100 uyumlu, yüksek dönüşüm (conversion) odaklı, profesyonel HTML ürün açıklamaları oluşturmaktır.

        KURALLAR:
        1. Amazon'a ait ŞU KELİMELERİ ASLA KULLANMA: "Amazon", "Prime", "FBA", "Subscribe and Save", "Alexa", "Kindle", "A-to-z Guarantee".
        2. Kargo vaatlerinde bulunma (örn: "2 günde kargo" deme). Kargo durumunu eBay politikaları yönetecek.
        3. Müşteriye garanti veya dışarıdan iade süreci vaat etme, sadece "Lütfen eBay İade Politikamıza bakın" tarzı genel ifadeler kur.
        4. Çıktı SADECE ve SADECE saf HTML kodu olmalıdır. Markdown (```html ... ```) İÇERMEMELİDİR.
        5. Modern, temiz, mobil uyumlu (responsive) CSS framework'suz düz HTML (inline css kabul edilebilir) kullan.
        6. Ürünün en güçlü 3 özelliğini (bullet points) vurgula.
        """

    def generate_ebay_html(self, title: str, features: List[str] = None, image_urls: List[str] = None) -> str:
        """
        Ürün bilgilerini kullanarak Gemini (başarısız olursa Claude) üzerinden eBay HTML açıklaması üretir.
        """
        prompt = self._build_prompt(title, features)
        
        if self.api_key and GEMINI_AVAILABLE:
            try:
                print(f"[Gemini] {self.primary_model_name} modeli ile HTML üretiliyor...")
                html_content = self._call_gemini(prompt)
                
                # Modeli test edip markdown wrapper'ını temizle
                html_content = html_content.strip()
                if html_content.startswith("```html"):
                    html_content = html_content[7:]
                if html_content.endswith("```"):
                    html_content = html_content[:-3]
                    
                return html_content.strip()
                
            except Exception as e:
                print(f"[Gemini Hatası] {e}. Claude 3.5 Sonnet'e düşülüyor (Fallback)...")
                if self.claude_key:
                    return self._call_claude(prompt)
                raise Exception("Hem Gemini hem de Claude fallback başarısız oldu veya API anahtarı eksik.")
        
        elif self.claude_key:
            print("[Sistem] Gemini kurulamadı, doğrudan Claude çağrılıyor...")
            return self._call_claude(prompt)
            
        else:
            raise Exception("API Key bulunamadı. Lütfen GEMINI_API_KEY veya CLAUDE_API_KEY sağlayın.")

    def _build_prompt(self, title: str, features: List[str]) -> str:
        f_text = "\n".join(features) if features else "Özellik belirtilmedi."
        return f"""
        Lütfen aşağıdaki ürün için satışı artıracak profesyonel bir eBay HTML açıklaması yaz.
        Sistem kurallarına (Amazon kelimelerini yasakla vb.) kesinlikle uy.

        Ürün Başlığı: {title}
        Mevcut Bilinen Özellikler & Açıklamalar:
        {f_text}

        Çıktıyı başlıklar (h2, h3), listeler (ul, li) ve kalın metinler (strong) ile zenginleştir.
        Sadece HTML kodunu döndür, başka hiçbir açıklama veya yorum ekleme.
        """

    def _call_gemini(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.primary_model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
            ),
        )
        return response.text

    def _call_claude(self, prompt: str) -> str:
        headers = {
            "x-api-key": self.claude_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": self.fallback_model_name,
            "max_tokens": 2048,
            "system": self.system_instruction,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            # Claude'un döndürdüğü metni parse et
            content = data.get("content", [])
            if content and len(content) > 0:
                html_content = content[0].get("text", "").strip()
                
                # Tıpkı Gemini'de olduğu gibi Markdown temizliği yap
                if html_content.startswith("```html"):
                    html_content = html_content[7:]
                if html_content.endswith("```"):
                    html_content = html_content[:-3]
                    
                return html_content.strip()
            return ""
        else:
            raise Exception(f"Claude API Hatası ({response.status_code}): {response.text}")

if __name__ == "__main__":
    # Test
    print("Test çalıştırılıyor...")
    assistant = GeminiAssistant()
    
    test_title = "Waterproof Hiking Boots Men's Durable Outdoor Trail Shoes"
    test_features = [
        "Color: Brown and Black",
        "Material: Leather and Breathable Mesh",
        "Sole: Anti-slip rubber outsoles",
        "Extra: Orthopedic insoles for long hikes",
        "Fast shipping with Prime"  # Bu cümlenin sistem tarafından elenmesi beklenir.
    ]
    
    try:
        html_out = assistant.generate_ebay_html(test_title, test_features)
        print("BAŞARILI! Üretilen HTML:")
        print("-" * 50)
        print(html_out)
        print("-" * 50)
    except Exception as e:
        print(f"Test Başarısız: {e}")
