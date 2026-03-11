import os
import json
from dotenv import load_dotenv
import google.generativeai as genai
from database import db

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

class CustomerServiceAgent:
    def __init__(self, model_name="gemini-2.5-flash-8b"):
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY .env dosyasında bulunamadı!")
            
        # Niyet Algılama (Intent Detection) için sistem yönergesi
        # Hızlı olduğu için 8b (veya normal flash) modeli idealdir.
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction="""You are a strict Intent Detection AI for an e-commerce customer service system. 
Your ONLY job is to read the customer's message and determine what kind of document they are requesting, if any.
You must output ONLY a valid JSON string with two keys:
1. "intent": Must be ONE of the following exact strings:
   - "SDS" (if they ask for Safety Data Sheet, MSDS, safety info, chemical makeup, hazards)
   - "MANUAL" (if they ask for a user manual, instructions, how to use it, assembly guide)
   - "WARRANTY" (if they ask for warranty information, guarantee terms, return policy related to warranty)
   - "CERTIFICATE" (if they ask for certifications like CE, FDA approval, ISO, authenticity certificate)
   - "EXPIRATION_DATE" (if they ask about expiration dates, shelf life, how long before it expires, use-by dates)
   - "OTHER" (if they are NOT asking for a document or expiration, but rather complaining, asking about shipping, pricing, etc)

2. "language": Detect the language of the user's message (e.g., "en", "tr", "es", "de"). Default to "en" if unsure.

Example Output:
{"intent": "SDS", "language": "en"}
"""
        )

        # Yanıt Oluşturma (Generation) için sistem yönergesi
        self.response_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction="""You are a highly professional, polite, and formal Customer Service Representative.
You must adopt 'Option 1' corporate tone: Formal, empathetic, yet direct and strictly adhering to store policies.
You are given a scenario where a customer requested a specific document (e.g., SDS, Manual, Warranty).
You will be provided with:
- The customer's message
- The document type they requested
- The language they used
- The URL to the document (if available in our database), OR "NOT_FOUND" if we don't have it.

Your task:
Write a reply to the customer in THEIR language.
1. Greet them professionally.
2. If the document URL is provided, give them the link clearly and explain that this is the document they requested.
3. If the document URL is "NOT_FOUND", apologize politely, state that the requested document is currently unavailable in our digital records, and assure them that their request has been forwarded to the relevant department for alternative assistance.
4. Close the message professionally (e.g., "Best regards, Customer Support Team").

Keep the message concise but extremely professional.
"""
        )

    def process_customer_message(self, isku: str, customer_message: str) -> dict:
        """
        1. Gelen mesajın NİYETİNİ (Intent) anlar (Hangi belge isteniyor?)
        2. İlgili ISKU'dan yola çıkarak Product ID'yi bulur.
        3. DB'den ilgili 'document_type' tabanlı dokümanları arar.
        4. Doküman varsa linkiyle, yoksa özür dileyen profesyonel bir metinle cevabı üretir.
        """
        result = {
            "isku": isku,
            "detected_intent": None,
            "detected_language": "en",
            "document_found": False,
            "generated_reply": "",
            "error": None
        }
        
        try:
            # ADIM 1: NİYET OKUMA (Intent Detection)
            response = self.model.generate_content(customer_message)
            raw_text = response.text.strip()
            
            # JSON formatını temizle (Eğer model ```json ... ``` tagleri döndürdüyse)
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.replace("```", "").strip()
                
            try:
                intent_data = json.loads(raw_text)
                detected_intent = intent_data.get("intent", "OTHER")
                detected_language = intent_data.get("language", "en")
            except json.JSONDecodeError:
                # Fallback in case the AI failed to output valid JSON
                detected_intent = "OTHER"
                detected_language = "en"
                
            result["detected_intent"] = detected_intent
            result["detected_language"] = detected_language
            
            # Eğer belge talebi yoksa, bu ajan işlem yapmaz (Normal müşteri hizmetlerine düşer)
            if detected_intent == "OTHER":
                result["generated_reply"] = "(Belge talebi algılanmadı. Standart destek akışına yönlendirilecek.)"
                return result

            # ADIM 2: ÜRÜNÜ VE BELGEYİ BULMA (EXPIRATION_DATE haricinde doc aranır)
            document_url = "NOT_FOUND"
            
            if detected_intent != "EXPIRATION_DATE":
                # 2.A - ISKU'dan Product ID'yi bul
                listing_res = db.client.table("listings").select("product_id").eq("channel_sku", isku).execute()
                if not listing_res.data:
                    raise ValueError(f"Sistemde {isku} ISKU koduna ait bir ürün bulunamadı.")
                    
                product_id = listing_res.data[0]["product_id"]
                
                # 2.B - Belgeyi (document_type = detected_intent) DB'de ara
                docs = db.get_product_documents(product_id=product_id, document_type=detected_intent)
                
                if docs:
                    # İlk bulduğu dokümanı (veya en güncelini) al
                    document_url = docs[0].get("document_url", "NOT_FOUND")
                    result["document_found"] = True

            # ADIM 3: YANIT METNİ OLUŞTURMA (Generation)
            if detected_intent == "EXPIRATION_DATE":
                policy_text = """
Hello,

Because our items are dispatched from high-turnover fulfillment centers, we cannot provide the exact expiration date for the specific unit shipping today.

However, our inventory operates under strict automated shelf-life rules:

Items are strictly monitored and must enter the facility with ample shelf life.
The system automatically removes any item from active inventory at least 50 days prior to its expiration date.
If the product takes time to consume (e.g., a 60-day supply of vitamins), that consumption period is added to the 50-day rule before removal.

This policy ensures that the item you receive will have sufficient time for regular use before expiring.

Best regards,
Informattach LLC
"""
                generation_prompt = f"""
Customer Message: "{customer_message}"
Language: {detected_language}
Instruction: The customer is asking about expiration/shelf life. Do NOT look for a document. Instead, beautifully translate the following official corporate policy into the customer's language ({detected_language}) and send it as the reply. Maintain the extremely polite and professional tone.
Policy to Translate:
{policy_text}
"""
            else:
                generation_prompt = f"""
Customer Message: "{customer_message}"
Requested Document Type: {detected_intent}
Language: {detected_language}
Document URL to Provide: {document_url}
"""
            reply_response = self.response_model.generate_content(generation_prompt)
            result["generated_reply"] = reply_response.text.strip()

        except Exception as e:
            result["error"] = str(e)
            
        return result

# Test için:
if __name__ == "__main__":
    agent = CustomerServiceAgent()
    
    test_message_1 = "Hi, I purchased this item but I lost the instructions. Can you send me the manual on how to assemble it?"
    print(f"--- TEST 1 (MANUAL) ---")
    res1 = agent.process_customer_message(isku="TEST1234", customer_message=test_message_1)
    print(json.dumps(res1, indent=2, ensure_ascii=False))
    
    test_message_2 = "Is there an MSDS sheet available for this chemical? My warehouse requires the safety data."
    print(f"\n--- TEST 2 (SDS) ---")
    res2 = agent.process_customer_message(isku="TEST1234", customer_message=test_message_2)
    print(json.dumps(res2, indent=2, ensure_ascii=False))

    test_message_3 = "Hola, compré estas vitaminas, pero necesito saber cuándo caducan. ¿Cuál es su fecha de vencimiento?"
    print(f"\n--- TEST 3 (EXPIRATION_DATE in Spanish) ---")
    res3 = agent.process_customer_message(isku="TEST1234", customer_message=test_message_3)
    print(json.dumps(res3, indent=2, ensure_ascii=False))
