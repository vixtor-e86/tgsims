-- ==============================================================================
-- TGSIMS MIGRATION 007: Drop UNIQUE constraint on public.profiles(username)
-- ==============================================================================
-- Since account registration and logins authenticate strictly via email,
-- usernames are treated as display names / aliases and do not need to be unique.
-- This migration removes the UNIQUE constraint from the profiles table so multiple
-- users can share the same display name without signup errors.

-- 1. Drop existing unique constraints on username if present
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_username_key;
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_username_unique;

-- 2. Drop unique index if created independently
DROP INDEX IF EXISTS public.profiles_username_key;
DROP INDEX IF EXISTS public.idx_profiles_username_unique;

-- 3. Maintain standard non-unique index for fast searching and admin queries
CREATE INDEX IF NOT EXISTS idx_profiles_username ON public.profiles(username);
