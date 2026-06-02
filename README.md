# Journeyman

Journeyman is an NBA guessing game where you are given a player's name and have to trace the roadmap of teams they played for throughout their career.

Each stop on the roadmap is one team in the player's career path. Guess the teams in order, from their first NBA team to their most recent. If a player returned to a previous team later in their career, that team appears again as a separate stop.

## How It Works

- Start a new game to receive a random NBA player.
- Select the team for each stop on their career roadmap.
- A correct team in the correct position is marked green.
- A team that appears elsewhere in the player's career is marked yellow.
- A team that does not belong on the roadmap is marked gray.

## Tech Stack

- React frontend
- Flask backend
- NBA Stats data for player career histories
- Vercel deployment configuration

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

The frontend proxies API requests to the Flask backend during local development.

## Player Data

The app reads NBA career paths from a committed static database:

```text
Journeyman/backend/nba_players.json
```

To refresh that database from NBA Stats, run:

```bash
cd Journeyman/backend
python refresh_nba_players.py
```

## Deployment

This project is configured for Vercel. Use `Journeyman` as the Vercel root directory.

The GitHub Actions workflow deploys to Vercel on pushes to `main` when these repository secrets are configured:

```text
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```
