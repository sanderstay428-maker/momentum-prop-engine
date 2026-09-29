# Deploy MPE API on Railway

The live UI stays on Vercel. The FastAPI + LiveHub backend runs on Railway (always-on process for WebSockets).

## One-time setup (dashboard)

1. Open [https://railway.com/new](https://railway.com/new)
2. **Deploy from GitHub** → select `sanderstay428-maker/momentum-prop-engine`
3. Set **Root Directory** to `backend`
4. Railway detects the Dockerfile and deploys
5. Generate a public domain: **Settings → Networking → Generate Domain**

Optional Redis (multi-worker):

- Add Railway Redis plugin
- Set variable `REDIS_URL` to the Redis connection URL (auto-injected if you link the plugin)

## Verify

```
https://YOUR-SERVICE.up.railway.app/health
https://YOUR-SERVICE.up.railway.app/game/state
https://YOUR-SERVICE.up.railway.app/props
ws://YOUR-SERVICE.up.railway.app/ws/live
```

## CLI alternative

```bash
npm i -g @railway/cli
railway login
cd backend
railway init
railway up
railway domain
```

## Wire the Vercel UI later

Point the dashboard WebSocket client at:

```
wss://YOUR-SERVICE.up.railway.app/ws/live
```

Until then the Vercel UI runs its own client-side simulation.

## Endpoints

| Path | Role |
|------|------|
| `GET /health` | Health + LiveHub connection count |
| `GET /game/state` | Full AI snapshot |
| `GET /props` | Prop cards |
| `POST /ai/predict` | Foul / blowout / usage / edge |
| `WS /ws/live` | LiveHub push feed |
