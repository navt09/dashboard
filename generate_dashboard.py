#!/usr/bin/env python3
"""
Automated Prop-Bet Scouting Dashboard (NBA + NFL)
- Pulls real player prop lines from The Odds API (free tier + api key required)
- Pulls injuries from ESPN (free) and filters out injured/inactive players
- Scores BOTH Over and Under using your rules-based edge model
- Generates AI_Prediction_Engine.html
"""

import os
import math
import json
import statistics
from datetime import datetime as dt, timezone
import requests

# =============================================================================
# YOUR EXISTING STATIC DATA (PASTED IN)
# =============================================================================

NBA_PLAYERS_DATA = {
    "Shai Gilgeous-Alexander": {
        "recent_ppg": 28.2, "recent_rpg": 4.8, "recent_apg": 7.2, "recent_3pm": 2.1, "recent_stl": 1.4, "recent_blk": 0.6,
        "usage_rate": 31.2, "efficiency": 0.62, "fgm": 10.2, "ft_rate": 0.28, "per_minute": 1.84,
        "home_away_split": 1.05, "back_to_back": False, "foul_trouble_risk": 0.2, "rest_days": 1, "red_zone_usage": 0.35, "load_managed": False
    },
    "Nikola Jokic": {
        "recent_ppg": 28.4, "recent_rpg": 11.2, "recent_apg": 9.8, "recent_3pm": 1.3, "recent_stl": 1.1, "recent_blk": 0.7,
        "usage_rate": 35.1, "efficiency": 0.68, "fgm": 10.2, "ft_rate": 0.35, "per_minute": 1.89,
        "home_away_split": 1.02, "back_to_back": False, "foul_trouble_risk": 0.15, "rest_days": 2, "red_zone_usage": 0.42, "load_managed": False
    },
    "Anthony Edwards": {
        "recent_ppg": 23.1, "recent_rpg": 4.5, "recent_apg": 3.2, "recent_3pm": 2.8, "recent_stl": 1.1, "recent_blk": 0.4,
        "usage_rate": 27.5, "efficiency": 0.58, "fgm": 8.3, "ft_rate": 0.25, "per_minute": 1.72,
        "home_away_split": 1.03, "back_to_back": True, "foul_trouble_risk": 0.25, "rest_days": 0, "red_zone_usage": 0.28, "load_managed": False
    },
    "Luka Doncic": {
        "recent_ppg": 33.2, "recent_rpg": 9.1, "recent_apg": 6.8, "recent_3pm": 2.5, "recent_stl": 1.0, "recent_blk": 0.5,
        "usage_rate": 33.8, "efficiency": 0.60, "fgm": 11.5, "ft_rate": 0.32, "per_minute": 1.95,
        "home_away_split": 1.08, "back_to_back": False, "foul_trouble_risk": 0.30, "rest_days": 1, "red_zone_usage": 0.38, "load_managed": True
    },
    "Jayson Tatum": {
        "recent_ppg": 27.5, "recent_rpg": 8.4, "recent_apg": 4.2, "recent_3pm": 2.4, "recent_stl": 1.2, "recent_blk": 0.8,
        "usage_rate": 32.1, "efficiency": 0.61, "fgm": 9.8, "ft_rate": 0.30, "per_minute": 1.88,
        "home_away_split": 1.04, "back_to_back": False, "foul_trouble_risk": 0.22, "rest_days": 1, "red_zone_usage": 0.40, "load_managed": False
    },
    "Kevin Durant": {
        "recent_ppg": 29.8, "recent_rpg": 6.2, "recent_apg": 4.5, "recent_3pm": 2.2, "recent_stl": 0.9, "recent_blk": 1.3,
        "usage_rate": 30.5, "efficiency": 0.65, "fgm": 11.0, "ft_rate": 0.22, "per_minute": 1.92,
        "home_away_split": 1.01, "back_to_back": False, "foul_trouble_risk": 0.18, "rest_days": 1, "red_zone_usage": 0.36, "load_managed": False
    },
    "Giannis Antetokounmpo": {
        "recent_ppg": 31.2, "recent_rpg": 12.8, "recent_apg": 5.4, "recent_3pm": 0.8, "recent_stl": 1.0, "recent_blk": 1.1,
        "usage_rate": 34.2, "efficiency": 0.67, "fgm": 12.1, "ft_rate": 0.42, "per_minute": 1.98,
        "home_away_split": 1.06, "back_to_back": False, "foul_trouble_risk": 0.28, "rest_days": 1, "red_zone_usage": 0.44, "load_managed": False
    },
    "LeBron James": {
        "recent_ppg": 24.6, "recent_rpg": 7.8, "recent_apg": 7.2, "recent_3pm": 1.9, "recent_stl": 1.2, "recent_blk": 0.5,
        "usage_rate": 28.1, "efficiency": 0.60, "fgm": 9.1, "ft_rate": 0.28, "per_minute": 1.68,
        "home_away_split": 1.02, "back_to_back": False, "foul_trouble_risk": 0.15, "rest_days": 2, "red_zone_usage": 0.32, "load_managed": True
    },
}

