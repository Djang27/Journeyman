# Journeyman

Journeyman is an NBA career guessing game. Given a player's name, trace the roadmap of every team they played for throughout their career — in order.

Each stop on the roadmap is one team in the player's career path. Guess the teams in order, from their first NBA team to their most recent. If a player returned to a previous team later in their career, that team appears again as a separate stop.

## Gameplay

- Start a new game to receive a random NBA player drawn from a real career database.
- Select the team for each stop on their career roadmap.
- **Green** — correct team in the correct position.
- **Yellow** — team appears elsewhere in the player's career but not here.
- **Gray** — team does not belong on the roadmap at all.
- You get up to 5 wrong guesses before the journey ends.

### Hint System

After 2 wrong guesses, a hint button unlocks. Activating it reveals the NBA conference (East or West) for each remaining stop, at a score penalty.

### Hard Mode

Toggle Hard Mode before your first guess. One wrong answer ends the game instantly. Successfully completing a journey in hard mode awards a **1.5× score multiplier**.

### Scoring

Your score is based on:
- A base value that decreases with time elapsed
- Penalties for wrong guesses and hint usage
- Hard mode multiplier applied to the final total

Scores are saved to a persistent leaderboard after each completed game.

## Features

- **Results modal** — dismissible overlay after each game showing your final score, a score breakdown, and a full post-game career timeline with correct answers highlighted and wrong guesses shown struck through.
- **Stats sidebar** — tracks win rate, best score, average score, best and average completion time, hint usage rate, current and best win streaks, and hard mode win rate across all your games.
- **Leaderboard** — global high scores stored in Supabase with Row Level Security.
- **Confetti** — fires on win, rendered above all UI layers.
- **Historical team accuracy** — season-aware resolution of renamed franchises (e.g. Charlotte Bobcats vs. Charlotte Hornets, New Orleans Hornets vs. Pelicans).

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React |
| Backend | Flask (Python) |
| Database / Auth | Supabase (PostgreSQL) |
| Player data | NBA Stats API |
| Deployment | Vercel |

## Local Development

Run the backend:

```bash
cd Journeyman/backend
python app.py
```

Run the frontend:

```bash
cd Journeyman/frontend
npm install
npm start
```

The frontend proxies API requests to the Flask backend during local development. Database schema and RLS setup for Supabase is in `Journeyman/supabase_setup.sql`.

## Player Database

Career paths are read from a committed static database:

```
Journeyman/backend/nba_players.json
```

To refresh it from the NBA Stats API (filters to players with 2+ distinct teams and a career PPG above a minimum threshold):

```bash
cd Journeyman/backend
python refresh_nba_players.py
```

To re-score and filter an existing database without re-fetching all players:

```bash
python refresh_nba_players.py --filter
```

## Deployment

This project is configured for Vercel. Use `Journeyman` as the Vercel root directory.

The GitHub Actions workflow deploys to Vercel on pushes to `main` when these repository secrets are configured:

```
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```
