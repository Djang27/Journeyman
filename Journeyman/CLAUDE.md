# Journeyman

An NBA career-path guessing game. Players are shown a player's name and must name
each team they played for, in order. Daily puzzle plus an unlimited mode.

Live on Vercel. React frontend, Flask API, Supabase (Postgres + Auth).

## Layout

```
backend/          Flask app, game logic, player selection
  app.py            routes
  game_logic.py     guess grading
  generate_players.py   daily + random player selection
  refresh_nba_players.py  one-off ingestion script (run locally only)
  nba_players.json  the player pool -- 200 players, static
  tests/            pytest suite
api/app.py        Vercel WSGI entrypoint; re-exports backend/app.py
frontend/         Create React App
  src/lib/scoring.js    score + streak maths (mirrored server-side in Phase 0)
supabase_setup.sql  schema, RLS, leaderboard function (becomes migration 0001)
docs/ROADMAP.md   the phased plan -- read before starting new work
docs/nba-data.md  player-data sourcing: current problems and the plan
```

## Commands

Run from the `Journeyman/` root unless noted.

```bash
pytest                      # backend suite
ruff check .                # lint
ruff format .               # format
cd frontend && npm test     # frontend suite
cd frontend && npm start    # dev server, proxies API to 127.0.0.1:5000
cd backend && python app.py # API on :5000
```

Dev dependencies: `pip install -r backend/requirements-dev.txt`.

## Conventions

- **Branch per deployable idea.** If merging would leave the game broken, split it.
  `main` is protected: PR required, CI must pass.
- **Conventional commits** (`feat(api):`, `test(web):`, `chore:`, `style:`).
- **Formatting sweeps get their own commit**, never mixed into feature work.
- **Additive database changes merge early and alone.** Destructive ones wait
  behind a verification gate.
- **Every bug gets a failing test before the fix.** Known-broken behaviour is
  marked `@pytest.mark.xfail(strict=True)` so it reports when it starts passing.
- **No test ever hits a live third-party API.** Ingestion tests replay recorded
  fixtures, or CI breaks whenever stats.nba.com rate-limits us.

## Current state

Phase 0 has not started. The game is **not** server-authoritative yet, and this
shapes almost every open decision:

- `/new-game` returns the full `Teams` answer array to the browser.
- `/check-guess` grades a client-supplied answer against a client-supplied
  position. It holds no state.
- Scores are computed in the browser and inserted into `game_results` with the
  anon key. RLS checks the row belongs to the caller, not that it is honest.
- The daily-replay gate is `localStorage`.

A global leaderboard is not shippable until this is fixed. See
`docs/ROADMAP.md` Phase 0.

## Gotchas

Things that have already cost time:

- **Do not add `pyproject.toml`.** Vercel's Python builder detects it and runs
  `uv lock`, which needs a `[project]` table, and the deploy fails before it
  reaches the app. Tool config lives in `pytest.ini` and `ruff.toml` for exactly
  this reason.
- **Node and npm versions are load-bearing.** `package-lock.json` was generated
  by npm 11 (Node 24). npm 10 (Node 22) resolves the tree differently and its
  `npm ci` rejects the lock. CI is pinned to Node 24 to match. Do not regenerate
  the lock under npm 10 -- it silently drops `resolved` and `integrity` from
  every entry.
- **Three Python versions are in play**: local 3.9, CI 3.12, Vercel 3.12. This is
  why `B905` (`zip(strict=)`) is ignored in `ruff.toml`. Pinning is a
  `chore/environments` task — Vercel's build log confirms it reads
  `.python-version`, and `.nvmrc`/`engines` for Node, so those are the levers.
  Upgrading local Python to 3.12 lets the `B905` ignore be removed.
- **Vercel builds every pushed commit.** A red preview deployment may be for an
  older commit on a branch that has since been fixed — check which SHA it built
  before debugging it.
- **CI is path-filtered to `Journeyman/**`.** The repo also holds unrelated
  projects. A PR touching nothing under `Journeyman/` will never run the required
  checks and will block forever waiting for them.
- **`daily_player()` is `md5(date) % len(players)`.** Editing `nba_players.json`
  reshuffles every future daily puzzle. There is a test that proves this.
- **The repo was renamed** from `VSCODE` to `Journeyman` on GitHub. Old remote
  URLs still work via redirect.