NFL_PLAYERS_DATA = {
    "Josh Allen": {
        "recent_pass_yds": 278, "recent_pass_td": 2.2, "recent_int": 0.8, "recent_rush_yds": 45, "recent_rush_td": 0.4,
        "completion_pct": 0.65, "td_rate": 2.2, "int_rate": 0.8, "route_participation": 0.88, "back_to_back": False,
        "weather_impact": 0.95, "red_zone_attempts": 3.2, "pressure_to_sack": 0.15, "rest_days": 3, "injury_risk": 0.1
    },
    "Patrick Mahomes": {
        "recent_pass_yds": 285, "recent_pass_td": 2.8, "recent_int": 0.6, "recent_rush_yds": 38, "recent_rush_td": 0.3,
        "completion_pct": 0.68, "td_rate": 2.8, "int_rate": 0.6, "route_participation": 0.92, "back_to_back": False,
        "weather_impact": 1.0, "red_zone_attempts": 3.5, "pressure_to_sack": 0.12, "rest_days": 3, "injury_risk": 0.05
    },
    "Lamar Jackson": {
        "recent_pass_yds": 245, "recent_pass_td": 2.1, "recent_int": 0.5, "recent_rush_yds": 65, "recent_rush_td": 0.6,
        "completion_pct": 0.66, "td_rate": 2.1, "int_rate": 0.5, "route_participation": 0.85, "back_to_back": False,
        "weather_impact": 0.90, "red_zone_attempts": 2.8, "pressure_to_sack": 0.18, "rest_days": 3, "injury_risk": 0.15
    },
    "Jalen Hurts": {
        "recent_pass_yds": 268, "recent_pass_td": 2.4, "recent_int": 0.7, "recent_rush_yds": 55, "recent_rush_td": 0.5,
        "completion_pct": 0.67, "td_rate": 2.4, "int_rate": 0.7, "route_participation": 0.89, "back_to_back": False,
        "weather_impact": 0.92, "red_zone_attempts": 3.1, "pressure_to_sack": 0.14, "rest_days": 3, "injury_risk": 0.08
    },
    "Travis Kelce": {
        "recent_rec": 7.2, "recent_rec_yds": 85, "recent_rec_td": 0.8, "targets": 9.5, "route_participation": 0.94,
        "back_to_back": False, "weather_impact": 1.0, "red_zone_targets": 1.8, "rest_days": 3, "injury_risk": 0.12
    },
}

OPPONENT_DEFENSE = {
    "nba": {
        "LAL": {"ppg_allowed": 112.3, "perimeter_rank": 14, "interior_rank": 8, "pace_adjust": 1.02},
        "GS": {"ppg_allowed": 110.8, "perimeter_rank": 18, "interior_rank": 12, "pace_adjust": 1.05},
        "HOU": {"ppg_allowed": 109.2, "perimeter_rank": 10, "interior_rank": 23, "pace_adjust": 1.08},
        "DEN": {"ppg_allowed": 108.5, "perimeter_rank": 5, "interior_rank": 15, "pace_adjust": 0.98},
    },
    "nfl": {
        "MIA": {"pass_yds_allowed": 262, "pass_rank": 16, "run_rank": 8, "pressure_rate": 0.28},
        "BUF": {"pass_yds_allowed": 248, "pass_rank": 12, "run_rank": 5, "pressure_rate": 0.35},
        "KC": {"pass_yds_allowed": 252, "pass_rank": 14, "run_rank": 10, "pressure_rate": 0.32},
    }
}

REFEREE_TENDENCIES = {
    "nba": {"tight_whistle": 0.8, "ft_rate_boost": 1.15, "foul_calls_per_game": 28},
    "nfl": {"dpi_rate": 0.32, "holding_rate": 0.28, "flag_rate": 1.08}
}

# =============================================================================
# CONFIG
# =============================================================================

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
ODDS_API_HOST = "https://api.the-odds-api.com"

# The Odds API sports keys (from v4 docs)
NBA_SPORT_KEY = "basketball_nba"
NFL_SPORT_KEY = "americanfootball_nfl"

# Player prop markets (official market keys list includes these) :contentReference[oaicite:2]{index=2}
NBA_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_blocks",
    "player_steals",
    "player_blocks_steals",
    "player_turnovers",
    "player_points_rebounds_assists",
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
    "player_field_goals",
    "player_frees_made",
]
NFL_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_rush_yds",
    "player_rush_attempts",
    "player_receptions",
    "player_reception_yds",
    "player_reception_tds",
    # combos available in API, but you chose "A = real lines only" — these ARE real lines, so we include:
    "player_pass_rush_yds",
    "player_rush_reception_yds",
    "player_pass_rush_reception_yds",
]

# Map Odds API market keys -> your internal prop_type names
NBA_MARKET_TO_PROP = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "3_pointers",
    "player_blocks": "blocks",
    "player_steals": "steals",
    "player_blocks_steals": "stl_blk",
    "player_turnovers": "turnovers",
    "player_points_rebounds_assists": "pts_reb_ast",
    "player_points_rebounds": "pts_reb",
    "player_points_assists": "pts_ast",
    "player_rebounds_assists": "reb_ast",
    "player_field_goals": "field_goals",
    "player_frees_made": "free_throws",
}

