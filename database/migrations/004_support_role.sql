-- Migration 004: Add 'support' to profiles.role CHECK constraint
-- Run this in your Supabase SQL Editor:
-- https://supabase.com/dashboard/project/vasyfwwbamkdieughmlv/sql

-- 1. Drop the existing 2-role check constraint
ALTER TABLE public.profiles 
DROP CONSTRAINT IF EXISTS profiles_role_check;

-- 2. Add the updated check constraint supporting 'user', 'admin', and 'support'
ALTER TABLE public.profiles 
ADD CONSTRAINT profiles_role_check 
CHECK (role IN ('user', 'admin', 'support'));
