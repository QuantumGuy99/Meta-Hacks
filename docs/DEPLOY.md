# Deploying Crucible (OPS-1)

Three pieces, three hosts. **Budget: zero dollars.** Use free tiers and credits only. Never add a payment
method or upgrade a plan for this project, and stop anything you aren't using.

| Piece | Host | Cost |
|---|---|---|
| Frontend (Next.js) | Vercel, Hobby plan | Free |
| Backend (FastAPI, WebSockets, SQLite) | Railway, trial credit | Free while the trial credit lasts; the service sleeps when idle |
| Attacks and test runs | Modal Sandboxes | Free monthly credits (+ hackathon credits if granted) |
| Models | Meta Model API | Hackathon credit ($150 per person; set a spend limit) |

## Backend on Railway

Config lives in [`railway.toml`](../railway.toml) and [`backend/Dockerfile`](../backend/Dockerfile): one
replica (sessions live in memory), health check on `/api/health`, and `sleepApplication = true`.

```bash
npx --yes @railway/cli login                 # browser sign-in
npx --yes @railway/cli init --name crucible  # once: creates the project
npx --yes @railway/cli up                    # build from this checkout and deploy
```

Then, in the Railway dashboard for the service:
1. **Volume:** add one, mounted at `/data`. SQLite writes `/data/crucible.db`, so sessions survive restarts.
2. **Variables** (paste them in the dashboard; never commit them):
   - `MODEL_API_KEY`: your Meta key.
   - `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`: copy them from `~/.modal.toml` (written by `modal token new`).
   - `CORS_ORIGINS`: the Vercel URL, e.g. `https://crucible.vercel.app`.
   - `RUNNER=modal`, `MOCK=0`, `MAX_SESSIONS_PER_IP_PER_DAY=10`.

   On Railway (or with `APP_ENV=prod`) the backend **refuses to start** if a dev-only setting is on:
   `DEFENSE_DEV_API`, `ALLOW_LOCAL_RUNNER`, `USE_CONTRIBUTOR_MODELS`, a runner other than Modal, or a
   `CORS_ORIGINS` that includes `*` or localhost. The deploy log names the setting to fix.
3. **Networking:** generate a public domain. That gives the backend URL.

Check it: `curl https://<backend-domain>/api/health` → `{"ok":true,...}`.

## Frontend on Vercel
Import the repo with the root directory set to `frontend/`, and set:
- `NEXT_PUBLIC_API_URL=https://<backend-domain>`
- `NEXT_PUBLIC_WS_URL=wss://<backend-domain>`

## Keeping it free
- Deploy as late as the plan allows (IC3 runs on the deployed build, Sun Nov 1). Until then, `make dev` locally.
- Let the backend sleep. It wakes on the next request, which takes a few seconds, so open the site once before
  recording a demo take.
- Check the remaining credit on Railway's Usage page before each demo day.
- After judging: remove the service, or the project, in the Railway dashboard.
