-- ==============================================================================
-- TGSIMS MIGRATION 002: 5SIM INTEGRATION, SIM ORDERS, SMS FEED, & TRANSACTIONS
-- ==============================================================================
-- Description:
--   1. Creates public.sim_orders tailored for 5sim activation & hosting lifecycles.
--   2. Creates public.wallet_transactions (double-entry ledger with order linking).
--   3. Creates public.sim_sms_messages for multi-SMS verification tracking.
--   4. Creates public.service_catalog for caching 5sim prices, stock & profit margins.
--   5. Creates public.platform_settings for global markups & exchange rates.
--   6. Implements atomic PostgreSQL RPC functions:
--      - deduct_wallet_balance: atomically deducts funds upon order creation
--      - refund_sim_order: atomically refunds wallet on order cancel/timeout/ban
--      - record_sim_sms: records received SMS and updates order state
--      - complete_sim_order: finalizes completed orders
--   7. Configures Row Level Security (RLS) policies and performance indexes.
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. SIM ORDERS TABLE (5sim lifecycle)
CREATE TABLE IF NOT EXISTS public.sim_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_reference VARCHAR(50) UNIQUE NOT NULL,
    provider VARCHAR(30) DEFAULT '5sim' NOT NULL,
    provider_order_id VARCHAR(100),
    order_type VARCHAR(20) DEFAULT 'activation' CHECK (order_type IN ('activation', 'hosting')),
    country_code VARCHAR(10) NOT NULL,
    country_name VARCHAR(60) NOT NULL,
    country_slug VARCHAR(60),
    operator VARCHAR(50) DEFAULT 'any',
    service_code VARCHAR(50) NOT NULL,
    service_name VARCHAR(60) NOT NULL,
    phone_number VARCHAR(35) NOT NULL,
    provider_cost NUMERIC(10, 4) DEFAULT 0.0000,
    user_cost NUMERIC(10, 2) NOT NULL,
    profit_margin NUMERIC(10, 4) DEFAULT 0.0000,
    currency VARCHAR(5) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'received', 'completed', 'cancelled', 'timeout', 'banned', 'refunded')),
    sms_code TEXT,
    full_sms_text TEXT,
    sms_count INT DEFAULT 0,
    qr_code_url TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    refunded_at TIMESTAMP WITH TIME ZONE,
    refund_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_orders_user_id ON public.sim_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_sim_orders_provider_order_id ON public.sim_orders(provider_order_id);
CREATE INDEX IF NOT EXISTS idx_sim_orders_status ON public.sim_orders(status);
CREATE INDEX IF NOT EXISTS idx_sim_orders_reference ON public.sim_orders(order_reference);
CREATE INDEX IF NOT EXISTS idx_sim_orders_created_at ON public.sim_orders(created_at DESC);

-- 3. WALLET TRANSACTIONS TABLE
CREATE TABLE IF NOT EXISTS public.wallet_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_id UUID REFERENCES public.sim_orders(id) ON DELETE SET NULL,
    amount NUMERIC(12, 2) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('deposit', 'purchase', 'refund', 'bonus', 'adjustment')),
    status VARCHAR(20) DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed', 'cancelled')),
    reference TEXT UNIQUE NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON public.wallet_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_order_id ON public.wallet_transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_reference ON public.wallet_transactions(reference);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_created_at ON public.wallet_transactions(created_at DESC);

-- 4. SIM SMS MESSAGES TABLE (Multiple SMS per order)
CREATE TABLE IF NOT EXISTS public.sim_sms_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES public.sim_orders(id) ON DELETE CASCADE,
    provider_sms_id VARCHAR(100),
    sender VARCHAR(100),
    sms_code VARCHAR(50),
    full_text TEXT NOT NULL,
    raw_data JSONB DEFAULT '{}'::jsonb,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_sms_messages_order_id ON public.sim_sms_messages(order_id);
CREATE INDEX IF NOT EXISTS idx_sim_sms_messages_received_at ON public.sim_sms_messages(received_at DESC);

-- 5. SERVICE CATALOG (5sim price & stock cache)
CREATE TABLE IF NOT EXISTS public.service_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code VARCHAR(10) NOT NULL,
    country_name VARCHAR(60) NOT NULL,
    country_slug VARCHAR(60) NOT NULL,
    service_code VARCHAR(50) NOT NULL,
    service_name VARCHAR(60) NOT NULL,
    category VARCHAR(40) DEFAULT 'SMS Verification',
    operator VARCHAR(50) DEFAULT 'any',
    provider_cost NUMERIC(10, 4) DEFAULT 0.0000,
    retail_price NUMERIC(10, 2) NOT NULL,
    available_count INT DEFAULT 0,
    success_rate NUMERIC(5, 2) DEFAULT 95.00,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT uq_service_catalog_item UNIQUE (country_slug, service_code, operator)
);

