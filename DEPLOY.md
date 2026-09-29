# MPE Deployment

## Live production (Vercel)

- **Production URL:** https://momentum-prop-engine-sniper4.vercel.app
- **Project:** momentum-prop-engine (team sniper4)
- **Surface:** Static live command center (client-side simulation + AI-shaped UI)

## GitHub

- **Repo:** https://github.com/sanderstay428-maker/momentum-prop-engine
- **Backend:** `backend/` — FastAPI + LiveHub + AI prediction layer

## Auto-deploy from Git (recommended)

1. Install the Vercel GitHub App: https://github.com/apps/vercel
2. Link repo `sanderstay428-maker/momentum-prop-engine` in the Vercel project
3. Every push to `main` will rebuild production

Until the GitHub App is installed, production is updated via Vercel deployment API.

## Backend (API + WebSocket)

Vercel static hosting does not run long-lived FastAPI WebSockets.
Run the API separately:

```bash
cd backend
pip install -r requirements.txt
# optional multi-worker:
# export REDIS_URL=redis://127.0.0.1:6379
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Endpoints: `/health`, `/game/state`, `/props`, `/ai/predict`, `WS /ws/live`

## System map

```
Browser  →  Vercel (index.html live UI)
                 optional: ws://API/ws/live
API      →  LiveHub → Redis (optional) → workers
AI       →  foul / blowout / usage → prop edge
```
