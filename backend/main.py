"""
Momentum Prop Engine — FastAPI backend with AI prediction layer + scalable WebSocket hub.
"""

from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from live_hub import LiveHub
from mpe_ai.predictions import (
    GameState,
    PlayerState,
    blowout_hazard,
    evaluate_swaps,
    foul_impact_minutes,
    prop_edge,
    usage_spike,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mpe.api")

hub = LiveHub(channel="mpe:live")
_producer_task: asyncio.Task | None = None

LIVE: dict[str, Any] = {
    "quarter": 3,
    "seconds": 6 * 60 + 42,
    "home": 92,
    "away": 81,
    "poss": "PHI",
    "pace_delta": 7.0,
    "players": {
        "embiid": {
            "name": "Joel Embiid", "team": "PHI", "points": 22.0, "fouls": 4,
            "minutes": 26.0, "on_ball": 0.28, "baseline_on_ball": 0.31,
            "line_pts": 28.5, "model_mean_pts": 26.8,
        },
        "maxey": {
            "name": "Tyrese Maxey", "team": "PHI", "points": 18.0, "fouls": 1,
            "minutes": 28.0, "on_ball": 0.36, "baseline_on_ball": 0.27,
            "line_pts": 24.5, "model_mean_pts": 25.4,
        },
        "cade": {
            "name": "Cade Cunningham", "team": "DET", "points": 19.0, "fouls": 2,
            "minutes": 29.0, "on_ball": 0.33, "baseline_on_ball": 0.34,
            "line_pra": 41.5, "model_mean_pra": 39.2,
        },
        "harris": {
            "name": "Tobias Harris", "team": "PHI", "points": 11.0, "fouls": 1,
            "minutes": 27.0, "on_ball": 0.14, "baseline_on_ball": 0.13,
            "line_reb": 6.5, "model_mean_reb": 7.1,
        },
    },
}


def build_game_state() -> GameState:
    return GameState(
        quarter=LIVE["quarter"],
        seconds_remaining_quarter=LIVE["seconds"],
        home_score=LIVE["home"],
        away_score=LIVE["away"],
        pace_delta=LIVE["pace_delta"],
    )


def build_players() -> list[PlayerState]:
    out: list[PlayerState] = []
    for pid, p in LIVE["players"].items():
        out.append(
            PlayerState(
                player_id=pid,
                name=p["name"],
                team=p["team"],
                points=p["points"],
                fouls=p["fouls"],
                minutes_played=p["minutes"],
                on_ball_rate=p["on_ball"],
                baseline_on_ball=p["baseline_on_ball"],
            )
        )
    return out


def compute_snapshot() -> dict[str, Any]:
    gs = build_game_state()
    players = build_players()
    blow = blowout_hazard(gs)
    props: list[dict[str, Any]] = []

    e = LIVE["players"]["embiid"]
    foul = foul_impact_minutes(e["fouls"], e["minutes"], gs.quarter, gs.seconds_remaining_quarter)
    edge_e = prop_edge("points", e["line_pts"], e["model_mean_pts"], under_bias=foul["under_bias"])
    props.append({"player_id": "embiid", "player": e["name"], "prop": "Points O/U", **edge_e, "foul": foul})

    m = LIVE["players"]["maxey"]
    us = usage_spike(
        PlayerState("maxey", m["name"], "PHI", m["points"], m["fouls"], m["minutes"], m["on_ball"], m["baseline_on_ball"])
    )
    edge_m = prop_edge("points", m["line_pts"], m["model_mean_pts"], over_bias=us["over_bias"])
    props.append({"player_id": "maxey", "player": m["name"], "prop": "Points O/U", **edge_m, "usage": us})

    c = LIVE["players"]["cade"]
    under_b = 0.35 if blow["blowout_probability"] >= 0.4 and LIVE["home"] > LIVE["away"] else 0.1
    edge_c = prop_edge("pra", c["line_pra"], c["model_mean_pra"], under_bias=under_b)
    if blow["blowout_probability"] >= 0.4:
        edge_c["tag"] = "BLOWOUT SENSITIVE"
        edge_c["color"] = "red" if edge_c["edge_pct"] < 58 else edge_c["color"]
    props.append({"player_id": "cade", "player": c["name"], "prop": "PRA", **edge_c})

    h = LIVE["players"]["harris"]
    edge_h = prop_edge("rebounds", h["line_reb"], h["model_mean_reb"], over_bias=0.15)
    props.append({"player_id": "harris", "player": h["name"], "prop": "Rebounds", **edge_h})

    swaps = evaluate_swaps(gs, players, blow)
    return {
        "matchup": "Philadelphia 76ers vs Detroit Pistons",
        "score": {"home": LIVE["home"], "away": LIVE["away"]},
        "clock": {"quarter": LIVE["quarter"], "seconds": LIVE["seconds"], "possession": LIVE["poss"]},
        "blowout": blow,
        "props": props,
        "swaps": swaps,
        "alerts": [
            f"Embiid {e['fouls']} fouls → UNDER bias {foul['under_bias']:.2f}",
            f"Blowout hazard {blow['blowout_probability']:.0%} ({blow['risk_band']})",
            f"Maxey usage spike {us['spike_score']:.2f}",
        ],
    }


def _tick_simulation() -> None:
    if random.random() < 0.4:
        if random.random() < 0.55:
            LIVE["home"] += random.choice([2, 3])
            LIVE["poss"] = "DET"
        else:
            LIVE["away"] += random.choice([2, 3])
            LIVE["poss"] = "PHI"
    if LIVE["seconds"] > 0:
        LIVE["seconds"] -= 5
    elif LIVE["quarter"] < 4:
        LIVE["quarter"] += 1
        LIVE["seconds"] = 12 * 60


async def snapshot_producer(interval: float = 4.0) -> None:
    while True:
        try:
            _tick_simulation()
            snap = compute_snapshot()
            await hub.publish({"type": "snapshot", "data": snap})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("snapshot_producer error")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _producer_task
    await hub.start()
    _producer_task = asyncio.create_task(snapshot_producer(), name="mpe-snapshot-producer")
    logger.info("MPE API up · LiveHub redis=%s channel=%s", hub.redis_enabled, hub.channel)
    yield
    if _producer_task and not _producer_task.done():
        _producer_task.cancel()
        try:
            await _producer_task
        except asyncio.CancelledError:
            pass
    await hub.stop()


app = FastAPI(title="Momentum Prop Engine API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    fouls: int = Field(ge=0, le=6)
    minutes_played: float = Field(ge=0, le=48)
    quarter: int = Field(ge=1, le=4)
    seconds_remaining_quarter: int = Field(ge=0, le=720)
    home_score: int = 0
    away_score: int = 0
    pace_delta: float = 0.0
    on_ball_rate: float = 0.3
    baseline_on_ball: float = 0.28
    market_line: float = 25.0
    model_mean: float = 24.0


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mpe-api",
        "ws": {
            "local_connections": hub.connection_count,
            "redis": hub.redis_enabled,
            "channel": hub.channel,
        },
    }


@app.get("/game/state")
def game_state() -> dict[str, Any]:
    return compute_snapshot()


@app.get("/props")
def props() -> dict[str, Any]:
    snap = compute_snapshot()
    return {"props": snap["props"], "blowout": snap["blowout"]}


@app.post("/ai/predict")
def ai_predict(body: PredictRequest) -> dict[str, Any]:
    foul = foul_impact_minutes(
        body.fouls, body.minutes_played, body.quarter, body.seconds_remaining_quarter
    )
    gs = GameState(
        body.quarter, body.seconds_remaining_quarter, body.home_score, body.away_score, pace_delta=body.pace_delta
    )
    blow = blowout_hazard(gs)
    player = PlayerState(
        "custom", "Player", "NA", 0.0, body.fouls, body.minutes_played, body.on_ball_rate, body.baseline_on_ball
    )
    usage = usage_spike(player)
    edge = prop_edge(
        "points", body.market_line, body.model_mean, under_bias=foul["under_bias"], over_bias=usage["over_bias"]
    )
    return {"foul_impact": foul, "blowout": blow, "usage": usage, "edge": edge}


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "snapshot", "data": compute_snapshot()})
        while True:
            msg = await ws.receive_text()
            if msg in ("ping", '{"type":"ping"}'):
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_live error")
    finally:
        hub.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
