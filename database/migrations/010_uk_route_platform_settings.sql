-- Migration 010: Add UK operator route column to public.platform_settings
-- Allows admin to configure clean physical UK carrier routes (EE, O2, Vodafone, Three, Route 34)

DO $$
BEGIN
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
