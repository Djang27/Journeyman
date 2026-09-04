-- Give every existing account a profile.
--
-- The leaderboard joins profiles to game_results, and production has thirty
-- results against zero profiles -- so it has been returning an empty list since
-- launch. Nobody noticed because an empty leaderboard looks like a new game
-- rather than a broken query.
--
-- The handle_new_user trigger creates a profile on signup, but it only fires for
-- accounts created after it existed. Anyone who signed up before that has no
-- profile and is invisible to every aggregate.
--
-- Idempotent, so it is safe wherever it lands and safe to re-run.

insert into public.profiles (id, display_name)
select
  u.id,
  coalesce(
    u.raw_user_meta_data ->> 'display_name',
    split_part(u.email, '@', 1),
    'Anonymous'
  )
from auth.users u
where not exists (select 1 from public.profiles p where p.id = u.id)
on conflict (id) do nothing;

-- The aggregate is a snapshot, so it has to be rebuilt for the backfill to show.
select public.refresh_leaderboard();
