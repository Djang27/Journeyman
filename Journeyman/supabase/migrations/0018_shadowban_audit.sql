-- Why somebody is shadowbanned, and since when.
--
-- 0017 added the flag as a bare boolean. That is enough to filter a board and
-- not enough to answer the question that always comes later: why is this
-- account hidden, and who decided? A boolean forgets, and the moment you want
-- the answer is the moment the person is asking you to justify it.
--
-- Same reasoning as game_results.voided_reason. Marked rather than deleted, and
-- with the reason attached rather than in somebody's memory.
--
-- Nullable and defaulted, so 0017's flag keeps working untouched.

alter table public.profiles
  add column if not exists shadowbanned_at timestamptz;

alter table public.profiles
  add column if not exists shadowbanned_reason text;

-- Both are as private as the flag. 0017 revoked SELECT on profiles and granted
-- id and display_name back, so these are already unreadable by clients -- a
-- column added later is not granted, which was the point of doing it that way.
-- Restated here so a future reader does not have to reconstruct it.
comment on column public.profiles.shadowbanned_at is
  'When the flag was set. Not readable by anon or authenticated.';
comment on column public.profiles.shadowbanned_reason is
  'Why. Operator-facing only, never shown to the account it describes.';


-- Set or clear the flag, stamping the reason with it.
--
-- One statement so the flag and its explanation cannot disagree -- setting the
-- boolean and forgetting the reason is exactly how a ban becomes unexplainable.
-- Returns whether anything changed, so a repeated call is distinguishable from
-- a first one without a second read.
create or replace function public.set_shadowbanned(
  p_user_id uuid,
  p_banned  boolean,
  p_reason  text default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_changed integer;
begin
  update public.profiles
  set shadowbanned = p_banned,
      -- Cleared on unban: a reason that outlives the ban it explained is a
      -- note nobody can interpret.
      shadowbanned_at = case when p_banned then now() else null end,
      shadowbanned_reason = case when p_banned then p_reason else null end
  where id = p_user_id
    and shadowbanned is distinct from p_banned;

  get diagnostics v_changed = row_count;
  return v_changed > 0;
end;
$$;

revoke all on function public.set_shadowbanned(uuid, boolean, text) from public;
revoke all on function public.set_shadowbanned(uuid, boolean, text) from anon;
revoke all on function public.set_shadowbanned(uuid, boolean, text) from authenticated;
grant execute on function public.set_shadowbanned(uuid, boolean, text) to service_role;


-- Who is hidden, and why. The operator's view; nothing here reaches a client.
create or replace function public.shadowbanned_players()
returns table (
  id            uuid,
  display_name  text,
  banned_at     timestamptz,
  reason        text
)
language sql
stable
security definer
set search_path = ''
as $$
  select p.id, coalesce(p.display_name, 'Anonymous'), p.shadowbanned_at, p.shadowbanned_reason
  from public.profiles p
  where p.shadowbanned
  order by p.shadowbanned_at desc nulls last;
$$;

revoke all on function public.shadowbanned_players() from public;
revoke all on function public.shadowbanned_players() from anon;
revoke all on function public.shadowbanned_players() from authenticated;
grant execute on function public.shadowbanned_players() to service_role;


-- Find an account by the name an operator would actually have. Nobody reports
-- a cheater by uuid.
create or replace function public.find_players(p_query text, p_limit integer default 20)
returns table (
  id            uuid,
  display_name  text,
  shadowbanned  boolean,
  games_played  bigint
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    p.id,
    coalesce(p.display_name, 'Anonymous'),
    p.shadowbanned,
    count(gr.id)
  from public.profiles p
  left join public.game_results gr on gr.user_id = p.id
  where p.display_name ilike '%' || coalesce(p_query, '') || '%'
  group by p.id, p.display_name, p.shadowbanned
  order by count(gr.id) desc
  limit least(greatest(coalesce(p_limit, 20), 1), 100);
$$;

revoke all on function public.find_players(text, integer) from public;
revoke all on function public.find_players(text, integer) from anon;
revoke all on function public.find_players(text, integer) from authenticated;
grant execute on function public.find_players(text, integer) to service_role;
