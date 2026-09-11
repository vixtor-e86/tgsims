-- ==============================================================================
-- TGSIMS MIGRATION 003: Admin Pricing, Multi-Channel Verification & Auditing
-- ==============================================================================

-- 1. ENHANCE PLATFORM SETTINGS FOR DYNAMIC MARGINS & FX RATE
CREATE TABLE IF NOT EXISTS public.platform_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ngn_per_usd_rate NUMERIC(10, 2) DEFAULT 1600.00,
    fivesim_markup_percent NUMERIC(5, 2) DEFAULT 30.00,
    fivesim_min_profit_usd NUMERIC(10, 2) DEFAULT 0.30,
    textverified_markup_percent NUMERIC(5, 2) DEFAULT 25.00,
    reactivation_fee_usd NUMERIC(10, 2) DEFAULT 1.00,
    crypto_deposit_address TEXT DEFAULT '',
    squad_enabled BOOLEAN DEFAULT TRUE,
    crypto_enabled BOOLEAN DEFAULT TRUE,
    manual_bank_details TEXT DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Ensure columns exist if table was previously created with fewer fields
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'ngn_per_usd_rate') THEN
        ALTER TABLE public.platform_settings ADD COLUMN ngn_per_usd_rate NUMERIC(10, 2) DEFAULT 1600.00;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'fivesim_markup_percent') THEN
        ALTER TABLE public.platform_settings ADD COLUMN fivesim_markup_percent NUMERIC(5, 2) DEFAULT 30.00;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'fivesim_min_profit_usd') THEN
        ALTER TABLE public.platform_settings ADD COLUMN fivesim_min_profit_usd NUMERIC(10, 2) DEFAULT 0.30;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'textverified_markup_percent') THEN
        ALTER TABLE public.platform_settings ADD COLUMN textverified_markup_percent NUMERIC(5, 2) DEFAULT 25.00;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'reactivation_fee_usd') THEN
        ALTER TABLE public.platform_settings ADD COLUMN reactivation_fee_usd NUMERIC(10, 2) DEFAULT 1.00;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'crypto_deposit_address') THEN
        ALTER TABLE public.platform_settings ADD COLUMN crypto_deposit_address TEXT DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'squad_enabled') THEN
        ALTER TABLE public.platform_settings ADD COLUMN squad_enabled BOOLEAN DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'crypto_enabled') THEN
        ALTER TABLE public.platform_settings ADD COLUMN crypto_enabled BOOLEAN DEFAULT TRUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'platform_settings' AND column_name = 'manual_bank_details') THEN
        ALTER TABLE public.platform_settings ADD COLUMN manual_bank_details TEXT DEFAULT '';
    END IF;
END $$;

-- Insert default row if table is empty
INSERT INTO public.platform_settings (
    ngn_per_usd_rate,
    fivesim_markup_percent,
    fivesim_min_profit_usd,
    textverified_markup_percent,
    reactivation_fee_usd,
    squad_enabled,
    crypto_enabled
)
SELECT 1600.00, 30.00, 0.30, 25.00, 1.00, true, true
WHERE NOT EXISTS (SELECT 1 FROM public.platform_settings);

-- 2. ENHANCE WALLET TRANSACTIONS FOR PAYMENT CHANNELS & AUDITED VERIFICATION
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'wallet_transactions' AND column_name = 'payment_channel') THEN
        ALTER TABLE public.wallet_transactions ADD COLUMN payment_channel VARCHAR(50) DEFAULT 'manual';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'wallet_transactions' AND column_name = 'proof_url') THEN
        ALTER TABLE public.wallet_transactions ADD COLUMN proof_url TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'wallet_transactions' AND column_name = 'verified_by') THEN
        ALTER TABLE public.wallet_transactions ADD COLUMN verified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'wallet_transactions' AND column_name = 'verified_at') THEN
        ALTER TABLE public.wallet_transactions ADD COLUMN verified_at TIMESTAMP WITH TIME ZONE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'wallet_transactions' AND column_name = 'admin_notes') THEN
        ALTER TABLE public.wallet_transactions ADD COLUMN admin_notes TEXT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_payment_channel ON public.wallet_transactions(payment_channel);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON public.wallet_transactions(status);

-- 3. SERVICE PRICE OVERRIDES TABLE
CREATE TABLE IF NOT EXISTS public.service_price_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_code VARCHAR(50) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(30) NOT NULL DEFAULT '5sim' CHECK (provider_type IN ('5sim', 'textverified')),
    override_price_usd NUMERIC(10, 2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT uq_service_override UNIQUE (service_code, provider_type)
);

CREATE INDEX IF NOT EXISTS idx_service_overrides_lookup ON public.service_price_overrides(service_code, provider_type);

-- 4. ADMIN ROLE CHECK HELPER FUNCTION
CREATE OR REPLACE FUNCTION public.is_admin(p_user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = p_user_id AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. ADMIN RLS POLICIES
ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_price_overrides ENABLE ROW LEVEL SECURITY;

-- Allow public read of settings
DROP POLICY IF EXISTS "Public can read platform settings" ON public.platform_settings;
CREATE POLICY "Public can read platform settings"
    ON public.platform_settings FOR SELECT
    USING (true);

-- Allow admins full management of platform settings
DROP POLICY IF EXISTS "Admins can update platform settings" ON public.platform_settings;
CREATE POLICY "Admins can update platform settings"
    ON public.platform_settings FOR ALL
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));

-- Allow public read of price overrides
DROP POLICY IF EXISTS "Public can view price overrides" ON public.service_price_overrides;
CREATE POLICY "Public can view price overrides"
    ON public.service_price_overrides FOR SELECT
    USING (is_active = true);

-- Allow admins full management of price overrides
DROP POLICY IF EXISTS "Admins can manage price overrides" ON public.service_price_overrides;
CREATE POLICY "Admins can manage price overrides"
    ON public.service_price_overrides FOR ALL
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));

-- Allow admins full access to profiles, wallets, transactions, sim_orders
DROP POLICY IF EXISTS "Admins can view all profiles" ON public.profiles;
CREATE POLICY "Admins can view all profiles"
    ON public.profiles FOR SELECT
    TO authenticated
    USING (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can update all profiles" ON public.profiles;
CREATE POLICY "Admins can update all profiles"
    ON public.profiles FOR UPDATE
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can view all wallets" ON public.wallets;
CREATE POLICY "Admins can view all wallets"
    ON public.wallets FOR SELECT
    TO authenticated
    USING (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can update all wallets" ON public.wallets;
CREATE POLICY "Admins can update all wallets"
    ON public.wallets FOR UPDATE
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can view all transactions" ON public.wallet_transactions;
CREATE POLICY "Admins can view all transactions"
    ON public.wallet_transactions FOR SELECT
    TO authenticated
    USING (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can insert transactions" ON public.wallet_transactions;
CREATE POLICY "Admins can insert transactions"
    ON public.wallet_transactions FOR INSERT
    TO authenticated
    WITH CHECK (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can update transactions" ON public.wallet_transactions;
CREATE POLICY "Admins can update transactions"
    ON public.wallet_transactions FOR UPDATE
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can view all sim orders" ON public.sim_orders;
CREATE POLICY "Admins can view all sim orders"
    ON public.sim_orders FOR SELECT
    TO authenticated
    USING (public.is_admin(auth.uid()));

DROP POLICY IF EXISTS "Admins can update sim orders" ON public.sim_orders;
CREATE POLICY "Admins can update sim orders"
    ON public.sim_orders FOR UPDATE
    TO authenticated
    USING (public.is_admin(auth.uid()))
    WITH CHECK (public.is_admin(auth.uid()));
