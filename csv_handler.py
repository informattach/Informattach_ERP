import pandas as pd
import streamlit as st
import datetime
from database import db
import requests
import io
import os

class CSVHandler:
    """
    Generic CSV handler that formats and processes inputs for different marketplaces.
    Uses pandas to safely iterate and upsert database values via existing database.py models.
    """
    
    @staticmethod
    def _safe_float(val):
        try:
            if pd.isna(val):
               return 0.0
            return float(str(val).replace('$', '').replace(',', '').strip())
        except:
            return 0.0
            
    @staticmethod
    def _safe_int(val):
        try:
            if pd.isna(val):
                return 0
            return int(str(val).replace(',', '').strip())
        except:
            return 0

    @classmethod
    def process_csv(cls, dataframe: pd.DataFrame, platform: str) -> dict:
        """
        Main router for processing CSVs based on platform choice.
        Returns a dict with success count and error info.
        """
        if platform == "eBay":
            return cls._process_ebay(dataframe)
        elif platform == "Easync":
            # Easync uses the existing logic in db.import_easync_data.
            # We can route it directly there.
            return db.import_easync_data(dataframe)
        else:
            raise ValueError(f"Platform '{platform}' is missing a specific processing profile.")

    @classmethod
    def _process_ebay(cls, df: pd.DataFrame) -> dict:
        """
        Process eBay 'Active Listings' or 'File Exchange' format.
        Focuses ONLY on updating the listings table to prevent creating garbage core_products.
        """
        df = df.fillna('')
        
        # eBay columns can vary slightly between "Active Listings" report and "File Exchange" report.
        # We handle both generic headers by looking for the required keys.
        
        success_count = 0
        error_count = 0
        
        # Mapping possible headers
        sku_col = next((c for c in df.columns if 'Custom label' in c or c == 'CustomLabel'), None)
        item_id_col = next((c for c in df.columns if 'Item number' in c or 'ItemID' in c), None)
        price_col = next((c for c in df.columns if 'Current price' in c or 'Start price' in c or 'StartPrice' in c), None)
        qty_col = next((c for c in df.columns if 'Available quantity' in c or 'Quantity' in c), None)
        sold_col = next((c for c in df.columns if 'Sold quantity' in c), None)

        if not sku_col or not price_col:
            raise ValueError("eBay CSV format is missing required columns (SKU or Price).")

        # Fetch current listings from DB to know the IDs for upserting
        list_data = db.client.table('listings').select('id, product_id, store_id, channel_sku').execute().data
        
        # Create a mapping of channel_sku -> listing db ID
        sku_to_listing = {l['channel_sku']: l for l in list_data if l['channel_sku']}
        
        updates = []
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        for index, row in df.iterrows():
            sku = str(row.get(sku_col, '')).strip()
            if not sku or sku not in sku_to_listing:
                # If SKU is empty or not in our DB, we skip it. We don't want to create orphan products.
                error_count += 1
                continue
                
            db_listing = sku_to_listing[sku]
            
            price = cls._safe_float(row.get(price_col, 0))
            qty = cls._safe_int(row.get(qty_col, 0))
            
            payload = {
                'id': db_listing['id'],
                'listed_price': price,
                'quantity': qty,
                'updated_at': now_str
            }
            
            # Additional Optional mappings
            if item_id_col:
                item_id = str(row.get(item_id_col, '')).strip()
                if item_id:
                    payload['channel_item_id'] = item_id
            
            if sold_col:
                sold_qty = cls._safe_int(row.get(sold_col, 0))
                payload['sold_quantity'] = sold_qty
                
            updates.append(payload)
            success_count += 1

        # Bulk upsert the updates
        if updates:
            chunk_size = 500
            for i in range(0, len(updates), chunk_size):
                try:
                    db.client.table('listings').upsert(updates[i:i+chunk_size]).execute()
                except Exception as e:
                    print(f"Error updating listings chunk: {e}")
                    error_count += len(updates[i:i+chunk_size])

        return {"success": success_count, "errors": error_count}

    @classmethod
    def fetch_from_url(cls, url: str) -> pd.DataFrame:
        """
        Helper method to download a CSV from a provided static URL.
        """
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        content = response.content.decode('utf-8')
        if url.endswith('.csv'):
            return pd.read_csv(io.StringIO(content))
        else:
            return pd.read_excel(io.BytesIO(response.content))
