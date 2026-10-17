-- ==============================================================================
-- TGSIMS MIGRATION 016: Add override_price_ngn column to service_price_overrides
-- ==============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'service_price_overrides' 
          AND column_name = 'override_price_ngn'
    ) THEN
        ALTER TABLE public.service_price_overrides 
        ADD COLUMN override_price_ngn NUMERIC(12, 2);
    END IF;
END $$;

COMMENT ON COLUMN public.service_price_overrides.override_price_ngn IS 'Optional manual override price denominated in NGN (Nigerian Naira)';
