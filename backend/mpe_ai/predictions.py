"""
AI prediction layer for Momentum Prop Engine.

v0 models are interpretable heuristics calibrated for product wiring.
Replace internals with trained models without changing call signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GameState:
    quarter: int
    seconds_remaining_quarter: int
    home_score: int
    away_score: int
    home_team: str = "PHI"
    away_team: str = "DET"
    pace_delta: float = 0.0  # possessions vs season average, last N min


@dataclass
class PlayerState:
    player_id: str
    name: str
    team: str
    points: float
    fouls: int
    minutes_played: float
    on_ball_rate: float  # 0-1 recent window
    baseline_on_ball: float
    is_starter: bool = True


def foul_impact_minutes(
    fouls: int,
    minutes_played: float,
    quarter: int,
    seconds_remaining_quarter: int,
    baseline_minutes: float = 34.0,
) -> dict[str, float]:
    """Estimate remaining minutes and minutes multiplier given foul trouble."""
    game_clock_left = max(0, (4 - quarter) * 12 * 60 + seconds_remaining_quarter)
    remaining_frac = game_clock_left / (48 * 60)

    if fouls <= 2:
        mult = 1.0
        risk = 0.1
    elif fouls == 3:
        mult = 0.92 if quarter <= 2 else 0.88
        risk = 0.35
    elif fouls == 4:
        mult = 0.72 if quarter <= 3 else 0.55
        risk = 0.7
    else:
        mult = 0.35
        risk = 0.95

    if fouls >= 3 and quarter <= 2:
        mult *= 0.9
        risk = min(1.0, risk + 0.1)

    expected_remaining = max(0.0, (baseline_minutes - minutes_played) * mult)
    under_bias = min(1.0, risk * 0.85 + (1.0 - mult) * 0.5)

    return {
        "expected_remaining_minutes": round(expected_remaining, 2),
        "minutes_multiplier": round(mult, 3),
        "foul_risk": round(risk, 3),
        "under_bias": round(under_bias, 3),
        "remaining_frac": round(remaining_frac, 3),
    }


def blowout_hazard(state: GameState) -> dict[str, float]:
    """P(game finishes as blowout) proxy from lead, time, pace."""
    lead = abs(state.home_score - state.away_score)
    game_clock_left = max(0, (4 - state.quarter) * 12 * 60 + state.seconds_remaining_quarter)
    time_frac_left = game_clock_left / (48 * 60)

    margin_term = min(0.75, lead / 28.0)
    time_term = (1.0 - time_frac_left) * 0.35
    pace_term = max(0.0, min(0.15, state.pace_delta / 20.0))

    p = max(0.05, min(0.92, margin_term + time_term + pace_term))
    if lead < 6:
        p *= 0.45
    elif lead < 10:
        p *= 0.75

    return {
        "blowout_probability": round(p, 3),
        "lead": float(lead),
        "time_frac_left": round(time_frac_left, 3),
        "risk_band": "high" if p >= 0.55 else "moderate" if p >= 0.32 else "low",
    }


def usage_spike(player: PlayerState) -> dict[str, float]:
    """Detect elevated on-ball usage vs baseline."""
    residual = player.on_ball_rate - player.baseline_on_ball
    spike = max(0.0, min(1.0, residual / 0.12))
    over_bias = spike * 0.8
    return {
        "usage_residual": round(residual, 4),
        "spike_score": round(spike, 3),
        "over_bias": round(over_bias, 3),
    }


def prop_edge(
    side: str,
    market_line: float,
    model_mean: float,
    model_sd: float = 4.5,
    under_bias: float = 0.0,
    over_bias: float = 0.0,
) -> dict[str, Any]:
    """Convert model mean vs line into edge % and recommendation."""
    import math

    adj_mean = model_mean - under_bias * model_sd * 0.6 + over_bias * model_sd * 0.5
    z = (adj_mean - market_line) / max(model_sd, 0.5)
    p_over = 1.0 / (1.0 + math.exp(-1.2 * z))
    if p_over >= 0.5:
        rec = "OVER"
        edge = p_over * 100
        trend = "\u2191"
    else:
        rec = "UNDER"
        edge = (1.0 - p_over) * 100
        trend = "\u2193"

    if edge >= 60:
        color, tag = "green", "FORMING EDGE"
    elif edge >= 55:
        color, tag = "yellow", "VOLATILE"
    else:
        color, tag = "red", "BLOWOUT SENSITIVE"

    return {
        "side": side,
        "line": market_line,
        "model_mean": round(adj_mean, 2),
        "edge_pct": round(edge, 1),
        "recommendation": rec,
        "trend": trend,
        "color": color,
        "tag": tag,
        "z": round(z, 3),
    }


def evaluate_swaps(
    state: GameState,
    players: list[PlayerState],
    blowout: dict[str, float],
) -> list[dict[str, Any]]:
    """Generate IF THIS -> THEN THAT rules with armed flags."""
    lead = state.home_score - state.away_score
    fouls = {p.player_id: p.fouls for p in players}
    embiid_fouls = fouls.get("embiid", 0)

    rules = [
        {
            "if": "Lead > 15",
            "then": "Switch Embiid to UNDER 28.5",
            "armed": lead > 15 or (lead > 12 and blowout["blowout_probability"] >= 0.45),
        },
        {
            "if": "Close game inside 6",
            "then": "Add Maxey OVER 24.5",
            "armed": abs(lead) <= 6 and state.quarter >= 4,
        },
        {
            "if": "Bench substitution spike",
            "then": "Add DET bench points OVER",
            "armed": lead >= 12 and blowout["blowout_probability"] >= 0.4,
        },
        {
            "if": "Embiid 5th foul",
            "then": "Kill Embiid minutes props",
            "armed": embiid_fouls >= 5,
        },
    ]
    return rules
