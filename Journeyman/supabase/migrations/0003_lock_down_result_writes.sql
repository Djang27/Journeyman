-- Phase 0, final step: only the server may write a game result.
--
-- Until now the browser inserted into game_results with the anon key, and row
-- level security checked that the row *belonged to* the caller -- never that it
-- was true. Any signed-in user could insert `score: 999999` in a loop, and
-- get_leaderboard would faithfully sum it. That is the reason a global
-- leaderboard was not shippable.
--
-- The API has written results server-side since #15, so nothing legitimate
-- needs these privileges any more.
--
-- Note this is a GRANT change, not a policy change. RLS does not apply to
-- service_role, but table grants do, so the revokes below are deliberately
-- scoped to anon and authenticated. service_role -- held only by the server --
-- keeps everything.

-- 1. Take away every way of writing a result.
revoke insert, update, delete, truncate on public.game_results from anon;
revoke insert, update, delete, truncate on public.game_results from authenticated;

-- Reading stays: the Stats and History tabs select the caller's own rows, and
-- the existing "Users can read their own results" policy still scopes that.
grant select on public.game_results to anon, authenticated;

-- 2. Drop the insert policy, which is now unreachable.
--
-- Left in place it would read as though clients could still insert, which is
-- exactly the confusion that makes a security model rot. The grant above is the
-- real control; this removes the misleading second answer.
drop policy if exists "Users can insert their own results" on public.game_results;

-- 3. Same treatment for profiles.
--
-- Display names appear on the leaderboard, so a client that can rewrite its own
-- profile can put anything there. Keeping update is a deliberate choice -- users
-- need to change their display name -- but insert is not: the
-- handle_new_user trigger creates the row, and a client inserting its own would
-- only ever race that trigger.
revoke insert, delete, truncate on public.profiles from anon;
revoke insert, delete, truncate on public.profiles from authenticated;

drop policy if exists "Users can insert their own profile" on public.profiles;