NFL_MARKET_TO_PROP = {
    "player_pass_yds": "pass_yards",
    "player_pass_tds": "pass_td",
    "player_pass_interceptions": "int",
    "player_rush_yds": "rush_yards",
    "player_rush_attempts": "carries",
    "player_receptions": "receptions",
    "player_reception_yds": "rec_yards",
    "player_reception_tds": "rec_td",
    "player_pass_rush_yds": "pass_rush_yards",
    "player_rush_reception_yds": "rush_rec_yards",
    "player_pass_rush_reception_yds": "pass_rush_rec_yards",
}

# =============================================================================
# ESPN INJURIES (FREE)
# =============================================================================

def _safe_get(url, timeout=12, headers=None):
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return r.json()

def fetch_espn_team_map(league: str):
    """
    Returns dict: {team_display_name: {"id": "...", "abbr": "..."}}
    """
    if league == "nba":
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    else:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

    data = _safe_get(url)
    out = {}
    for t in data.get("sports", [])[0].get("leagues", [])[0].get("teams", []):
        team = t.get("team", {})
        out[team.get("displayName", "")] = {
            "id": team.get("id", ""),
            "abbr": team.get("abbreviation", ""),
        }
    return out

def fetch_espn_injuries(league: str):
    """
    Returns:
      injured_names: set of player names that are OUT/INACTIVE/DOUBTFUL/etc.
      details: dict name -> (status, teamabbr)
    Uses ESPN team endpoint with enable=injuries.
    """
    team_map = fetch_espn_team_map(league)
    injured = set()
    details = {}

    for team_name, meta in team_map.items():
        team_id = meta["id"]
        abbr = meta["abbr"]
        if not team_id:
            continue

        if league == "nba":
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}?enable=injuries"
        else:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}?enable=injuries"

        try:
            data = _safe_get(url)
            injuries = data.get("team", {}).get("injuries", []) or data.get("injuries", [])
            for inj in injuries:
                athlete = inj.get("athlete", {})
                name = athlete.get("displayName")
                status = inj.get("status", {}).get("name") or inj.get("status") or ""
                status_upper = str(status).upper()

                # treat these as "do not play"
                if any(x in status_upper for x in ["OUT", "INACTIVE", "DOUBTFUL", "DNP", "IR"]):
                    if name:
                        injured.add(name)
                        details[name] = (status, abbr)
        except Exception:
            # don’t hard fail if one team endpoint errors
            continue

    return injured, details

# Fallback injuries (keep yours; you can update)
FALLBACK_INJURIES = {
    "nba": {"LAL": [{"player": "Anthony Davis", "status": "Out", "impact": 0.20}]},
    "nfl": {"KC": [{"player": "Patrick Mahomes", "status": "Out", "impact": 0.25}]},
}

def build_injury_sets():
    nba_injured, nba_details = fetch_espn_injuries("nba")
    nfl_injured, nfl_details = fetch_espn_injuries("nfl")

    # Also include fallback list by player name
    for abbr, lst in FALLBACK_INJURIES.get("nba", {}).items():
        for p in lst:
            nba_injured.add(p["player"])
            nba_details[p["player"]] = (p.get("status", "Out"), abbr)
    for abbr, lst in FALLBACK_INJURIES.get("nfl", {}).items():
        for p in lst:
            nfl_injured.add(p["player"])
            nfl_details[p["player"]] = (p.get("status", "Out"), abbr)

    return (nba_injured, nba_details), (nfl_injured, nfl_details)

# =============================================================================
# THE ODDS API: EVENTS + PLAYER PROP LINES
# =============================================================================

def require_api_key():
    if not ODDS_API_KEY:
        raise RuntimeError(
            "Missing ODDS_API_KEY. Add it as a GitHub Secret or env var."
        )

def oddsapi_get_events(sport_key: str):
    """
    Uses /v4/sports/{sport}/events (does not count against quota) :contentReference[oaicite:3]{index=3}
    """
    require_api_key()
    url = f"{ODDS_API_HOST}/v4/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY, "dateFormat": "iso"}
    return requests.get(url, params=params, timeout=15).json()

def oddsapi_get_event_props(sport_key: str, event_id: str, markets: list[str]):
    """
    Uses /v4/sports/{sport}/events/{eventId}/odds for player props :contentReference[oaicite:4]{index=4}
    """
    require_api_key()
    url = f"{ODDS_API_HOST}/v4/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def normalize_player_name(name: str) -> str:
    """
    Try to align odds-feed player names to your dictionary keys.
    Your player DB is small (8 NBA, 5 NFL), so we match by exact or simplified.
    """
    if not name:
        return ""
    s = name.strip()
    # Fix common variations if needed
    fixes = {
        "Shai Gilgeous Alexander": "Shai Gilgeous-Alexander",
    }
    if s in fixes:
        return fixes[s]
    return s

