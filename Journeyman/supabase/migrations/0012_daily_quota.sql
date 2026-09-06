-- Five free unlimited games a day.
--
-- A product rule, not a rate limit, and the difference decides where it lives.
-- A rate limit is about abuse and may be approximate: the worst case of a
-- fixed window is someone getting 2x across a boundary, which costs nothing. A
-- quota is about money. Handing out a sixth free game because two requests
-- raced is a bug someone can farm, so this counts in one statement like the
-- limiter does, and in Postgres rather than anywhere evictable.
--
-- ## What it does and does not apply to
--
-- The daily puzzle is free forever and needs no account -- it is the whole
-- acquisition funnel, and a wall in front of it would be the most expensive
-- possible place to put one. This counts unlimited mode only.
--
-- ## Anonymous callers
--
-- A quota keyed only on user id is bypassed by signing out, which would make it
-- decorative. So anonymous play counts against a hashed IP, the same coarse
-- handle the rate limiter uses. That is imperfect -- a shared network shares a
-- quota, a new IP is a new allowance -- and it is the honest ceiling for a rule
-- that must apply to people who have not told you who they are.
--
-- ## The day boundary
--
-- Eastern, matching the daily puzzle rollover, so "today" means one thing in
-- this product. A rolling 24-hour window would be more precise and worse: a
-- player who cannot work out when their games come back assumes they are gone.
-- The date is passed in rather than computed here, because the application
-- already owns that calculation and two implementations of "today" would
-- eventually disagree.

create table if not exists public.game_quota (
  game_slug   text    not null,
  -- Who this counts against: 'user:<uuid>' or 'ip:<sha256 prefix>'. Opaque
  -- here, like the rate limiter's bucket -- the application decides what
  -- deserves its own allowance.
  subject     text    not null,
  quota_date  date    not null,
  used        integer not null default 0,
  primary key (game_slug, subject, quota_date)
);

-- Yesterday's rows are dead weight, and this is what a prune would scan.
create index if not exists game_quota_by_date
  on public.game_quota (quota_date);

-- Server only. A client that could write here would grant itself free games.
alter table public.game_quota enable row level security;


-- Spend one game against a subject's allowance and say whether it was allowed.
--
-- Atomic in a single statement, for the reason above: two concurrent starts
-- must not both read four-used and both conclude they are the fifth.
--
-- Counts every attempt, including refused ones, exactly as the rate limiter
-- does. `used` can therefore exceed the limit; `remaining` is clamped so the UI
-- never shows a negative. Not refunding an abandoned game is deliberate --
-- start, look at the player, abandon, repeat would otherwise be free.
create or replace function public.consume_quota(
  p_game_slug  text,
  p_subject    text,
  p_quota_date date,
  p_limit      integer
)
returns table (allowed boolean, used integer, remaining integer)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_used integer;
begin
  insert into public.game_quota as q (game_slug, subject, quota_date, used)
  values (p_game_slug, p_subject, p_quota_date, 1)
  on conflict (game_slug, subject, quota_date)
    do update set used = q.used + 1
  returning q.used into v_used;

  return query select
    v_used <= p_limit,
    v_used,
    greatest(p_limit - v_used, 0);
end;
$$;

-- Revoked by name: default privileges grant EXECUTE to anon and authenticated
-- separately, and those survive a revoke from PUBLIC. A client able to call
-- this could burn someone else's allowance, or read whether they have any left.
revoke all on function public.consume_quota(text, text, date, integer) from public;
revoke all on function public.consume_quota(text, text, date, integer) from anon;
revoke all on function public.consume_quota(text, text, date, integer) from authenticated;
grant execute on function public.consume_quota(text, text, date, integer) to service_role;


-- Read an allowance without spending it, for showing "3 games left" before the
-- player commits to anything.
create or replace function public.quota_used(
  p_game_slug  text,
  p_subject    text,
  p_quota_date date
)
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (select q.used from public.game_quota q
      where q.game_slug = p_game_slug
        and q.subject = p_subject
        and q.quota_date = p_quota_date),
    0
  );
$$;

revoke all on function public.quota_used(text, text, date) from public;
revoke all on function public.quota_used(text, text, date) from anon;
revoke all on function public.quota_used(text, text, date) from authenticated;
grant execute on function public.quota_used(text, text, date) to service_role;