CREATE INDEX IF NOT EXISTS idx_service_catalog_country ON public.service_catalog(country_code);
CREATE INDEX IF NOT EXISTS idx_service_catalog_service ON public.service_catalog(service_code);
CREATE INDEX IF NOT EXISTS idx_service_catalog_active ON public.service_catalog(is_active);

-- 6. PLATFORM SETTINGS (Markups & Conversion Rates)
CREATE TABLE IF NOT EXISTS public.platform_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    default_markup_percent NUMERIC(5, 2) DEFAULT 30.00,
    min_profit_usd NUMERIC(10, 2) DEFAULT 0.30,
    rub_to_usd_rate NUMERIC(10, 6) DEFAULT 0.011000,
    ngn_per_usd_rate NUMERIC(10, 2) DEFAULT 1600.00,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Seed initial default settings if table empty
INSERT INTO public.platform_settings (default_markup_percent, min_profit_usd, rub_to_usd_rate, ngn_per_usd_rate)
SELECT 30.00, 0.30, 0.011000, 1600.00
WHERE NOT EXISTS (SELECT 1 FROM public.platform_settings);

-- 7. ROW LEVEL SECURITY (RLS) POLICIES
ALTER TABLE public.sim_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_sms_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;

-- SIM Orders Policies
DROP POLICY IF EXISTS "Users can view own sim orders" ON public.sim_orders;
CREATE POLICY "Users can view own sim orders"
    ON public.sim_orders FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Wallet Transactions Policies
DROP POLICY IF EXISTS "Users can view own transactions" ON public.wallet_transactions;
CREATE POLICY "Users can view own transactions"
    ON public.wallet_transactions FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- SIM SMS Messages Policies
DROP POLICY IF EXISTS "Users can view own order messages" ON public.sim_sms_messages;
CREATE POLICY "Users can view own order messages"
    ON public.sim_sms_messages FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.sim_orders
            WHERE public.sim_orders.id = public.sim_sms_messages.order_id
              AND public.sim_orders.user_id = auth.uid()
        )
    );

-- Catalog Policies (Public read-only)
DROP POLICY IF EXISTS "Catalog is viewable by everyone" ON public.service_catalog;
CREATE POLICY "Catalog is viewable by everyone"
    ON public.service_catalog FOR SELECT
    USING (true);

-- Settings Policies (Public read-only)
DROP POLICY IF EXISTS "Platform settings viewable by everyone" ON public.platform_settings;
CREATE POLICY "Platform settings viewable by everyone"
    ON public.platform_settings FOR SELECT
    USING (true);

-- 8. TRIGGER: set_updated_at for sim_orders and service_catalog
DROP TRIGGER IF EXISTS tr_sim_orders_updated_at ON public.sim_orders;
CREATE TRIGGER tr_sim_orders_updated_at
    BEFORE UPDATE ON public.sim_orders
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS tr_service_catalog_updated_at ON public.service_catalog;
CREATE TRIGGER tr_service_catalog_updated_at
    BEFORE UPDATE ON public.service_catalog
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ==============================================================================
-- 9. ATOMIC STORED PROCEDURES (RPCs)
-- ==============================================================================

-- 9A. DEDUCT WALLET BALANCE FOR PURCHASE
CREATE OR REPLACE FUNCTION public.deduct_wallet_balance(
    p_user_id UUID,
    p_amount NUMERIC(12, 2),
    p_reference TEXT,
    p_description TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb,
    p_order_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_balance NUMERIC(12, 2);
    v_new_balance NUMERIC(12, 2);
    v_transaction_id UUID;
BEGIN
    -- Lock wallet row FOR UPDATE to strictly prevent race conditions & double-spend
    SELECT balance INTO v_current_balance
    FROM public.wallets
    WHERE user_id = p_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'message', 'Wallet not found.');
    END IF;

    IF v_current_balance < p_amount THEN
        RETURN jsonb_build_object(
            'success', false,
            'message', 'Insufficient wallet balance.',
            'balance', v_current_balance,
            'required', p_amount
        );
    END IF;

    v_new_balance := v_current_balance - p_amount;

    -- Update balance
    UPDATE public.wallets
    SET balance = v_new_balance,
        updated_at = timezone('utc'::text, now())
    WHERE user_id = p_user_id;

    -- Record transaction
    INSERT INTO public.wallet_transactions (
        user_id, order_id, amount, type, status, reference, description, metadata
    ) VALUES (
        p_user_id, p_order_id, -p_amount, 'purchase', 'completed', p_reference, p_description, p_metadata
    )
    RETURNING id INTO v_transaction_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Balance deducted successfully.',
        'new_balance', v_new_balance,
        'transaction_id', v_transaction_id
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'message', SQLERRM);
END;
$$;

