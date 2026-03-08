-- draft tablosuna extra_data adında JSON formatında bir kolon ekliyoruz
-- Bu sayede Amazon'dan gelen standart dışı (Quantity, Priority, Comment vs.) ekstra verileri kaybetmeden tutabileceğiz

ALTER TABLE public.draft ADD COLUMN IF NOT EXISTS extra_data JSONB;
