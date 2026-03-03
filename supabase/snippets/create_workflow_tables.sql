-- Workflow MVP schema for enterprise task orchestration.
-- Scenario covered: monthly operating analysis.

create table if not exists public.workflow_jobs (
  id bigint primary key generated always as identity,
  job_id text not null unique,
  user_id text not null,
  session_id text not null,
  name text not null,
  scenario text not null,
  status text not null default 'pending',
  current_step integer not null default 0,
  model_backend text not null default 'local',
  requires_confirmation boolean not null default false,
  confirmed_at timestamptz,
  confirmed_by text,
  input_json jsonb not null default '{}'::jsonb,
  result_json jsonb not null default '{}'::jsonb,
  error text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.workflow_steps (
  id bigint primary key generated always as identity,
  job_id text not null references public.workflow_jobs(job_id) on delete cascade,
  step_key text not null,
  step_name text not null,
  step_order integer not null,
  status text not null default 'pending',
  needs_confirmation boolean not null default false,
  confirmed_at timestamptz,
  confirmed_by text,
  input_json jsonb not null default '{}'::jsonb,
  output_json jsonb not null default '{}'::jsonb,
  artifact_url text,
  error text,
  started_at timestamptz,
  finished_at timestamptz,
  duration_ms integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (job_id, step_key)
);

create index if not exists workflow_jobs_user_idx on public.workflow_jobs(user_id, created_at desc);
create index if not exists workflow_jobs_status_idx on public.workflow_jobs(status, created_at desc);
create index if not exists workflow_steps_job_idx on public.workflow_steps(job_id, step_order);
