# Database Migrations

This folder contains versioned SQL migrations for the **Tgsims** Supabase PostgreSQL database.

## Migration History

| File | Description | Status |
|---|---|---|
| [`001_create_users_profiles_wallets.sql`](./001_create_users_profiles_wallets.sql) | Creates `public.profiles`, `public.wallets`, and automated trigger `on_auth_user_created` to sync with Supabase `auth.users`. | Ready to apply |

## How to Apply Migrations to Supabase

1. Open your **Supabase Dashboard**: [https://supabase.com/dashboard](https://supabase.com/dashboard).
2. Select your project.
3. In the left navigation menu, click **SQL Editor**.
4. Click **New Query**.
5. Copy the full contents of `001_create_users_profiles_wallets.sql` and paste it into the editor.
6. Click **Run** (or press `Ctrl+Enter`).
7. You should see `Success. No rows returned`.
