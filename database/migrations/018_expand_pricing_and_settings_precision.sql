-- ==============================================================================
-- TGSIMS MIGRATION 018: EXPAND PRICING & SETTINGS CURRENCY PRECISION TO 4 DECIMALS
-- ==============================================================================
-- Description:
--   Expands monetary setting and price override columns from NUMERIC(10, 2)
--   to NUMERIC(16, 4). This allows sub-cent USD precision (up to 4 decimal places)
--   for reactivation fees (e.g. $0.8845), min profit floors ($0.2550), and service
--   price overrides without database rounding distortion.
-- ==============================================================================

-- 1. PLATFORM SETTINGS: Expand reactivation fee and profit floors to NUMERIC(16, 4)
ALTER TABLE public.platform_settings 
    ALTER COLUMN reactivation_fee_usd TYPE NUMERIC(16, 4),
    ALTER COLUMN fivesim_min_profit_usd TYPE NUMERIC(16, 4),
    ALTER COLUMN textverified_min_profit_usd TYPE NUMERIC(16, 4),
    ALTER COLUMN min_profit_usd TYPE NUMERIC(16, 4),
    ALTER COLUMN ngn_per_usd_rate TYPE NUMERIC(16, 4);

-- 2. SERVICE PRICE OVERRIDES: Expand override_price_usd to NUMERIC(16, 4)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'service_price_overrides') THEN
        ALTER TABLE public.service_price_overrides 
            ALTER COLUMN override_price_usd TYPE NUMERIC(16, 4);
    END IF;
END $$;

-- 3. RENTAL SERVICE PRICING: Expand wholesale and custom price to NUMERIC(16, 4)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'rental_service_pricing') THEN
        ALTER TABLE public.rental_service_pricing 
            ALTER COLUMN wholesale_price_usd TYPE NUMERIC(16, 4),
            ALTER COLUMN custom_price_usd TYPE NUMERIC(16, 4);
    END IF;
END $$;

COMMENT ON COLUMN public.platform_settings.reactivation_fee_usd IS 'Reactivation fee in USD (up to 4 decimal places, e.g. 0.8850)';
