-- ==============================================================================
-- TGSIMS MIGRATION 014: Korapay Dedicated Virtual Accounts Integration
-- ==============================================================================
-- This migration ensures the dedicated virtual accounts table supports both
-- Korapay and Squad providers, with provider tagging and indexing.
-- ==============================================================================

-- 1. Ensure provider column exists on squad_virtual_accounts
ALTER TABLE public.squad_virtual_accounts 
    ADD COLUMN IF NOT EXISTS provider VARCHAR(50) DEFAULT 'korapay';

-- 2. Index for provider lookups
CREATE INDEX IF NOT EXISTS idx_squad_va_provider ON public.squad_virtual_accounts(provider);

-- 3. Function to lookup user by virtual account number (updated to support both)
CREATE OR REPLACE FUNCTION public.get_user_by_virtual_account(p_account_number TEXT)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT user_id INTO v_user_id
    FROM public.squad_virtual_accounts
    WHERE account_number = p_account_number
      AND is_active = TRUE
    LIMIT 1;
    RETURN v_user_id;
END;
$$;