def parse_event_prop_lines(event_odds_json: dict):
    """
    Returns list of dicts:
      {player, market_key, line, over_price, under_price}
    We compute a consensus line as the median of 'point' across books for the same player+market.
    """
    lines_by = {}  # (player, market_key) -> list of points, plus prices if present
    price_by = {}  # (player, market_key, side, point) -> list(prices)

    for book in event_odds_json.get("bookmakers", []):
        for m in book.get("markets", []):
            mkey = m.get("key")
            for out in m.get("outcomes", []):
                player = normalize_player_name(out.get("description") or out.get("name") or "")
                # Odds API commonly uses: name="Over"/"Under", description="Player Name", point=<line>
                side = (out.get("name") or "").strip().lower()  # "over"/"under"
                point = out.get("point", None)
                price = out.get("price", None)

                if not player or point is None:
                    continue
                if side not in ("over", "under"):
                    continue

                k = (player, mkey)
                lines_by.setdefault(k, []).append(float(point))
                price_by.setdefault((player, mkey, side, float(point)), []).append(price)

    parsed = []
    for (player, mkey), pts in lines_by.items():
        if not pts:
            continue
        # consensus line
        line = statistics.median(pts)

        # choose a representative over/under price from closest point match if possible
        # (if books differ slightly, pick the most common point)
        point_mode = max(set(pts), key=pts.count)
        over_prices = price_by.get((player, mkey, "over", float(point_mode)), [])
        under_prices = price_by.get((player, mkey, "under", float(point_mode)), [])
        over_price = over_prices[0] if over_prices else None
        under_price = under_prices[0] if under_prices else None

        parsed.append({
            "player": player,
            "market_key": mkey,
            "line": float(line),
            "over_price": over_price,
            "under_price": under_price
        })
    return parsed

# =============================================================================
# EDGE MODEL: projection + edge score + factor breakdown
# =============================================================================

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))

def nba_projection(player_data: dict, prop_type: str, game_ctx: dict):
    """
    Produce a rough projection using your inputs + matchup.
    This is NOT a full stat model; it's a rules-based projection aligned to your scoring factors.
    """
    opp = game_ctx.get("opponent_abbr", "")
    opp_def = OPPONENT_DEFENSE["nba"].get(opp, {})
    pace = opp_def.get("pace_adjust", 1.0)

    usage = player_data.get("usage_rate", 25.0)
    eff = player_data.get("efficiency", 0.58)
    rest = player_data.get("rest_days", 1)
    ha = player_data.get("home_away_split", 1.0)
    b2b = player_data.get("back_to_back", False)
    load = player_data.get("load_managed", False)

    # generic multipliers
    usage_mult = 1.0 + (usage - 25.0) / 200.0
    eff_mult = 1.0 + (eff - 0.58) / 5.0
    rest_mult = 1.0 + (rest - 1) * 0.02
    ha_mult = ha
    sched_mult = 1.0 - (0.04 if b2b else 0.0) - (0.06 if load else 0.0)
    pace_mult = pace

    mult = usage_mult * eff_mult * rest_mult * ha_mult * sched_mult * pace_mult

    if prop_type == "points":
        base = player_data.get("recent_ppg", 0)
    elif prop_type == "rebounds":
        base = player_data.get("recent_rpg", 0)
    elif prop_type == "assists":
        base = player_data.get("recent_apg", 0)
    elif prop_type == "3_pointers":
        base = player_data.get("recent_3pm", 0)
    elif prop_type == "steals":
        base = player_data.get("recent_stl", 0)
    elif prop_type == "blocks":
        base = player_data.get("recent_blk", 0)
    elif prop_type == "turnovers":
        # not in your player dict; approximate from usage
        base = 2.5 + (usage - 25) / 20
    elif prop_type == "field_goals":
        base = player_data.get("fgm", 0)
    elif prop_type == "free_throws":
        # rough FT made estimate from ppg and ft_rate
        ft_rate = player_data.get("ft_rate", 0.25)
        ppg = player_data.get("recent_ppg", 0)
        ft_att = (ppg * ft_rate) / 0.75
        base = ft_att * 0.75
    elif prop_type == "pts_reb":
        base = player_data.get("recent_ppg", 0) + player_data.get("recent_rpg", 0)
    elif prop_type == "pts_ast":
        base = player_data.get("recent_ppg", 0) + player_data.get("recent_apg", 0)
    elif prop_type == "reb_ast":
        base = player_data.get("recent_rpg", 0) + player_data.get("recent_apg", 0)
    elif prop_type == "pts_reb_ast":
        base = player_data.get("recent_ppg", 0) + player_data.get("recent_rpg", 0) + player_data.get("recent_apg", 0)
    elif prop_type == "stl_blk":
        base = player_data.get("recent_stl", 0) + player_data.get("recent_blk", 0)
    else:
        base = 0

    return base * mult

