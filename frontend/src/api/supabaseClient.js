import { createClient } from '@supabase/supabase-js';

const DEFAULT_SUPABASE_URL = 'http://127.0.0.1:54321';
const DEFAULT_SUPABASE_ANON_KEY =
  '***REMOVED_SUPABASE_DEMO_TOKEN***';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || DEFAULT_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || DEFAULT_SUPABASE_ANON_KEY;

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: false,
  },
});

export const STORAGE_BUCKET = 'voice_uploads';
