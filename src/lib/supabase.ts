import { createClient } from '@supabase/supabase-js';

const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || '').trim();
const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || '').trim();

// Fail loud: a missing or truncated env var must break the build's runtime, not silently point at another project
if (!/^https:\/\/\S+$/.test(supabaseUrl)) {
  throw new Error('VITE_SUPABASE_URL is missing or not an https URL. Set it in .env / Vercel env.');
}
if (supabaseAnonKey.split('.').length !== 3) {
  throw new Error('VITE_SUPABASE_ANON_KEY is missing or malformed (expected a 3-part JWT). Set it in .env / Vercel env.');
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: typeof window !== 'undefined' ? window.localStorage : undefined,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true
  }
});

// Backward compatibility alias
export const db = supabase;
