import { createClient } from '@supabase/supabase-js';

// 使用你提供的 Supabase 项目信息
const SUPABASE_URL = "https://gjbmkzduwtcfhmivvklj.supabase.co";
const SUPABASE_ANON_KEY = "***REMOVED_SUPABASE_SERVICE_ROLE_TOKEN***";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});

// 存储桶名称常量
export const STORAGE_BUCKET = 'voice_uploads';
