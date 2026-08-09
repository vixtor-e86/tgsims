-- ========================================================
-- TGSIMS - DATABASE SCHEMA FOR SUPABASE (POSTGRESQL)
-- ========================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. PROFILES TABLE (Linked to auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    phone_number TEXT,
    role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. WALLETS TABLE (Stores user wallet balances)
CREATE TABLE IF NOT EXISTS public.wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (balance >= 0),
    currency VARCHAR(5) DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. WALLET TRANSACTIONS TABLE (Double-entry ledger)
CREATE TABLE IF NOT EXISTS public.wallet_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('deposit', 'purchase', 'refund', 'bonus')),
    status VARCHAR(20) DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed', 'cancelled')),
    reference TEXT UNIQUE NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. SIM ORDERS TABLE (Active & Historical SIM Purchases)
CREATE TABLE IF NOT EXISTS public.sim_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    order_reference VARCHAR(50) UNIQUE NOT NULL,
    service_name VARCHAR(50) NOT NULL, -- e.g., 'WhatsApp', 'Telegram', 'eSIM Data'
    country_name VARCHAR(50) NOT NULL,
    country_code VARCHAR(10) NOT NULL,
    phone_number VARCHAR(30) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'expired', 'cancelled', 'refunded')),
    provider_order_id VARCHAR(100),
    sms_code TEXT,
    full_sms_text TEXT,
    qr_code_url TEXT, -- For eSIM activation
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ========================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ========================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sim_orders ENABLE ROW LEVEL SECURITY;

-- Profiles: Users can view & update their own profile
CREATE POLICY "Users can view own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- Wallets: Users can view their own wallet
CREATE POLICY "Users can view own wallet" ON public.wallets FOR SELECT USING (auth.uid() = user_id);

-- Transactions: Users can view their own transactions
CREATE POLICY "Users can view own transactions" ON public.wallet_transactions FOR SELECT USING (auth.uid() = user_id);

-- SIM Orders: Users can view their own SIM orders
CREATE POLICY "Users can view own sim orders" ON public.sim_orders FOR SELECT USING (auth.uid() = user_id);

-- ========================================================
-- ATOMIC POSTGRESQL RPC FUNCTION: DEDUCT WALLET BALANCE
-- Prevent Race Conditions when purchasing SIMs
-- ========================================================
CREATE OR REPLACE FUNCTION public.deduct_wallet_balance(
    p_user_id UUID,
    p_amount NUMERIC(12, 2),
    p_reference TEXT,
    p_description TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
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
    -- Lock wallet row for update to prevent simultaneous double-spend
    SELECT balance INTO v_current_balance
    FROM public.wallets
    WHERE user_id = p_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'message', 'Wallet not found.');
    END IF;

    IF v_current_balance < p_amount THEN
        RETURN jsonb_build_object('success', false, 'message', 'Insufficient wallet balance.');
    END IF;

    -- Calculate new balance
    v_new_balance := v_current_balance - p_amount;

    -- Update wallet balance
    UPDATE public.wallets
    SET balance = v_new_balance,
        updated_at = timezone('utc'::text, now())
    WHERE user_id = p_user_id;

    -- Record transaction
    INSERT INTO public.wallet_transactions (
        user_id, amount, type, status, reference, description, metadata
    ) VALUES (
        p_user_id, -p_amount, 'purchase', 'completed', p_reference, p_description, p_metadata
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

-- ========================================================
-- ATOMIC POSTGRESQL RPC FUNCTION: CREDIT WALLET BALANCE
-- For deposits and refunds
-- ========================================================
CREATE OR REPLACE FUNCTION public.credit_wallet_balance(
    p_user_id UUID,
    p_amount NUMERIC(12, 2),
    p_type TEXT,
    p_reference TEXT,
    p_description TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_balance NUMERIC(12, 2);
    v_transaction_id UUID;
BEGIN
    -- Ensure wallet exists, create if not present
    INSERT INTO public.wallets (user_id, balance)
    VALUES (p_user_id, 0.00)
    ON CONFLICT (user_id) DO NOTHING;

    -- Lock and update
    UPDATE public.wallets
    SET balance = balance + p_amount,
        updated_at = timezone('utc'::text, now())
    WHERE user_id = p_user_id
    RETURNING balance INTO v_new_balance;

    -- Record transaction
    INSERT INTO public.wallet_transactions (
        user_id, amount, type, status, reference, description, metadata
    ) VALUES (
        p_user_id, p_amount, p_type, 'completed', p_reference, p_description, p_metadata
    )
    RETURNING id INTO v_transaction_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Wallet credited successfully.',
        'new_balance', v_new_balance,
        'transaction_id', v_transaction_id
    );
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'message', SQLERRM);
END;
$$;
