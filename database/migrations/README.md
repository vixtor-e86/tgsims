# Database Migrations

This folder contains versioned SQL migrations for the **Tgsims** Supabase PostgreSQL database.

## Migration History

| File | Description | Status |
|---|---|---|
| [`001_create_users_profiles_wallets.sql`](./001_create_users_profiles_wallets.sql) | Creates `public.profiles`, `public.wallets`, and automated trigger `on_auth_user_created` to sync with Supabase `auth.users`. | Ready to apply |
| [`002_create_sim_orders_transactions_and_sms.sql`](./002_create_sim_orders_transactions_and_sms.sql) | Creates `public.sim_orders` (5sim lifecycle), `public.sim_sms_messages` (multi-SMS feed), `public.wallet_transactions`, `public.service_catalog` (cached 5sim rates & stock), `public.platform_settings`, and atomic RPC functions for balance deduction, cancellations, and instant refunds. | Ready to apply |

## How to Apply Migrations to Supabase

1. Open your **Supabase Dashboard**: [https://supabase.com/dashboard](https://supabase.com/dashboard).
2. Select your project.
3. In the left navigation menu, click **SQL Editor**.
4. If you have already applied `001_create_users_profiles_wallets.sql`, click **New Query**, paste the full contents of `002_create_sim_orders_transactions_and_sms.sql`, and click **Run**.
5. If setting up a completely fresh database, you can simply paste and run [`database/schema.sql`](../schema.sql) which contains the entire unified schema.
6. You should see `Success. No rows returned`.
