# playmmf

A play-money betting app for a school soccer tournament. It uses proportional
outcome pools with locked-in payouts so odds are transparent and each wager's
potential payout is fixed at the moment it is placed.

## How it works

- Each match is a **zápas** with 2+ possible **results** (e.g. "Team A
  wins" / "Team B wins").
- Odds move automatically as people place wagers — no manual odds-setting
  needed. Prices always sum to 100% and represent the crowd's implied
  probability.
- Every player starts with 10,000 play points (`STARTING_BALANCE` in
  `backend/app/crud.py`).
- Players register with a school email ending in `@gbn.cz` or `@gymbn.cz`, a
  username, and a password. They then log in with that school email.
- Each outcome starts with a pool equal to the match's liquidity value `b`.
  Current odds are the total pool divided by that outcome's pool.
- A wager locks its payout immediately. Later wagers can move the displayed
  odds, but never change an existing wager's payout.
- A player may have only one open outcome position per match, preventing
  risk-free hedging across multiple outcomes.

## Project layout

```
backend/    FastAPI + SQLAlchemy (SQLite) API
  app/
    lmsr.py       the pricing engine (pure math, thoroughly tested)
    models.py     database tables
    crud.py       business logic (wagers, resolving, leaderboard)
    schemas.py    request/response shapes
    main.py       API routes
  tests/          pytest suite (engine + full API flow)
frontend/   React (Vite) single-page app
```

## Running it locally

### Backend

```bash
cd backend
python -m venv .venv   # or use your existing shared venv
source .venv/bin/activate
pip install -r requirements.txt

# ADMIN_KEY protects match creation, administration, and resolution — pick something and share
# it only with whoever is running the tournament.
ADMIN_KEY=your-secret-here uvicorn app.main:app --reload

# For a frontend served from another origin, configure CORS before starting
# Uvicorn. Multiple origins can be comma-separated.
# Windows PowerShell: $env:CORS_ORIGINS="http://localhost:5173"
```

The API runs on `http://localhost:8000`. Interactive docs are at
`http://localhost:8000/docs` (FastAPI's auto-generated Swagger UI) — handy
for testing endpoints before the frontend is wired up.

Run the tests any time you change the engine or API:

```bash
cd backend
pytest -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` (Vite's default) and talks to the backend
at `http://localhost:8000` by default. To point it elsewhere (e.g. once
deployed), copy `.env.example` to `.env` and set `VITE_API_URL`.

## Using it

1. Anyone opens the frontend and registers with a school email, username,
  and password. Only `@gbn.cz` and `@gymbn.cz` addresses are accepted.
2. Whoever is running the tournament enters the `ADMIN_KEY` in the Admin
  tab, then creates a match per game (title + possible results + a
  initial pool value `b`).
3. The Admin tab can grant or remove points from every player, ban or unban a
  player by school email, permanently delete matches, and perform a factory
  reset. Balance changes are recorded in transaction history; balance removal
  is rejected if it would make any account negative.
4. Players select an outcome, enter a stake of at least 100 points, review the
  exact gross payout and multiplier, and confirm the wager. Prices update live
  after every wager (the app polls every 5 seconds).
5. When a match ends, the admin picks the winning outcome from the
  dropdown on that match's card — this resolves the match and pays out
   winners automatically.
6. Leaderboard tab ranks players by cash balance only.

## Choosing `b` (the initial pool value)

Bigger `b` = more stable odds because each wager is smaller relative to the
starting pools. The admin form defaults to `b = 5,000`, a reasonable starting
point for 10,000-point accounts and many participants. Use `b = 1,000` for
faster odds movement or `b = 10,000` for steadier odds. There is no maximum
loss bound in this pool model, so choose `b` with the tournament's total
possible payouts in mind.

## Notes / things to decide before running it for real

- **Admin key**: currently a single shared secret via the `ADMIN_KEY`
  environment variable, checked via an `X-Admin-Key` header. Fine for a
  small trusted group; swap for real accounts/auth if this grows.
- **Existing database**: the new account fields are added at startup, but
  existing username-only accounts cannot log in. The ban field and pool-bet
  fields are added automatically at startup. Existing LMSR positions are
  preserved with a legacy fallback payout; new matches and wagers use pool
  odds and locked payouts.
- **Persistence**: SQLite file (`backend/tournament.db`), fine at this
  scale. Back it up if you care about the results.
- **Deployment**: both are plain processes (Uvicorn + a static Vite
  build) — deploy however you'd deploy any small FastAPI + SPA app (a
  single VM, a school server, etc.). `npm run build` produces static
  files in `frontend/dist` you can serve from anything.
