-- Qgurukul user profiles (run in Supabase SQL Editor if the table is incomplete).
-- This is the source of truth for name, email, plan flags, and rate limits.
-- Flask sessions only store "who is logged in", not the plan itself.

create table if not exists public.users (
  email text primary key,
  name text not null,
  mobile text,
  institute_name text,
  city text,
  role text not null default 'student', -- student, teacher, admin
  school_name text,
  class_teaching text,
  is_premium boolean not null default false,
  is_super_premium boolean not null default false,
  password_hash text, -- nullable: older accounts may log in by email only
  created_at timestamptz not null default now(),
  hourly_count integer not null default 0,
  hourly_reset timestamptz,
  daily_count integer not null default 0,
  daily_reset timestamptz
);

-- If the table already exists, these ALTER statements are safe to re-run.
alter table public.users add column if not exists is_premium boolean not null default false;
alter table public.users add column if not exists is_super_premium boolean not null default false;
alter table public.users add column if not exists password_hash text;
-- Add after the daily_reset line:
alter table public.users add column if not exists total_papers integer not null default 0;
alter table public.users add column if not exists total_questions integer not null default 0;
alter table public.users add column if not exists recent_papers text;

-- Helpful if you later enable Row Level Security with Supabase Auth.
-- Until then, the Flask server uses the API key to read/write this table.
create index if not exists users_created_at_idx on public.users (created_at);

-- Optional: turn on RLS only AFTER you migrate to Supabase Auth (auth.uid()).
-- alter table public.users enable row level security;
