-- ==============================================================================
-- TGSIMS MIGRATION 012: DEDICATED RENTAL PRICING & PROFIT CONTROL
-- ==============================================================================
-- Description:
--   Stores live wholesale costs and custom selling price overrides for dedicated
--   virtual number rentals across all duration tiers (3, 7, 14, and 30 days).
--   Wholesale costs can be synchronized directly from the TextVerified API.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.rental_service_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_code VARCHAR(50) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    duration_days INT NOT NULL CHECK (duration_days IN (3, 7, 14, 30)),
    wholesale_price_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    custom_price_usd NUMERIC(10, 2) DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT uq_rental_service_duration UNIQUE (service_code, duration_days)
);

-- Index for fast lookup by service and duration
CREATE INDEX IF NOT EXISTS idx_rental_pricing_lookup 
ON public.rental_service_pricing (service_code, duration_days);

-- Enable RLS
ALTER TABLE public.rental_service_pricing ENABLE ROW LEVEL SECURITY;

-- Allow public read of active rental pricing (for frontend and API)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'rental_service_pricing' AND policyname = 'Allow public read access to rental pricing'
    ) THEN
        CREATE POLICY "Allow public read access to rental pricing" 
        ON public.rental_service_pricing FOR SELECT 
        USING (true);
    END IF;
END $$;

-- Allow service_role / admin full access
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'rental_service_pricing' AND policyname = 'Allow full access for service_role'
    ) THEN
        CREATE POLICY "Allow full access for service_role" 
        ON public.rental_service_pricing FOR ALL 
        USING (true)
        WITH CHECK (true);
    END IF;
END $$;

-- Seed initial default rows for the 10 core rental services
INSERT INTO public.rental_service_pricing (service_code, service_name, duration_days, wholesale_price_usd)
VALUES
    -- Universal (All Services)
    ('allservices', 'Universal Number (All Services)', 3, 6.00),
    ('allservices', 'Universal Number (All Services)', 7, 7.00),
    ('allservices', 'Universal Number (All Services)', 14, 8.00),
    ('allservices', 'Universal Number (All Services)', 30, 10.00),
    -- WhatsApp
    ('whatsapp', 'WhatsApp / Business', 3, 2.40),
    ('whatsapp', 'WhatsApp / Business', 7, 3.00),
    ('whatsapp', 'WhatsApp / Business', 14, 4.00),
    ('whatsapp', 'WhatsApp / Business', 30, 4.80),
    -- Telegram
    ('telegram', 'Telegram Messenger', 3, 3.00),
    ('telegram', 'Telegram Messenger', 7, 3.50),
    ('telegram', 'Telegram Messenger', 14, 5.00),
    ('telegram', 'Telegram Messenger', 30, 6.40),
    -- Google
    ('google', 'Google / Gmail / YouTube', 3, 2.20),
    ('google', 'Google / Gmail / YouTube', 7, 2.40),
    ('google', 'Google / Gmail / YouTube', 14, 3.00),
    ('google', 'Google / Gmail / YouTube', 30, 3.60),
    -- OpenAI
    ('openai', 'OpenAI / ChatGPT', 3, 1.90),
    ('openai', 'OpenAI / ChatGPT', 7, 2.00),
    ('openai', 'OpenAI / ChatGPT', 14, 2.80),
    ('openai', 'OpenAI / ChatGPT', 30, 3.60),
    -- PayPal
    ('paypal', 'PayPal / Venmo', 3, 2.40),
    ('paypal', 'PayPal / Venmo', 7, 2.90),
    ('paypal', 'PayPal / Venmo', 14, 3.80),
    ('paypal', 'PayPal / Venmo', 30, 4.60),
    -- Facebook
    ('facebook', 'Facebook / Instagram / Threads', 3, 2.00),
    ('facebook', 'Facebook / Instagram / Threads', 7, 2.60),
    ('facebook', 'Facebook / Instagram / Threads', 14, 3.50),
    ('facebook', 'Facebook / Instagram / Threads', 30, 4.20),
    -- Apple
    ('apple', 'Apple ID / iCloud', 3, 1.90),
    ('apple', 'Apple ID / iCloud', 7, 3.00),
    ('apple', 'Apple ID / iCloud', 14, 4.00),
    ('apple', 'Apple ID / iCloud', 30, 5.00),
    -- Twitter
    ('twitter', 'Twitter / X', 3, 1.90),
    ('twitter', 'Twitter / X', 7, 2.50),
    ('twitter', 'Twitter / X', 14, 3.20),
    ('twitter', 'Twitter / X', 30, 4.00),
    -- Microsoft
    ('microsoft', 'Microsoft / Outlook / Office', 3, 1.90),
    ('microsoft', 'Microsoft / Outlook / Office', 7, 2.40),
    ('microsoft', 'Microsoft / Outlook / Office', 14, 3.20),
    ('microsoft', 'Microsoft / Outlook / Office', 30, 3.80)
ON CONFLICT (service_code, duration_days) DO NOTHING;
