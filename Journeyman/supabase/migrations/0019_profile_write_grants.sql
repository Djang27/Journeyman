-- A shadowbanned player could clear their own flag.
--
-- 0017 revoked SELECT on profiles and granted it back on id and display_name,
-- and stopped there. Supabase grants UPDATE on every column by default, and the
-- "Users can update their own profile" policy allows a row where
-- auth.uid() = id -- so one PostgREST call cleared the ban:
--
--   update profiles set shadowbanned = false where id = auth.uid()
--
-- Verified against a real database before writing this, and it worked.
--
-- The same trap as 0017's own note, one privilege along: revoking SELECT says
-- nothing about UPDATE, and a column-level grant does not appear until the
-- table-level one is gone. So the write side gets the same treatment as the
-- read side -- revoke the table, grant back only what a person may set about
-- themselves, which is their display name.
--
-- INSERT stays with the handle_new_user trigger, which is security definer and
-- unaffected by these grants.

revoke update on public.profiles from anon;
revoke update on public.profiles from authenticated;

-- The one field a person owns. Not id: the RLS policy compares against it, and
-- a row whose key can be rewritten is a row that can be moved onto somebody
-- else's account.
grant update (display_name) on public.profiles to authenticated;

-- anon gets nothing. There is no signed-out edit that makes sense here, and the
-- policy would refuse it anyway -- but a grant that relies on a policy to be
-- safe is one policy edit away from not being.


-- Display names are shown on every leaderboard, so they are not free text.
-- Enforced in the database rather than in a form, because the form is not the
-- only way to reach this column.
alter table public.profiles drop constraint if exists profiles_display_name_shape;

alter table public.profiles
  add constraint profiles_display_name_shape
  check (
    display_name is null
    or (
      length(btrim(display_name)) between 2 and 24
      -- Letters, digits, and the punctuation a real name uses. Excludes the
      -- control and format characters that let one name impersonate another.
      and display_name ~ '^[[:alnum:] ._''-]+$'
      and display_name = btrim(display_name)
    )
  );
