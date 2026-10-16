-- Strud AI: additive authenticated persistence support.
-- Apply with the Supabase CLI or SQL Editor after reviewing against the
-- existing production schema.  This migration does not alter or delete rows.

create table if not exists public.provider_configs (
  -- Existing Strud tables use text user_id values (auth.uid()::text), so a
  -- UUID foreign key would be incompatible. RLS below is the ownership gate.
  user_id text primary key,
  provider text not null check (provider in ('gptoss', 'qwen', 'gemini', 'custom')),
  model_id text not null,
  base_url text,
  temperature numeric,
  max_tokens integer,
  key_in_browser boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.provider_configs enable row level security;

drop policy if exists provider_configs_owner_all on public.provider_configs;
create policy provider_configs_owner_all on public.provider_configs
  for all to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

-- The existing initial migration predates source/error fields used by the
-- authenticated web client.  Add them only if that deployment lacks them.
alter table public.conversations
  add column if not exists sources_json jsonb not null default '[]'::jsonb,
  add column if not exists error text;

-- Profile identity is seeded from verified Google metadata.  These columns
-- are intentionally non-secret and remain governed by the existing profile
-- owner RLS policy.
alter table public.profiles
  add column if not exists email text,
  add column if not exists avatar text;
