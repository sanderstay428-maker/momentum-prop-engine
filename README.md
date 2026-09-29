# Momentum Prop Engine (MPE)

Live prop intelligence dashboard — decision advantage under changing game state.

## Live product

**Production:** https://momentum-prop-engine-sniper4.vercel.app

Public, no login. Client-side live simulation with Prop Engine, Swap Engine, Bet Builder, and Alert Feed.

## Repository layout

| Path | Purpose |
|------|--------|
| `index.html` | Live command-center UI |
| `backend/main.py` | FastAPI API + WebSocket gateway |
| `backend/live_hub.py` | Redis-optional multi-worker fan-out |
| `backend/mpe_ai/` | Foul impact, blowout hazard, usage spike, prop edge |
| `vercel.json` | Static deploy config |
| `DEPLOY.md` | Production and Git→Vercel notes |

## AI prediction layer

| Model | Drives |
|-------|--------|
| Foul-impact minutes | Embiid UNDER bias, 5th-foul swap |
| Blowout hazard | Blowout meter, BLOWOUT SENSITIVE tags |
| Usage spike | Maxey OVER, bench value |
| Prop edge | Edge %, OVER/UNDER, confidence color |

## Run the API locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Optional multi-worker:

```bash
export REDIS_URL=redis://127.0.0.1:6379
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

| Endpoint | Role |
|----------|------|
| `GET /health` | Status + LiveHub connection count |
| `GET /game/state` | Full AI snapshot |
| `GET /props` | Prop cards |
| `POST /ai/predict` | Foul / blowout / usage / edge |
| `WS /ws/live` | LiveHub push feed |

## Monetization thesis

Free: basic props, delayed alerts.  
Premium: live Swap Engine, edge %, Auto Optimize.

> People do not pay for information. They pay for decision advantage.

## Disclaimer

Demo data is simulated. Connect licensed sports/odds APIs for production. Software infrastructure only — not gambling advice.
