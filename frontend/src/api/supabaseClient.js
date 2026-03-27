/* global __APP_PUBLIC_SUPABASE_URL__, __APP_PUBLIC_SUPABASE_ANON_KEY__ */

import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL =
  typeof __APP_PUBLIC_SUPABASE_URL__ === 'string' ? __APP_PUBLIC_SUPABASE_URL__.trim() : '';
const SUPABASE_ANON_KEY =
  typeof __APP_PUBLIC_SUPABASE_ANON_KEY__ === 'string' ? __APP_PUBLIC_SUPABASE_ANON_KEY__.trim() : '';

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error('Missing Supabase public config. Set SUPABASE_URL and SUPABASE_ANON_KEY in Backend/.env.local.');
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: false,
  },
});

export const STORAGE_BUCKET = 'voice_uploads';
