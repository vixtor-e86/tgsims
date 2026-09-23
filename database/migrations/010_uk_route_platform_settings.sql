-- Migration 010: Add missing columns to public.platform_settings
-- 1. textverified_min_profit_usd (Minimum guaranteed dollar profit floor for TextVerified)
-- 2. uk_operator_route (Clean physical carrier routing for UK numbers)

DO $$
BEGIN
    -- 1. textverified_min_profit_usd
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'platform_settings' 
          AND column_name = 'textverified_min_profit_usd'
    ) THEN
        ALTER TABLE public.platform_settings 
        ADD COLUMN textverified_min_profit_usd NUMERIC(10, 2) DEFAULT 0.50;
    END IF;

    -- 2. uk_operator_route
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'platform_settings' 
          AND column_name = 'uk_operator_route'
    ) THEN
        ALTER TABLE public.platform_settings 
        ADD COLUMN uk_operator_route TEXT DEFAULT 'clean_route';
    END IF;
END $$;

