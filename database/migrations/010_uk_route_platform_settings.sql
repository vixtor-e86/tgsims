-- Migration 010: Add textverified_min_profit_usd column to public.platform_settings
-- Adds missing minimum guaranteed dollar profit floor for TextVerified

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'platform_settings' 
          AND column_name = 'textverified_min_profit_usd'
    ) THEN
        ALTER TABLE public.platform_settings 
        ADD COLUMN textverified_min_profit_usd NUMERIC(10, 2) DEFAULT 0.50;
    END IF;
END $$;