-- 9B. ATOMIC REFUND FOR SIM ORDER (On Cancel, Timeout, or Ban)
CREATE OR REPLACE FUNCTION public.refund_sim_order(
    p_order_id UUID,
    p_reason TEXT DEFAULT 'Order cancelled or expired without receiving SMS'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_order RECORD;
    v_new_balance NUMERIC(12, 2);
    v_ref_tx_id UUID;
    v_refund_ref TEXT;
BEGIN
    -- Lock order row
    SELECT * INTO v_order
    FROM public.sim_orders
    WHERE id = p_order_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'message', 'Order not found.');
    END IF;

    -- Prevent double refund
    IF v_order.status IN ('refunded', 'cancelled') THEN
        RETURN jsonb_build_object('success', false, 'message', 'Order has already been refunded or cancelled.');
    END IF;

    -- Prevent refunding completed orders
    IF v_order.status = 'completed' THEN
        RETURN jsonb_build_object('success', false, 'message', 'Completed orders cannot be refunded.');
    END IF;

    -- Lock and credit user wallet
    UPDATE public.wallets
    SET balance = balance + v_order.user_cost,
        updated_at = timezone('utc'::text, now())
    WHERE user_id = v_order.user_id
    RETURNING balance INTO v_new_balance;

    -- Generate refund reference
    v_refund_ref := 'REF-' || substr(md5(random()::text || clock_timestamp()::text), 1, 10);

    -- Insert refund ledger entry
    INSERT INTO public.wallet_transactions (
        user_id, order_id, amount, type, status, reference, description, metadata
    ) VALUES (
        v_order.user_id,
        v_order.id,
        v_order.user_cost,
        'refund',
        'completed',
        v_refund_ref,
        'Refund for ' || v_order.service_name || ' (' || v_order.phone_number || ') - ' || p_reason,
        jsonb_build_object('order_reference', v_order.order_reference, 'reason', p_reason)
    )
    RETURNING id INTO v_ref_tx_id;

    -- Update order status
    UPDATE public.sim_orders
    SET status = 'refunded',
        refunded_at = timezone('utc'::text, now()),
        refund_reason = p_reason,
        updated_at = timezone('utc'::text, now())
    WHERE id = p_order_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Order refunded successfully.',
        'refunded_amount', v_order.user_cost,
        'new_balance', v_new_balance,
        'transaction_id', v_ref_tx_id
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'message', SQLERRM);
END;
$$;

-- 9C. RECORD RECEIVED SMS FOR AN ORDER
CREATE OR REPLACE FUNCTION public.record_sim_sms(
    p_order_id UUID,
    p_provider_sms_id VARCHAR,
    p_sender VARCHAR,
    p_sms_code VARCHAR,
    p_full_text TEXT,
    p_raw_data JSONB DEFAULT '{}'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_sms_id UUID;
BEGIN
    -- Insert into sim_sms_messages
    INSERT INTO public.sim_sms_messages (
        order_id, provider_sms_id, sender, sms_code, full_text, raw_data
    ) VALUES (
        p_order_id, p_provider_sms_id, p_sender, p_sms_code, p_full_text, p_raw_data
    )
    RETURNING id INTO v_sms_id;

    -- Update sim_orders with latest SMS info
    UPDATE public.sim_orders
    SET status = 'received',
        sms_code = p_sms_code,
        full_sms_text = p_full_text,
        sms_count = sms_count + 1,
        updated_at = timezone('utc'::text, now())
    WHERE id = p_order_id;

    RETURN jsonb_build_object(
        'success', true,
        'sms_id', v_sms_id,
        'sms_code', p_sms_code
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'message', SQLERRM);
END;
$$;

-- 9D. COMPLETE SIM ORDER
CREATE OR REPLACE FUNCTION public.complete_sim_order(
    p_order_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.sim_orders
    SET status = 'completed',
        completed_at = timezone('utc'::text, now()),
        updated_at = timezone('utc'::text, now())
    WHERE id = p_order_id;

    RETURN jsonb_build_object('success', true, 'message', 'Order marked as completed.');
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'message', SQLERRM);
END;
$$;
