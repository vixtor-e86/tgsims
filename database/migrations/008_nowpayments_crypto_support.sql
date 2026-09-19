-- ==============================================================================
-- TGSIMS MIGRATION 008: NOWPayments Enterprise Crypto Gateway Support
-- ==============================================================================
-- Optimizes indices and constraints for automated cryptocurrency IPN callbacks
-- and payment reference lookups.

-- 1. Ensure indexes for rapid payment lookup and IPN idempotency checks
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_reference ON public.wallet_transactions(reference);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_payment_channel ON public.wallet_transactions(payment_channel);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON public.wallet_transactions(status);

-- 2. Optional index on JSONB metadata payment_id for fast webhook lookups
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_meta_payment_id 
ON public.wallet_transactions ((metadata->>'payment_id'));
