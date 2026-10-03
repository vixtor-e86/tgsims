-- ==============================================================================
-- TGSIMS MIGRATION 011: RENTALS (RESERVATIONS) SYSTEM & REACTIVATION EXPIRY
-- ==============================================================================
-- Description:
--   1. Creates public.sim_rentals for dedicated long-term virtual number rentals
--      (3-day, 7-day, 14-day, 30-day, etc. with TextVerified / provider reservations).
--   2. Links wallet_transactions to sim_rentals for transaction auditing.
--   3. Enables sim_sms_messages to store incoming SMS for rental lines.
--   4. Adds reactivation_expired column to public.sim_orders to permanently
--      hide/disable reactivation button once a carrier slot has rotated.
--   5. Configures Row Level Security (RLS) policies and performance indexes.
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. CREATE SIM RENTALS TABLE
CREATE TABLE IF NOT EXISTS public.sim_rentals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    rental_reference VARCHAR(50) UNIQUE NOT NULL,
    provider VARCHAR(30) DEFAULT 'textverified' NOT NULL,
    provider_reservation_id VARCHAR(100),
    service_code VARCHAR(50) NOT NULL,
    service_name VARCHAR(80) NOT NULL,
    phone_number VARCHAR(35) NOT NULL,
    country_code VARCHAR(10) DEFAULT 'US' NOT NULL,
    country_name VARCHAR(60) DEFAULT 'United States' NOT NULL,
    duration_days INT NOT NULL,
    duration_tier VARCHAR(30) NOT NULL,
    provider_cost NUMERIC(10, 4) DEFAULT 0.0000,
    user_cost NUMERIC(10, 2) NOT NULL,
    user_cost_ngn NUMERIC(12, 2),
    profit_margin NUMERIC(10, 4) DEFAULT 0.0000,
    currency VARCHAR(5) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'pending', 'refunded')),
    sms_count INT DEFAULT 0,
    last_sms_code TEXT,
    last_sms_text TEXT,
    starts_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    auto_renew BOOLEAN DEFAULT false,
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Indexes for sim_rentals
CREATE INDEX IF NOT EXISTS idx_sim_rentals_user_id ON public.sim_rentals(user_id);
CREATE INDEX IF NOT EXISTS idx_sim_rentals_status ON public.sim_rentals(status);
CREATE INDEX IF NOT EXISTS idx_sim_rentals_reference ON public.sim_rentals(rental_reference);
CREATE INDEX IF NOT EXISTS idx_sim_rentals_expires_at ON public.sim_rentals(expires_at);
CREATE INDEX IF NOT EXISTS idx_sim_rentals_created_at ON public.sim_rentals(created_at DESC);

-- 3. LINK WALLET TRANSACTIONS TO RENTALS
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'wallet_transactions' 
          AND column_name = 'rental_id'
    ) THEN
        ALTER TABLE public.wallet_transactions 
        ADD COLUMN rental_id UUID REFERENCES public.sim_rentals(id) ON DELETE SET NULL;

        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_rental_id 
        ON public.wallet_transactions(rental_id);
    END IF;
END $$;

-- 4. LINK SIM SMS MESSAGES TO RENTALS (Allow SMS to belong to order OR rental)
DO $$
BEGIN
    -- Make order_id optional so rental SMS can exist independently
    ALTER TABLE public.sim_sms_messages ALTER COLUMN order_id DROP NOT NULL;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'sim_sms_messages' 
          AND column_name = 'rental_id'
    ) THEN
        ALTER TABLE public.sim_sms_messages 
        ADD COLUMN rental_id UUID REFERENCES public.sim_rentals(id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS idx_sim_sms_messages_rental_id 
        ON public.sim_sms_messages(rental_id);
    END IF;
END $$;

-- 5. ADD REACTIVATION_EXPIRED COLUMN TO SIM_ORDERS
-- Flags orders whose carrier slot rotated away so the Reactivate button disappears permanently
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'sim_orders' 
          AND column_name = 'reactivation_expired'
    ) THEN
        ALTER TABLE public.sim_orders 
        ADD COLUMN reactivation_expired BOOLEAN DEFAULT false;
    END IF;
END $$;

-- 6. ROW LEVEL SECURITY (RLS) FOR SIM RENTALS
ALTER TABLE public.sim_rentals ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    DROP POLICY IF EXISTS "Users can view their own rentals" ON public.sim_rentals;
    DROP POLICY IF EXISTS "Service role can manage all rentals" ON public.sim_rentals;
END $$;

CREATE POLICY "Users can view their own rentals"
    ON public.sim_rentals
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage all rentals"
    ON public.sim_rentals
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 7. PERMISSIONS
GRANT ALL ON public.sim_rentals TO service_role;
GRANT SELECT ON public.sim_rentals TO authenticated;
