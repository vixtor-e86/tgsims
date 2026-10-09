-- ==============================================================================
-- TGSIMS MIGRATION 015: EXPAND RENTAL DURATIONS (1, 90, 365 DAYS)
-- ==============================================================================
-- Description:
--   Expands rental_service_pricing check constraint to support 1-day, 90-day,
--   and 365-day (1 year) dedicated rental duration tiers alongside 3, 7, 14, and 30 days.
-- ==============================================================================

-- Drop the old 4-tier check constraint
ALTER TABLE public.rental_service_pricing 
DROP CONSTRAINT IF EXISTS rental_service_pricing_duration_days_check;

-- Add updated check constraint supporting all TextVerified rental tiers
ALTER TABLE public.rental_service_pricing 
ADD CONSTRAINT rental_service_pricing_duration_days_check 
CHECK (duration_days IN (1, 3, 7, 14, 30, 90, 365));

-- Seed default wholesale price entries for 1-day, 90-day, and 365-day tiers
INSERT INTO public.rental_service_pricing (service_code, service_name, duration_days, wholesale_price_usd)
VALUES
    ('allservices', 'Universal Number (All Services)', 1, 4.50),
    ('allservices', 'Universal Number (All Services)', 90, 28.90),
    ('allservices', 'Universal Number (All Services)', 365, 96.00),

    ('whatsapp', 'WhatsApp / Business', 1, 1.90),
    ('whatsapp', 'WhatsApp / Business', 90, 13.90),
    ('whatsapp', 'WhatsApp / Business', 365, 48.00),

    ('telegram', 'Telegram Messenger', 1, 2.80),
    ('telegram', 'Telegram Messenger', 90, 18.20),
    ('telegram', 'Telegram Messenger', 365, 62.40),

    ('google', 'Google / Gmail / YouTube', 1, 1.80),
    ('google', 'Google / Gmail / YouTube', 90, 10.30),
    ('google', 'Google / Gmail / YouTube', 365, 32.40),

    ('openai', 'OpenAI / ChatGPT', 1, 1.70),
    ('openai', 'OpenAI / ChatGPT', 90, 10.50),
    ('openai', 'OpenAI / ChatGPT', 365, 35.00),

    ('paypal', 'PayPal / Venmo', 1, 2.00),
    ('paypal', 'PayPal / Venmo', 90, 13.50),
    ('paypal', 'PayPal / Venmo', 365, 45.00),

    ('facebook', 'Facebook / Instagram / Threads', 1, 1.80),
    ('facebook', 'Facebook / Instagram / Threads', 90, 15.80),
    ('facebook', 'Facebook / Instagram / Threads', 365, 58.80),

    ('apple', 'Apple ID / iCloud', 1, 2.00),
    ('apple', 'Apple ID / iCloud', 90, 15.00),
    ('apple', 'Apple ID / iCloud', 365, 50.00),

    ('twitter', 'Twitter / X', 1, 1.60),
    ('twitter', 'Twitter / X', 90, 12.00),
    ('twitter', 'Twitter / X', 365, 40.00),

    ('microsoft', 'Microsoft / Outlook / Office', 1, 1.60),
    ('microsoft', 'Microsoft / Outlook / Office', 90, 11.50),
    ('microsoft', 'Microsoft / Outlook / Office', 365, 38.00)
ON CONFLICT (service_code, duration_days) 
DO UPDATE SET wholesale_price_usd = EXCLUDED.wholesale_price_usd;