def nfl_projection(player_data: dict, prop_type: str, game_ctx: dict):
    opp = game_ctx.get("opponent_abbr", "")
    opp_def = OPPONENT_DEFENSE["nfl"].get(opp, {})

    weather = player_data.get("weather_impact", 1.0)
    rz = player_data.get("red_zone_attempts", player_data.get("red_zone_targets", 0.0))
    pressure = player_data.get("pressure_to_sack", 0.15)
    rest = player_data.get("rest_days", 3)

    weather_mult = weather
    rest_mult = 1.0 + (rest - 3) * 0.01
    pressure_mult = 1.0 - max(0.0, (pressure - 0.15)) * 0.25

    mult = weather_mult * rest_mult * pressure_mult

    if prop_type == "pass_yards":
        base = player_data.get("recent_pass_yds", 0)
        # adjust vs pass_rank (lower rank = stronger defense)
        pass_rank = opp_def.get("pass_rank", 16)
        def_mult = 1.0 + (pass_rank - 16) / 100.0
        return base * mult * def_mult
    if prop_type == "pass_td":
        base = player_data.get("recent_pass_td", 0)
        return base * mult * (1.0 + rz / 50.0)
    if prop_type == "int":
        base = player_data.get("recent_int", 0)
        return base * (1.0 + opp_def.get("pressure_rate", 0.30) / 10.0)
    if prop_type == "rush_yards":
        base = player_data.get("recent_rush_yds", 0)
        run_rank = opp_def.get("run_rank", 16)
        def_mult = 1.0 + (run_rank - 16) / 120.0
        return base * mult * def_mult
    if prop_type == "carries":
        base = player_data.get("recent_rush_yds", 0) / 4.5
        return base * mult
    if prop_type == "receptions":
        base = player_data.get("recent_rec", 0)
        rp = player_data.get("route_participation", 0.80)
        return base * mult * (0.8 + rp / 2.0)
    if prop_type == "rec_yards":
        base = player_data.get("recent_rec_yds", 0)
        rp = player_data.get("route_participation", 0.80)
        return base * mult * (0.8 + rp / 2.0)
    if prop_type == "rec_td":
        base = player_data.get("recent_rec_td", 0)
        return base * mult * (1.0 + rz / 20.0)
    if prop_type == "pass_rush_yards":
        base = player_data.get("recent_pass_yds", 0) + player_data.get("recent_rush_yds", 0)
        return base * mult
    if prop_type == "rush_rec_yards":
        base = player_data.get("recent_rush_yds", 0) + player_data.get("recent_rec_yds", 0)
        return base * mult
    if prop_type == "pass_rush_rec_yards":
        base = player_data.get("recent_pass_yds", 0) + player_data.get("recent_rush_yds", 0) + player_data.get("recent_rec_yds", 0)
        return base * mult
    return 0.0

def edge_score_from_projection(proj: float, line: float, side: str):
    """
    Convert projection difference into a 0-100 edge score for that side.
    side: "over" or "under"
    """
    if line <= 0:
        return 0.0

    diff = proj - line
    # For under, invert
    if side == "under":
        diff = -diff

    # scale by typical variance: larger lines have larger noise
    # This keeps it from saying everything is 99% edge.
    scale = max(1.0, line * 0.12)
    z = diff / scale

    # map to 0..100 around midpoint ~50
    p = sigmoid(z)  # 0..1
    score = 100.0 * p
    return float(clamp(score, 0.0, 100.0))

def calculate_prop_edge(player_name: str, prop_type: str, line: float, game_ctx: dict, league: str):
    base = 50.0
    breakdown = {}

    if league == "nba":
        pd = NBA_PLAYERS_DATA.get(player_name, {})
        proj = nba_projection(pd, prop_type, game_ctx)

        usage = pd.get("usage_rate", 25)
        breakdown["Usage Rate"] = min(10, usage / 3.2)
        breakdown["Efficiency"] = min(8, pd.get("efficiency", 0.58) * 12)
        breakdown["Rest Days"] = min(6, pd.get("rest_days", 1) * 2.5)
        breakdown["Pace"] = (OPPONENT_DEFENSE["nba"].get(game_ctx.get("opponent_abbr",""), {}).get("pace_adjust", 1.0) - 1.0) * 30
        breakdown["Back-to-Back"] = -6 if pd.get("back_to_back", False) else 2
        breakdown["Load Mgmt"] = -8 if pd.get("load_managed", False) else 2

    else:
        pd = NFL_PLAYERS_DATA.get(player_name, {})
        proj = nfl_projection(pd, prop_type, game_ctx)

        breakdown["Route Part"] = min(10, pd.get("route_participation", 0.80) * 10)
        breakdown["Weather"] = (pd.get("weather_impact", 1.0) - 0.9) * 50
        breakdown["Red Zone"] = min(8, (pd.get("red_zone_attempts", pd.get("red_zone_targets", 0.0))) * 2.0)
        breakdown["Pressure"] = -6 if pd.get("pressure_to_sack", 0.15) > 0.20 else 2
        breakdown["Injury Risk"] = -6 if pd.get("injury_risk", 0.10) > 0.15 else 2

    # Score both sides; pick best
    over = edge_score_from_projection(proj, line, "over")
    under = edge_score_from_projection(proj, line, "under")

    if under > over:
        pick_side = "UNDER"
        score = under
    else:
        pick_side = "OVER"
        score = over

    # Add a small "distance" factor to breakdown for visibility
    breakdown["Proj vs Line"] = (proj - line)

    return score, pick_side, proj, breakdown

