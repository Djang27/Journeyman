-- Local development seed. Runs automatically after migrations on `supabase db
-- reset`, and never anywhere else -- the hosted project does not read this file.
--
-- The point is that a fresh local database is immediately useful: the Stats,
-- History and Leaderboard tabs in Sidebar.js all read from game_results, so
-- without seed rows they render empty and cannot be worked on.
--
-- Passwords are 'password123' for every account below.

-- Users are inserted straight into auth.users rather than through the signup
-- API, because seeding runs before anything is listening. The on_auth_user_created
-- trigger from migration 0001 fires on these inserts and creates the matching
-- public.profiles rows, so those are deliberately not inserted here -- if the
-- profiles below ever go missing, that trigger has broken.
insert into auth.users (
  instance_id, id, aud, role, email,
  encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data,
  created_at, updated_at
)
values
  (
    '00000000-0000-0000-0000-000000000000',
    '11111111-1111-1111-1111-111111111111',
    'authenticated', 'authenticated', 'ada@example.com',
    extensions.crypt('password123', extensions.gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}',
    '{"display_name":"Ada"}',
    now(), now()
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '22222222-2222-2222-2222-222222222222',
    'authenticated', 'authenticated', 'grace@example.com',
    extensions.crypt('password123', extensions.gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}',
    '{"display_name":"Grace"}',
    now(), now()
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '33333333-3333-3333-3333-333333333333',
    'authenticated', 'authenticated', 'alan@example.com',
    extensions.crypt('password123', extensions.gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}',
    '{"display_name":"Alan"}',
    now(), now()
  )
on conflict (id) do nothing;

-- Identities, so the email/password login flow actually works locally.
insert into auth.identities (
  provider_id, user_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
)
select
  u.id::text, u.id,
  jsonb_build_object('sub', u.id::text, 'email', u.email),
  'email', now(), now(), now()
from auth.users u
where u.email in ('ada@example.com', 'grace@example.com', 'alan@example.com')
on conflict (provider, provider_id) do nothing;

-- Finished games. Spread across daily and unlimited, wins and losses, so the
-- streak maths in lib/scoring.js has something non-trivial to chew on and the
-- leaderboard has a real ordering rather than a single row.
insert into public.game_results (
  user_id, player_name, result, wrong_guesses, num_teams,
  time_seconds, hint_used, hard_mode, score, game_mode, created_at
)
values
  -- Ada: a current 3-game win streak, best of 3, top of the board.
  ('11111111-1111-1111-1111-111111111111', 'Vince Carter',    'win',  0, 4,  42, false, false,  988, 'daily',     now() - interval '1 day'),
  ('11111111-1111-1111-1111-111111111111', 'Chauncey Billups','win',  1, 5,  75, false, true,  1163, 'unlimited', now() - interval '2 days'),
  ('11111111-1111-1111-1111-111111111111', 'Steve Francis',   'win',  0, 3,  28, false, false, 1000, 'daily',     now() - interval '3 days'),
  ('11111111-1111-1111-1111-111111111111', 'Rasheed Wallace', 'loss', 3, 5, 190, true,  false,    0, 'unlimited', now() - interval '4 days'),

  -- Grace: mid-table, streak broken by the most recent game.
  ('22222222-2222-2222-2222-222222222222', 'Jamal Crawford',  'loss', 3, 6, 210, true,  false,    0, 'daily',     now() - interval '1 day'),
  ('22222222-2222-2222-2222-222222222222', 'Marcus Camby',    'win',  1, 4,  95, false, false,  835, 'unlimited', now() - interval '2 days'),
  ('22222222-2222-2222-2222-222222222222', 'Antawn Jamison',  'win',  0, 4,  60, true,  false,  820, 'daily',     now() - interval '3 days'),

  -- Alan: one win, one loss -- exercises the low end of the leaderboard.
  ('33333333-3333-3333-3333-333333333333', 'Drew Gooden',     'win',  2, 7, 150, true,  false,  530, 'unlimited', now() - interval '1 day'),
  ('33333333-3333-3333-3333-333333333333', 'Joe Smith',       'loss', 3, 8, 240, true,  false,    0, 'unlimited', now() - interval '5 days')
on conflict do nothing;

-- The leaderboard is a materialized view, and migrations run before this file.
-- Without a refresh here it holds a snapshot of an empty table, so a freshly
-- reset local database shows no leaderboard at all. Production is unaffected --
-- the view is populated at creation from data that already exists.
select public.refresh_leaderboard();
