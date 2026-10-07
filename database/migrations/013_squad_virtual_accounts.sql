-- ==============================================================================
-- TGSIMS MIGRATION 013: Squad Payment Gateway & Dedicated Virtual Accounts
-- ==============================================================================
-- Adds tables for Squad dedicated virtual accounts (permanent per-user bank
-- accounts that auto-credit user wallets on incoming transfers), plus updates
-- wallet_transactions to support the new payment channels.
-- ==============================================================================

-- 1. SQUAD DEDICATED VIRTUAL ACCOUNTS TABLE
--    Each user gets ONE permanent virtual account number from Squad.
--    Incoming transfers auto-credit their Tgsims wallet.
CREATE TABLE IF NOT EXISTS public.squad_virtual_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    customer_identifier VARCHAR(50) UNIQUE NOT NULL,
    account_number VARCHAR(20) UNIQUE,
    account_name VARCHAR(100),
    bank_name VARCHAR(100),
    bank_code VARCHAR(10),
    bvn VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    squad_response JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_squad_va_user_id ON public.squad_virtual_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_squad_va_account_number ON public.squad_virtual_accounts(account_number);
CREATE INDEX IF NOT EXISTS idx_squad_va_customer_id ON public.squad_virtual_accounts(customer_identifier);

-- 2. Add payment_channel column to wallet_transactions if not exists
--    (supports: card, crypto_cryptomus, crypto_nowpayments, bank_transfer,
--     dedicated_virtual_account, manual, referral, bonus)
ALTER TABLE public.wallet_transactions
    ADD COLUMN IF NOT EXISTS payment_channel VARCHAR(50) DEFAULT 'manual';

ALTER TABLE public.wallet_transactions
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE public.wallet_transactions
    ADD COLUMN IF NOT EXISTS admin_notes TEXT;

-- Index for fast payment channel lookups
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_payment_channel ON public.wallet_transactions(payment_channel);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON public.wallet_transactions(status);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_meta_payment_id ON public.wallet_transactions ((metadata->>'payment_id'));

-- 3. RLS for squad_virtual_accounts
ALTER TABLE public.squad_virtual_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own virtual account" ON public.squad_virtual_accounts;
CREATE POLICY "Users can view own virtual account"
    ON public.squad_virtual_accounts FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Service role can do all operations (for server-side crediting)
DROP POLICY IF EXISTS "Service role full access to squad_va" ON public.squad_virtual_accounts;
CREATE POLICY "Service role full access to squad_va"
    ON public.squad_virtual_accounts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 4. Updated_at trigger for squad_virtual_accounts
DROP TRIGGER IF EXISTS tr_squad_va_updated_at ON public.squad_virtual_accounts;
CREATE TRIGGER tr_squad_va_updated_at
    BEFORE UPDATE ON public.squad_virtual_accounts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 5. Function: lookup user_id from virtual account number (for webhook processing)
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

-- 6. Function: check if a wallet transaction reference already exists (idempotency)
CREATE OR REPLACE FUNCTION public.transaction_reference_exists(p_reference TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.wallet_transactions WHERE reference = p_reference
    );
END;
$$;