# =============================================================================
# PROP COLLECTION (REAL LINES ONLY)
# =============================================================================

def format_time_local(iso_time: str):
    try:
        t = dt.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone(timezone.utc)
        # keep it simple: show ET label like your original did (but using UTC here)
        return t.strftime("%I:%M %p UTC")
    except Exception:
        return iso_time

def build_games_from_events(events: list[dict]):
    games = []
    for e in events:
        games.append({
            "id": e.get("id"),
            "home_team": e.get("home_team", ""),
            "away_team": e.get("away_team", ""),
            "commence_time": e.get("commence_time", ""),
            "matchup": f"{e.get('away_team','')} @ {e.get('home_team','')}",
            "time": format_time_local(e.get("commence_time", "")),
        })
    return games

def abbreviate_team(team_name: str, league: str) -> str:
    """
    Minimal helper. You can expand this if you want perfect abbreviations.
    If unknown, returns "".
    """
    # Very small shortcut map; expand if you want. Your OPPONENT_DEFENSE only has a few teams anyway.
    nba_map = {
        "Los Angeles Lakers": "LAL",
        "Golden State Warriors": "GS",
        "Houston Rockets": "HOU",
        "Denver Nuggets": "DEN",
    }
    nfl_map = {
        "Miami Dolphins": "MIA",
        "Buffalo Bills": "BUF",
        "Kansas City Chiefs": "KC",
    }
    return (nba_map if league == "nba" else nfl_map).get(team_name, "")

def generate_top_props_for_league(league: str, injured_set: set[str]):
    """
    Pull events -> pull event odds -> parse prop lines -> score -> return top picks.
    """
    if league == "nba":
        sport_key = NBA_SPORT_KEY
        markets = NBA_MARKETS
        market_to_prop = NBA_MARKET_TO_PROP
        player_db = NBA_PLAYERS_DATA
        keep_top = 8
    else:
        sport_key = NFL_SPORT_KEY
        markets = NFL_MARKETS
        market_to_prop = NFL_MARKET_TO_PROP
        player_db = NFL_PLAYERS_DATA
        keep_top = 8

    events = oddsapi_get_events(sport_key)
    games = build_games_from_events(events)

    picks = []

    for g in games:
        event_id = g["id"]
        if not event_id:
            continue

        try:
            odds = oddsapi_get_event_props(sport_key, event_id, markets)
        except Exception:
            continue

        lines = parse_event_prop_lines(odds)

        # opponent context (use opponent = home team for away player context as baseline)
        opp_abbr = abbreviate_team(g["home_team"], league)  # simple
        # Team injuries from your fallback list are handled earlier by name set.

        for item in lines:
            player = item["player"]
            market_key = item["market_key"]
            line = item["line"]

            if player not in player_db:
                continue
            if player in injured_set:
                continue
            if market_key not in market_to_prop:
                continue

            prop_type = market_to_prop[market_key]
            score, side, proj, breakdown = calculate_prop_edge(
                player, prop_type, line,
                {"opponent_abbr": opp_abbr},
                league
            )

            # Keep only meaningful edges
            if score < 65:
                continue

            picks.append({
                "player": player,
                "prop_type": prop_type,
                "line": line,
                "side": side,
                "proj": proj,
                "edge_score": score,
                "matchup": g["matchup"],
                "time": g["time"],
                "breakdown": breakdown
            })

    picks.sort(key=lambda x: x["edge_score"], reverse=True)
    return picks[:keep_top]

# =============================================================================
# HTML OUTPUT
# =============================================================================

def generate_factor_html(breakdown):
    html = '<div class="factor-breakdown">'
    # pick the strongest 6
    items = sorted(breakdown.items(), key=lambda x: abs(x[1]) if isinstance(x[1], (int,float)) else 0, reverse=True)[:6]
    for name, val in items:
        try:
            score = float(val)
        except Exception:
            score = 0.0

        # normalize for display
        norm = int(clamp(50 + score * 8, 0, 100))

        if norm >= 75:
            gradient = "linear-gradient(90deg, #00ff88, #00cc66)"
        elif norm >= 50:
            gradient = "linear-gradient(90deg, #00d4ff, #0099ff)"
        else:
            gradient = "linear-gradient(90deg, #ffaa00, #ff8800)"

        html += f"""
            <div class="factor-item">
                <div class="factor-name">{name}</div>
                <div class="factor-score-bar">
                    <div class="factor-score-fill" style="width: {norm}%; background: {gradient};">{norm}</div>
                </div>
            </div>
        """
    html += "</div>"
    return html

