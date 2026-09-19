-- ==============================================================================
-- TGSIMS MIGRATION 009: 5-CHARACTER REFERRAL SYSTEM, COMMISSIONS & REDEMPTION WALLET
-- ==============================================================================
-- Description:
--   1. Adds 5-character referral code, referred_by link, and referral wallet balance to profiles.
--   2. Provides unique 5-char alphanumeric generator and backfills existing profiles.
--   3. Updates handle_new_user() trigger to generate codes and link referrers upon signup.
--   4. Creates public.referral_commissions to track 5% earnings on spendings/orders.
--   5. Creates public.referral_redemptions to track transfers from referral wallet to main balance ($1.00 minimum).
--   6. Configures indexes and Row Level Security (RLS).
-- ==============================================================================

-- 1. ADD REFERRAL COLUMNS TO PROFILES
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS referral_code VARCHAR(10) UNIQUE,
    ADD COLUMN IF NOT EXISTS referred_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS referral_balance NUMERIC(12, 4) NOT NULL DEFAULT 0.0000 CHECK (referral_balance >= 0);

CREATE INDEX IF NOT EXISTS idx_profiles_referral_code ON public.profiles(referral_code);
CREATE INDEX IF NOT EXISTS idx_profiles_referred_by ON public.profiles(referred_by);

-- 2. 5-CHARACTER UNIQUE REFERRAL CODE GENERATOR FUNCTION
CREATE OR REPLACE FUNCTION public.generate_unique_referral_code()
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    code TEXT := '';
    i INT;
    done BOOLEAN := false;
BEGIN
    WHILE NOT done LOOP
        code := '';
        FOR i IN 1..5 LOOP
            code := code || substr(chars, floor(random() * length(chars) + 1)::integer, 1);
        END LOOP;
        IF NOT EXISTS (SELECT 1 FROM public.profiles WHERE referral_code = code) THEN
            done := true;
        END IF;
    END LOOP;
    RETURN code;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- 3. BACKFILL EXISTING PROFILES WITH 5-CHARACTER REFERRAL CODES
DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN SELECT id FROM public.profiles WHERE referral_code IS NULL LOOP
        UPDATE public.profiles
        SET referral_code = public.generate_unique_referral_code()
        WHERE id = rec.id;
    END LOOP;
END $$;

-- 4. UPDATE handle_new_user() TRIGGER TO AUTOMATICALLY ASSIGN 5-CHAR CODE & LINK REFERRER
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    v_username TEXT;
    v_full_name TEXT;
    v_ref_code TEXT;
    v_referred_by UUID := NULL;
    v_input_ref TEXT;
BEGIN
    -- Extract username and full_name from raw user metadata if passed during sign_up
    v_username := COALESCE(
        NEW.raw_user_meta_data->>'username',
        split_part(NEW.email, '@', 1)
    );
    v_full_name := COALESCE(
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'username',
        split_part(NEW.email, '@', 1)
    );

    -- Generate unique 5-character referral code if not provided
    v_ref_code := COALESCE(
        NULLIF(trim(NEW.raw_user_meta_data->>'referral_code'), ''),
        public.generate_unique_referral_code()
    );

    -- Check if user was referred by an existing code
    v_input_ref := COALESCE(
        NEW.raw_user_meta_data->>'referred_by_code',
        NEW.raw_user_meta_data->>'referral_code_used'
    );
    IF v_input_ref IS NOT NULL AND trim(v_input_ref) <> '' THEN
        SELECT id INTO v_referred_by
        FROM public.profiles
        WHERE UPPER(referral_code) = UPPER(trim(v_input_ref))
        LIMIT 1;
    END IF;

    -- Insert into public.profiles
    INSERT INTO public.profiles (id, email, username, full_name, referral_code, referred_by, referral_balance)
    VALUES (NEW.id, NEW.email, v_username, v_full_name, v_ref_code, v_referred_by, 0.0000)
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        username = COALESCE(public.profiles.username, EXCLUDED.username),
        full_name = COALESCE(public.profiles.full_name, EXCLUDED.full_name),
        referral_code = COALESCE(public.profiles.referral_code, EXCLUDED.referral_code),
        referred_by = COALESCE(public.profiles.referred_by, EXCLUDED.referred_by),
        updated_at = timezone('utc'::text, now());

    -- Automatically initialize wallet with $0.00 balance
    INSERT INTO public.wallets (user_id, balance, currency)
    VALUES (NEW.id, 0.00, 'USD')
    ON CONFLICT (user_id) DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. REFERRAL COMMISSIONS TABLE (5% of referred users' spendings)
CREATE TABLE IF NOT EXISTS public.referral_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    referred_user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id UUID REFERENCES public.sim_orders(id) ON DELETE SET NULL,
    order_reference VARCHAR(50),
    amount_spent NUMERIC(10, 4) NOT NULL,
    commission_rate NUMERIC(5, 2) NOT NULL DEFAULT 5.00,
    commission_earned NUMERIC(10, 4) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'credited' CHECK (status IN ('credited', 'reversed', 'cancelled')),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referral_commissions_referrer ON public.referral_commissions(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_referred ON public.referral_commissions(referred_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_order ON public.referral_commissions(order_id);

-- 6. REFERRAL REDEMPTIONS TABLE (Withdrawal to Main Wallet, $1.00 min)
CREATE TABLE IF NOT EXISTS public.referral_redemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount NUMERIC(10, 4) NOT NULL CHECK (amount >= 1.00),
    status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed')),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_referral_redemptions_user ON public.referral_redemptions(user_id);

-- 7. ROW LEVEL SECURITY
ALTER TABLE public.referral_commissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_redemptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their earned referral commissions" ON public.referral_commissions;
CREATE POLICY "Users can view their earned referral commissions"
    ON public.referral_commissions FOR SELECT
    TO authenticated
    USING (auth.uid() = referrer_id);

DROP POLICY IF EXISTS "Users can view their referral redemptions" ON public.referral_redemptions;
CREATE POLICY "Users can view their referral redemptions"
    ON public.referral_redemptions FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);
