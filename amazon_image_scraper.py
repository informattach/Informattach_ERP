import asyncio
import os
import random
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from database import db
from image_processor import ImageProcessor
from ebay_core import EbayManager

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

class AmazonImageScraper:
    def __init__(self):
        self.processor = ImageProcessor()
        # You need to specify a STORE_ID, assuming the primary store
        self.ebay = EbayManager(store_id="197bd215-3bec-4f43-aa40-f2fb4d204eee")
        
    async def __get_images_to_scrape(self, limit=50):
        """Returns ASINs that DO NOT have an image URL in product_media yet."""
        # Query core_products that lack media
        res = db.client.table("core_products").select("id, asin, product_media(media_url)").execute()
        
        needs_image = []
        for p in res.data:
            media = p.get("product_media", [])
            # media can be empty or a list of items where media_url is empty
            if not media or not isinstance(media, list) or len(media) == 0:
                needs_image.append(p)
            elif media and isinstance(media, list) and not media[0].get("media_url"):
                needs_image.append(p)
                
            if len(needs_image) >= limit:
                break
                
        return needs_image

    async def auto_scroll(self, page):
        for _ in range(3):
            await page.mouse.wheel(0, random.randint(300, 600))
            await asyncio.sleep(0.5)

    async def scrape_images(self, limit=10):
        items = await self.__get_images_to_scrape(limit=limit)
        if not items:
            print("📷 Tüm ürünlerin görseli tam, scraping'e gerek yok.")
            return

        print(f"🔍 Toplam {len(items)} ürün için görsel taranacak...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            for item in items:
                asin = item['asin']
                pid = item['id']
                url = f"https://www.amazon.com/dp/{asin}"
                
                print(f"[{asin}] Amazon sayfası yükleniyor: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await self.auto_scroll(page)
                    await asyncio.sleep(random.uniform(2, 4)) # Anti-bot delay
                    
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Try to extract the main hi-res landing image
                    img_el = soup.find("img", id="landingImage")
                    if not img_el:
                        # Fallback for dynamic/different templates
                        img_el = soup.find("img", id="imgBlkFront")
                        if not img_el:
                            print(f"[{asin}] HATA: landingImage bulunamadı.")
                            continue

                    # Extract the hi-res dynamic zoom URL if present, otherwise src
                    data_hi_res = img_el.get('data-old-hires') or img_el.get('data-a-dynamic-image')
                    image_url = ""
                    
                    if data_hi_res and "http" in data_hi_res:
                        import json
                        try:
                            # Parse a-dynamic-image json map and get the largest URL
                            img_dict = json.loads(data_hi_res)
                            image_url = list(img_dict.keys())[0] # Usually the first/biggest
                        except Exception:
                            # Regex fallback
                            import re
                            urls = re.findall(r'(https?://[^\s"]+)', data_hi_res)
                            if urls: image_url = urls[0]
                    
                    if not image_url or len(image_url) < 10:
                        image_url = img_el.get('src', "")

                    if "data:image" in image_url or not image_url:
                        print(f"[{asin}] Geçerli bir görsel URL çıkartılamadı.")
                        continue
                        
                    print(f"[{asin}] Görsel Bulundu: {image_url}")
                    
                    # Push through Image Processor (EXIF Strip, Watermark, JPEG)
                    print(f"[{asin}] Görsel işleniyor ve eBay EPS'ye doğrudan (Base64) yükleniyor...")
                    base64_img = self.processor.process_url_to_base64(image_url)
                    
                    if base64_img:
                        # Upload directly to eBay Site Hosted Pictures
                        ebay_result = self.ebay.upload_site_hosted_picture(base64_img, extension="jpg", pic_name=f"{asin}_img")
                        if ebay_result.get("success"):
                            public_url = ebay_result.get("url")
                            # Upsert into product_media to sync it to the local DB
                            db.client.table("product_media").upsert({
                                "product_id": pid,
                                "media_url": public_url,
                                "media_type": "image"
                            }).execute()
                            print(f"[{asin}] BAŞARILI: Görsel eBay'e yüklendi ve DB'ye bağlandı ({public_url})")
                        else:
                            print(f"[{asin}] eBay Upload Hatası: {ebay_result.get('message')}")
                    else:
                        print(f"[{asin}] İşleme hatası yaşandı (Processor boş döndü).")
                        
                except Exception as e:
                    print(f"[{asin}] Tarama/Bağlantı Hatası: {e}")
                    
            await browser.close()
            print("✅ Görsel çekme turu tamamlandı.")

if __name__ == "__main__":
    scraper = AmazonImageScraper()
    asyncio.run(scraper.scrape_images(limit=1))
