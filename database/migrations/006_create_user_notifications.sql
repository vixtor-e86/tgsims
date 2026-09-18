-- ==============================================================================
-- TGSIMS MIGRATION 006: User Notifications System & Admin Broadcasts
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.user_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE, -- NULL indicates global broadcast to all users
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'system' CHECK (type IN ('deposit', 'purchase', 'refund', 'admin_credit', 'admin_debit', 'promo', 'update', 'system')),
    link VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_id ON public.user_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notifications_created_at ON public.user_notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_unread ON public.user_notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_user_notifications_type ON public.user_notifications(type);

-- ROW LEVEL SECURITY (RLS)
ALTER TABLE public.user_notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read their own or broadcast notifications" ON public.user_notifications;
CREATE POLICY "Users can read their own or broadcast notifications"
    ON public.user_notifications FOR SELECT
    TO authenticated
    USING (user_id IS NULL OR user_id = auth.uid());

DROP POLICY IF EXISTS "Users can update their own notifications" ON public.user_notifications;
CREATE POLICY "Users can update their own notifications"
    ON public.user_notifications FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "Service role has full access to user notifications" ON public.user_notifications;
CREATE POLICY "Service role has full access to user notifications"
    ON public.user_notifications FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
