-- Amazon ASIN Scraper Draft Table Schema
CREATE TABLE IF NOT EXISTS public.draft (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    product_id TEXT UNIQUE NOT NULL, -- ASIN
    title TEXT,
    price NUMERIC,
    original_price NUMERIC,
    discount_percentage TEXT,
    deal_duration TEXT,
    merchant_name TEXT,
    is_amazon_selling BOOLEAN DEFAULT FALSE,
    stock_quantity TEXT,
    delivery_date TEXT,
    needs_sync BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trigger to update updated_at automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_draft_updated_at
BEFORE UPDATE ON public.draft
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
