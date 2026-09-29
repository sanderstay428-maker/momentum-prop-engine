# Momentum Prop Engine (MPE)

Live prop intelligence dashboard — decision advantage, not raw lines.

## Live demo (usable today)

Open the static command center (simulated live state + Swap Engine + Bet Builder):

- **Local:** open `index.html` in a browser  
- **GitHub Pages / deploy:** root `index.html`

Production path: Next.js UI + FastAPI WebSockets + AI prediction layer below.

## Product thesis

People do not pay for information. They pay for **decision advantage** under changing game state.

Core surfaces:
1. Live Game Command Center  
2. Prop Engine (edge %, tags, confidence)  
3. Swap Engine (`IF THIS → THEN THAT`)  
4. Bet Builder (2-pick safe / 3-pick boost)  
5. Alert Feed  
6. Cross-sport toggle  

## AI prediction layer (v0)

Three first models drive every panel:

| Model | Signal | UI effect |
|-------|--------|-----------|
| Foul-impact minutes | Personal fouls → remaining minutes distribution | Embiid UNDER edge, Swap “5th foul” |
| Blowout hazard | Lead + time + pace → P(blowout) | Blowout meter, BLOWOUT SENSITIVE tags |
| Usage spike | On-ball rate residual after rotation/foul | Maxey OVER, bench OVER swaps |

Location: `backend/mpe_ai/`

## Stack

| Layer | Choice |
|-------|--------|
| Demo UI | Single-file HTML + Tailwind CDN (instant) |
| Product UI | Next.js 14 + Tailwind |
| API / realtime | FastAPI + WebSockets |
| Intelligence | Python models → edge, swap rules, combo hit % |

## Quick start — API + AI

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Endpoints:
- `GET /health`
- `GET /game/state` — live snapshot
- `GET /props` — prop cards with edge
- `POST /ai/predict` — foul / blowout / usage
- `WS /ws/live` — push updates

## Quick start — Next.js (next phase)

```bash
npx create-next-app@latest web --typescript --tailwind --eslint --app
# wire web/ to http://localhost:8000 and /ws/live
```

## Monetization gates

| Tier | Access |
|------|--------|
| Free | Basic props, delayed alerts |
| Premium | Live Swap Engine, edge %, Auto Optimize |

## Disclaimer

Demo data is simulated. Connect licensed sports / odds APIs for production. This is software infrastructure, not gambling advice.