def generate_prediction_card(prop):
    edge_score = prop["edge_score"]
    confidence_color = "high" if edge_score >= 80 else ("medium" if edge_score >= 70 else "low")
    confidence_text = f"{int(edge_score)}% EDGE"

    prop_display = f"{prop['player']} {prop['prop_type'].replace('_',' ').title()} {prop['side']} {prop['line']}"

    html = f"""
        <div class="prediction-card {confidence_color}-confidence">
            <div class="prediction-header">
                <div>
                    <div class="prediction-title">{prop_display}</div>
                    <div style="color: var(--color-text-secondary); font-size: 0.9em; margin-top: 5px;">
                        {prop['matchup']} | {prop['time']}
                    </div>
                    <div style="color: var(--color-text-secondary); font-size: 0.85em; margin-top: 6px;">
                        Model proj: {prop['proj']:.2f}
                    </div>
                </div>
                <div class="confidence-badge {confidence_color}">{confidence_text}</div>
            </div>

            {generate_factor_html(prop['breakdown'])}

            <div class="ai-reasoning">
                <strong>📊 Real Line + Model Edge:</strong>
                Line pulled from sportsbook prop markets. Pick side (Over/Under) chosen by model projection vs the real line,
                then adjusted by your context factors (usage, efficiency, pace, rest, etc.).
            </div>

            <span class="risk-indicator {'low' if confidence_color == 'high' else 'medium'}-risk">Real-line selection</span>
        </div>
    """
    return html

def generate_html(nba_props, nfl_props):
    now = dt.now()
    today_date = now.strftime("%B %d, %Y")
    last_updated = now.strftime("%B %d, %Y at %I:%M %p")

    nba_cards = "".join(generate_prediction_card(p) for p in nba_props) or '<p style="color: var(--color-text-secondary);">No high-edge NBA props found.</p>'
    nfl_cards = "".join(generate_prediction_card(p) for p in nfl_props) or '<p style="color: var(--color-text-secondary);">No high-edge NFL props found.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>🤖 Advanced Prop Analyzer</title>
