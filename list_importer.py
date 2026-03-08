import asyncio
import os
import sys
import re
import random
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_KEY is missing in environment variables.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stealth settings
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

def extract_asin_from_url(url: str) -> str:
    """Extracts ASIN from Amazon URL if possible."""
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if match: return match.group(1)
    match = re.search(r"/gp/product/([A-Z0-9]{10})", url)
    if match: return match.group(1)
    match = re.search(r"([A-Z0-9]{10})", url) # Fallback heuristic
    return match.group(0) if match else None

async def random_sleep(min_ms=1000, max_ms=3000):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)

async def auto_scroll(page):
    """Slowly scroll down to load lazy images and content."""
    for _ in range(5):
        await page.mouse.wheel(0, random.randint(300, 600))
        await random_sleep(200, 500)

async def extract_product_details(page, url: str) -> dict:
    """Visits a detail page and extracts all necessary fields."""
    print(f"  -> Visiting detail page: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await auto_scroll(page)
    
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    data = {"url": url}
    
    # 1. ASIN
    # Sometimes it's in a hidden input
    asin_input = soup.find("input", {"id": "ASIN"}) or soup.find("input", {"name": "ASIN"})
    if asin_input and asin_input.get("value"):
        data["product_id"] = asin_input.get("value")
    else:
        data["product_id"] = extract_asin_from_url(url)
        
    print(f"  -> ASIN found: {data.get('product_id')}")
    
    # 2. Title
    title_el = soup.find(id="productTitle")
    data["title"] = title_el.get_text(strip=True) if title_el else "Unknown Title"
    
    # 3. Price (Mandatory)
    price = None
    
    # Try various common Amazon price selectors
    price_selectors = [
        ".priceToPay span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price span.a-offscreen",
        "#corePrice_desktop .a-price span.a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price span.a-offscreen"
    ]
    
    for selector in price_selectors:
        price_els = soup.select(selector)
        for p_el in price_els:
            pt = p_el.get_text(strip=True).replace("$", "").replace(",", "")
            try:
                # some elements might have a space or other chars, extract first valid float
                match = re.search(r"(\d+\.\d+|\d+)", pt)
                if match:
                    price = float(match.group(1))
                    break
            except Exception: pass
        if price is not None:
            break

    data["price"] = price
    
    if data["price"] is None:
        print(f"  -> [SKIPPING] No price found for {data.get('product_id')} - {data.get('title')[:30]}")
        # print some debug
        debug_price = soup.select_one("#corePrice_desktop, #corePriceDisplay_desktop_feature_div")
        if debug_price:
            print(f"  -> Debug HTML snippet: {debug_price.get_text(separator=' ', strip=True)[:150]}")
        return None  # Price is mandatory

    # 4. Original Price & Discount
    # Typically <span class="a-text-strike">$...</span>
    strike_el = soup.select_one(".a-text-strike")
    if strike_el:
        orig = strike_el.get_text(strip=True).replace("$", "").replace(",", "")
        try:
            data["original_price"] = float(orig)
            if data["original_price"] > 0 and data["price"] < data["original_price"]:
                disc = ((data["original_price"] - data["price"]) / data["original_price"]) * 100
                data["discount_percentage"] = f"%{round(disc)}"
        except: pass
        
    if "discount_percentage" not in data:
        savings_el = soup.select_one(".savingsPercentage")
        if savings_el:
            data["discount_percentage"] = savings_el.get_text(strip=True)

    # 5. Merchant Name & Amazon Selling
    merchant_el = soup.select_one("#merchant-info, #tabular-buybox-text, .tabular-buybox-text")
    merchant_name = "Unknown Details"
    if merchant_el:
        merchant_name = merchant_el.get_text(separator=' ', strip=True)
        
    data["merchant_name"] = merchant_name[:200]
    data["is_amazon_selling"] = "Amazon" in merchant_name or "Amazon.com" in merchant_name
    
    # 6. Deal Duration (Ends in ...)
    deal_timer = soup.select_one("#deal_expiry_timer, .deal-timer, .a-size-base.a-color-price")
    if deal_timer and "ends in" in deal_timer.get_text(strip=True).lower():
        data["deal_duration"] = deal_timer.get_text(strip=True)
        
    # 7. Stock Quantity
    availability_el = soup.select_one("#availability")
    if availability_el:
        avail_text = availability_el.get_text(strip=True)
        data["stock_quantity"] = avail_text[:100]
        # Try to parse exact quantity if "only X left"
        match = re.search(r"only (\d+) left", avail_text.lower())
        if match:
            data["stock_quantity"] = int(match.group(1))
            
    # 8. Delivery Date
    delivery_el = soup.select_one("#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE")
    if delivery_el:
        data["delivery_date"] = delivery_el.get_text(strip=True)[:100]

    data["needs_sync"] = True
    
    return data

async def run_scraper(start_url: str):
    print(f"Target URL: {start_url}")
    print("Launching Chromium (Headed mode for bot evasion)...")
    
    async with async_playwright() as p:
        # We use headed mode to reduce the chances of being blocked by Amazon's automated systems.
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True
        )
        
        # Adding anti-bot evasion scripts
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
            """
        )

        page = await context.new_page()
        
        print(f"Navigating to {start_url} ...")
        await page.goto(start_url, timeout=60000)
        await random_sleep(3000, 5000)
        await auto_scroll(page)
        
        # Determine if we are on a list page (Deals, Search) or a detail page
        # Let's extract all possible product links if it's a list page
        
        product_links = []
        
        # Generic product link selector (Deals, Search results, etc)
        # Search for links containing /dp/ or /gp/product/
        elements = await page.locator("a").all()
        for element in elements:
            href = await element.get_attribute("href")
            if href and ("/dp/" in href or "/gp/product/" in href):
                # Clean URL (remove ref= and other trackers)
                clean_url = href.split("?")[0].split("ref=")[0]
                full_url = urljoin(start_url, clean_url)
                if full_url not in product_links:
                    product_links.append(full_url)
                    
        # Filter to only main product pages
        product_links = [l for l in product_links if "/dp/" in l or "/gp/product/" in l]
        
        if not product_links and ("/dp/" in start_url or "/gp/product/" in start_url):
            print("Seems like start URL is a detail page already.")
            product_links = [start_url]
            
        print(f"Found {len(product_links)} potential product links on the page.")
        
        valid_items_added = 0
        
        for link in product_links[:15]:  # Limit to 15 for demonstration
            # ASIN Check against draft table to prevent duplicates
            possible_asin = extract_asin_from_url(link)
            if possible_asin:
                try:
                    existing = supabase.table("draft").select("id").eq("product_id", possible_asin).limit(1).execute()
                    if existing.data:
                        print(f"  [SKIPPED] ASIN {possible_asin} already exists in the draft list. Skipping full scan.")
                        continue
                except Exception:
                    pass
                    
            # Visit detail page
            await random_sleep(2000, 4000)
            
            try:
                product_data = await extract_product_details(page, link)
                if not product_data:
                    continue # Skipped (likely no price)
                    
                print(f"  [SUCCESS] Scraped info for {product_data['product_id']} | Price: ${product_data['price']} | Title: {product_data['title'][:30]}...")
                
                # Insert into Supabase `draft` table
                del product_data["url"] # Don't insert URL column if not in schema usually
                
                try:
                    res = supabase.table("draft").upsert(product_data, on_conflict="product_id").execute()
                    print(f"  -> DB Insert/Update Success.")
                    valid_items_added += 1
                except Exception as db_err:
                    print(f"  -> Supabase Insert Error: {db_err}")
                
            except Exception as e:
                print(f"  [ERROR] Failed to process {link}: {e}")
                
        print(f"Scraping finished. Successfully added {valid_items_added} items to the draft table.")
        await browser.close()


if __name__ == "__main__":
    url = ""
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Please enter the Amazon List/Search/Deals URL: ")
        
    if not url.strip():
        url = "https://www.amazon.com/deals"
        print("No URL provided. Defaulting to Today's Deals.")
        
    asyncio.run(run_scraper(url))
