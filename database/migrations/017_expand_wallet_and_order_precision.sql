-- ==============================================================================
-- TGSIMS MIGRATION 017: EXPAND WALLET, TRANSACTION, & ORDER CURRENCY PRECISION
-- ==============================================================================
-- Description:
--   Expands monetary columns from NUMERIC(12, 2) / NUMERIC(10, 2) to NUMERIC(16, 4).
--   This allows sub-cent USD precision (up to 4 decimal places) so that Naira (NGN)
--   conversions (e.g. ₦3,000 / 1333 = $2.2506) preserve mathematical fidelity
--   without 1-3 Naira round-trip conversion loss.
--   Also adds optional amount_ngn and user_cost_ngn columns for audit and explicit tracking.
-- ==============================================================================

-- 1. WALLETS: Expand balance to NUMERIC(16, 4)
ALTER TABLE public.wallets 
    ALTER COLUMN balance TYPE NUMERIC(16, 4);

-- 2. WALLET TRANSACTIONS: Expand amount to NUMERIC(16, 4) and add amount_ngn
ALTER TABLE public.wallet_transactions 
    ALTER COLUMN amount TYPE NUMERIC(16, 4);

ALTER TABLE public.wallet_transactions 
    ADD COLUMN IF NOT EXISTS amount_ngn NUMERIC(16, 2);

-- 3. SIM ORDERS: Expand user_cost to NUMERIC(16, 4) and add user_cost_ngn
ALTER TABLE public.sim_orders 
    ALTER COLUMN user_cost TYPE NUMERIC(16, 4);

ALTER TABLE public.sim_orders 
    ADD COLUMN IF NOT EXISTS user_cost_ngn NUMERIC(16, 2);

-- Comment for Supabase table documentation
COMMENT ON COLUMN public.wallets.balance IS 'User wallet balance in USD with 4 decimal places for exact NGN conversion fidelity';
COMMENT ON COLUMN public.sim_orders.user_cost IS 'Price charged to customer in USD (4 decimal places)';
COMMENT ON COLUMN public.sim_orders.user_cost_ngn IS 'Optional exact customer charge in NGN at the time of purchase';