<style>
:root {{
    --color-primary: #1e40af;
    --color-secondary: #0f766e;
    --color-bg: #0a0e27;
    --color-surface: #1a1f3a;
    --color-border: #2d3748;
    --color-text: #f1f5f9;
    --color-text-secondary: #cbd5e1;
    --shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, var(--color-bg) 0%, #0f1729 100%);
    color: var(--color-text);
    padding: 20px;
    min-height: 100vh;
}}
.header {{
    text-align:center;
    margin-bottom:40px;
    border-bottom:2px solid var(--color-border);
    padding-bottom:20px;
}}
.header h1 {{
    font-size:2.4em;
    margin-bottom:10px;
    background: linear-gradient(135deg, #00d4ff, #0099ff);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}}
.header-badge {{
    display:inline-block;
    background: rgba(0,212,255,0.2);
    border:1px solid #00d4ff;
    padding:8px 16px;
    border-radius:20px;
    font-size:0.9em;
    color:#00d4ff;
    margin-bottom:10px;
    font-weight:600;
}}
.methodology {{
    background: rgba(0,212,255,0.05);
    border:1px solid rgba(0,212,255,0.2);
    padding:15px;
    border-radius:8px;
    color: var(--color-text-secondary);
    font-size:0.85em;
    margin-top:10px;
    line-height:1.6;
}}
.container {{ max-width: 1600px; margin: 0 auto; }}
.controls-section {{
    background: var(--color-surface);
    border:1px solid var(--color-border);
    border-radius:12px;
    padding:20px;
    margin-bottom:30px;
    box-shadow: var(--shadow);
}}
.league-tabs {{ display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap; }}
.league-tab {{
    padding:10px 20px;
    border:2px solid var(--color-border);
    background:transparent;
    color: var(--color-text);
    cursor:pointer;
    border-radius:8px;
    font-weight:600;
    transition: all 0.3s ease;
}}
.league-tab:hover {{
    border-color:#00d4ff;
    background: rgba(0,212,255,0.1);
}}
.league-tab.active {{
    background: linear-gradient(135deg, #00d4ff, #0099ff);
    border-color:#00d4ff;
    color:#000;
}}
.league-content {{ display:none; }}
.league-content.active {{ display:block; }}

.prediction-card {{
    background: var(--color-surface);
    border:2px solid var(--color-border);
    border-radius:12px;
    padding:20px;
    margin-bottom:20px;
    transition: all 0.3s ease;
}}
.prediction-card:hover {{
    border-color:#00d4ff;
    box-shadow: 0 8px 24px rgba(0,212,255,0.1);
    transform: translateY(-2px);
}}
.prediction-card.high-confidence {{ border-left:5px solid #00ff88; }}
.prediction-card.medium-confidence {{ border-left:5px solid #ffaa00; }}
.prediction-card.low-confidence {{ border-left:5px solid #ff6b6b; }}

.prediction-header {{
    display:flex;
    justify-content:space-between;
    align-items:start;
    margin-bottom:15px;
}}
.prediction-title {{ font-size:1.25em; font-weight:700; }}
.confidence-badge {{
    display:inline-block;
    padding:8px 16px;
    border-radius:20px;
    font-size:0.9em;
    font-weight:700;
    color:white;
}}
.confidence-badge.high {{ background: linear-gradient(135deg, #00ff88, #00cc66); }}
.confidence-badge.medium {{ background: linear-gradient(135deg, #ffaa00, #ff8800); }}
.confidence-badge.low {{ background: linear-gradient(135deg, #ff6b6b, #cc0000); }}

.factor-breakdown {{
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap:12px;
    margin: 15px 0;
}}
.factor-item {{
    background: rgba(0,212,255,0.05);
    border:1px solid rgba(0,212,255,0.2);
    padding:12px;
    border-radius:6px;
}}
.factor-name {{
    font-size:0.85em;
    font-weight:600;
    color:#00d4ff;
    text-transform:uppercase;
    letter-spacing:0.5px;
    margin-bottom:6px;
}}
.factor-score-bar {{
    background: rgba(0,0,0,0.3);
    height:20px;
    border-radius:3px;
    overflow:hidden;
}}
.factor-score-fill {{
    height:100%;
    width:0%;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:0.7em;
    font-weight:700;
    color:#000;
}}
.ai-reasoning {{
    background: rgba(0,212,255,0.05);
    border-left:3px solid #00d4ff;
    padding:12px;
    border-radius:6px;
    margin: 12px 0;
    font-size:0.9em;
    line-height:1.5;
    color: var(--color-text-secondary);
}}
.risk-indicator {{
    display:inline-block;
    padding:6px 12px;
    border-radius:4px;
    font-size:0.8em;
    font-weight:600;
    margin-top:10px;
    background: rgba(0,255,136,0.15);
    color:#00ff88;
}}
@media (max-width:768px) {{
    .header h1 {{ font-size:1.8em; }}
    .factor-breakdown {{ grid-template-columns:1fr; }}
}}
</style>
</head>
<body>
<div class="header">
    <div class="header-badge">🤖 REAL LINES + EDGE MODEL</div>
    <h1>Advanced Prop Analyzer</h1>
    <p style="color: var(--color-text-secondary); font-size: 1.05em;">Over + Under picks | Injury filtering | Best edges only</p>
    <p style="color: var(--color-text-secondary); font-size: 0.95em; margin-top: 8px;">
        📊 {len(nba_props)} NBA Picks | 🏈 {len(nfl_props)} NFL Picks
    </p>
    <div class="methodology">
        Uses The Odds API player prop markets (real sportsbook lines) accessed per-event via /events/{{eventId}}/odds, then applies your rules-based context model. :contentReference[oaicite:5]{index=5}
        Injuries are pulled from ESPN team injury feeds and filtered out.
    </div>
</div>

<div class="container">
    <div class="controls-section">
        <div class="league-tabs">
            <button class="league-tab active" data-league="nba">🏀 NBA PICKS</button>
            <button class="league-tab" data-league="nfl">🏈 NFL PICKS</button>
        </div>
    </div>

    <div id="nba" class="league-content active">
        <h2 style="font-size: 1.5em; margin: 30px 0 20px 0;">NBA Top Plays – {today_date}</h2>
        {nba_cards}
    </div>

    <div id="nfl" class="league-content">
        <h2 style="font-size: 1.5em; margin: 30px 0 20px 0;">NFL Top Plays – {today_date}</h2>
        {nfl_cards}
    </div>
</div>

<div style="text-align:center; margin: 40px 0; color: var(--color-text-secondary); font-size:0.9em;">
    <p>⚡ Updated Daily at 8:00 AM PST</p>
    <p>Last Updated: {last_updated}</p>
    <p style="font-size:0.85em; margin-top: 15px;">Disclaimer: informational only.</p>
</div>

<script>
document.querySelectorAll('.league-tab').forEach(tab => {{
    tab.addEventListener('click', function() {{
        const league = this.getAttribute('data-league');
        document.querySelectorAll('.league-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.league-content').forEach(c => c.classList.remove('active'));
        this.classList.add('active');
        document.getElementById(league).classList.add('active');
    }});
}});
</script>
</body>
</html>
"""

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("🚀 Starting Prop Analyzer (Real Lines + Injury Filter)...")
    print(f"⏰ {dt.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not ODDS_API_KEY:
        raise RuntimeError("Set ODDS_API_KEY (GitHub Secret) before running.")

    print("🩺 Fetching injuries from ESPN...")
    (nba_inj, nba_details), (nfl_inj, nfl_details) = build_injury_sets()
    print(f"✓ Injured loaded: NBA={len(nba_inj)}, NFL={len(nfl_inj)}")

    print("📡 Pulling NBA props (real lines)...")
    nba_top = generate_top_props_for_league("nba", nba_inj)

    print("📡 Pulling NFL props (real lines)...")
    nfl_top = generate_top_props_for_league("nfl", nfl_inj)

    html = generate_html(nba_top, nfl_top)
    with open("AI_Prediction_Engine.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Done. Wrote AI_Prediction_Engine.html")

if __name__ == "__main__":
    main()
