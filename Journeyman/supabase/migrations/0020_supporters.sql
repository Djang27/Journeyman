-- Who paid, shown on the front page.
--
-- Published by default, with a way out. That is the owner's call and it is a
-- real disclosure, so the parts that make an opt-out meaningful are built in
-- rather than promised:
--
--   * the flag defaults to true, so the default is publication
--   * a person can clear it themselves, from their account
--   * the purchase panel says so before the money moves, so nobody discovers
--     it afterwards
--
-- An opt-out nobody can find is not an opt-out. The first two are here; the
-- third is in the client.
--
-- Only a display name is ever exposed. Not the email, not when they paid, not
-- what they paid -- a name is already public on every leaderboard, and the new
-- fact is only that this person supported the game.

alter table public.profiles
  add column if not exists supporter_public boolean not null default true;

comment on column public.profiles.supporter_public is
  'Whether this supporter is named on the front page. Defaults to true; the person can clear it.';

-- 0019 revoked UPDATE on profiles and granted back only display_name, which
-- was the fix for a shadowbanned player clearing their own flag. This is the
-- second column a person may set about themselves, and it is granted by name
-- for the same reason: the table-level grant is what let the last one through.
grant update (supporter_public) on public.profiles to authenticated;


-- The list, as anybody may see it.
--
-- security definer because it reads entitlements, which no client may touch --
-- the answer is public, the table is not. Three exclusions, and each matters:
-- a revoked entitlement is not a supporter, somebody hidden from every board is
-- hidden from this one too, and an opt-out is an opt-out.
create or replace function public.supporters(limit_count integer default 60)
returns table (display_name text)
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(p.display_name, 'Anonymous')
  from public.entitlements e
  join public.profiles p on p.id = e.user_id
  where e.revoked_at is null
    and p.supporter_public
    and not p.shadowbanned
  -- Oldest first: the people who backed it earliest are the ones worth naming
  -- first, and a stable order stops the strip reshuffling on every load.
  order by e.granted_at asc
  limit least(greatest(coalesce(limit_count, 60), 1), 200);
$$;

revoke all on function public.supporters(integer) from public;
grant execute on function public.supporters(integer) to anon;
grant execute on function public.supporters(integer) to authenticated;


-- How many there are, including the ones who opted out. Shown as a count when
-- somebody wants the number without the names, and it is the honest total:
-- opting out removes a name from the strip, not a person from the tally.
create or replace function public.supporter_count()
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select count(*)::integer
  from public.entitlements e
  join public.profiles p on p.id = e.user_id
  where e.revoked_at is null
    and not p.shadowbanned;
$$;

revoke all on function public.supporter_count() from public;
grant execute on function public.supporter_count() to anon;
grant execute on function public.supporter_count() to authenticated;
