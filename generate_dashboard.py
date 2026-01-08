#!/usr/bin/env python3
"""
Automated Prop-Bet Scouting Dashboard (NBA + NFL)
- Pulls upcoming games + player prop lines from The Odds API (free tier friendly)
- Pulls team abbreviations + injuries from ESPN (free)
- Scores props with a rules-based edge model and outputs AI_Prediction_Engine.html

Key fix:
- Use ESPN abbreviations for roster/injury/team matching
- Use normalized abbreviations ONLY for OPPONENT_DEFENSE keys (e.g., GSW -> GS)
"""

import os
import re
import math
import json
import time
import requests
from datetime import datetime as dt
from datetime import timezone
from typing import Dict, List, Tuple, Any

# =============================================================================
# CONFIG
# =============================================================================

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
if not ODDS_API_KEY:
    raise RuntimeError("Missing ODDS_API_KEY environment variable. Add it in GitHub Secrets.")

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

NBA_SPORT_KEY = "basketball_nba"
NFL_SPORT_KEY = "americanfootball_nfl"

# Keep your prop markets aligned to what your Odds API plan supports.
# If a market is unsupported, the request might error or return empty markets.
# You can prune/adjust later.
NBA_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
    "player_turnovers",
    "player_points_rebounds_assists",
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
    "player_free_throws",
    "player_field_goals",
]
NFL_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_rush_yds",
    "player_rush_tds",
    "player_receptions",
    "player_reception_yds",
    "player_reception_tds",
]

# Optional: try to fetch spreads/totals for blowout/script logic
MAIN_LINE_MARKETS = ["spreads", "totals"]

# Map Odds API market -> your internal prop_type keys (must match your projection/scoring logic)
NBA_MARKET_TO_PROP = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "3_pointers",
    "player_steals": "steals",
    "player_blocks": "blocks",
    "player_turnovers": "turnovers",
    "player_points_rebounds_assists": "pts_reb_ast",
    "player_points_rebounds": "pts_reb",
    "player_points_assists": "pts_ast",
    "player_rebounds_assists": "reb_ast",
    "player_free_throws": "free_throws",
    "player_field_goals": "field_goals",
}

NFL_MARKET_TO_PROP = {
    "player_pass_yds": "pass_yards",
    "player_pass_tds": "pass_td",
    "player_pass_interceptions": "int",
    "player_rush_yds": "rush_yards",
    "player_rush_tds": "rush_td",
    "player_receptions": "receptions",
    "player_reception_yds": "rec_yards",
    "player_reception_tds": "rec_td",
}

# =============================================================================
# PASTE YOUR EXISTING DICTIONARIES HERE (UNCHANGED)
# =============================================================================

# --- PASTE: NBA_PLAYERS_DATA (unchanged) ---
# NBA_PLAYERS_DATA = {...}

# --- PASTE: NFL_PLAYERS_DATA (unchanged) ---
# NFL_PLAYERS_DATA = {...}

# --- PASTE: OPPONENT_DEFENSE (unchanged) ---
# OPPONENT_DEFENSE = {...}

# --- PASTE: REFEREE_TENDENCIES (unchanged) ---
# REFEREE_TENDENCIES = {...}


# =============================================================================
# TEAM ABBR NORMALIZATION (ESPN -> your OPPONENT_DEFENSE keys)
# =============================================================================

NBA_ABBR_ALIASES = {
    # ESPN uses GSW; your defense table uses GS
    "GSW": "GS",
}

NFL_ABBR_ALIASES = {
    # Add if you ever need it
    # "WSH": "WAS",
}

# Odds API team naming sometimes differs from ESPN displayName.
# Add aliases here if you see mismatches.
TEAM_NAME_ALIASES = {
    "nba": {
        "LA Lakers": "Los Angeles Lakers",
        "Los Angeles Lakers": "Los Angeles Lakers",
        "LA Clippers": "LA Clippers",
        "Golden State Warriors": "Golden State Warriors",
        "GS Warriors": "Golden State Warriors",
    },
    "nfl": {
        "Kansas City Chiefs": "Kansas City Chiefs",
        "KC Chiefs": "Kansas City Chiefs",
    }
}


# =============================================================================
# UTIL
# =============================================================================

def _safe_get_json(url: str, timeout: int = 12, headers: dict | None = None) -> dict:
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return r.json()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def format_time_local(iso_time: str) -> str:
    # Odds API times are ISO8601 UTC like "2026-01-07T03:00:00Z"
    try:
        t = dt.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone()
        return t.strftime("%I:%M %p %Z")
    except Exception:
        return iso_time

def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    # remove punctuation
    s = re.sub(r"[^a-z0-9\s]", "", s)
    # remove suffixes
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s).strip()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_team_abbr(league: str, abbr: str) -> str:
    if not abbr:
        return ""
    abbr = abbr.strip().upper()
    if league == "nba":
        return NBA_ABBR_ALIASES.get(abbr, abbr)
    return NFL_ABBR_ALIASES.get(abbr, abbr)


# =============================================================================
# ESPN: TEAM MAP + INJURIES (FREE)
# =============================================================================

def fetch_espn_team_map(league: str) -> dict:
    """
    Returns dict: {team_display_name: {"id": "...", "abbr": "..."}}
    """
    if league == "nba":
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    else:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

    data = _safe_get_json(url)
    out = {}
    # ESPN format: sports -> leagues -> teams
    leagues = data.get("sports", [])[0].get("leagues", []) if data.get("sports") else []
    teams = leagues[0].get("teams", []) if leagues else []
    for t in teams:
        team = t.get("team", {})
        name = team.get("displayName", "")
        out[name] = {
            "id": team.get("id", ""),
            "abbr": team.get("abbreviation", ""),
        }
    return out

def resolve_espn_display_name(league: str, odds_team_name: str, espn_team_map: dict) -> str:
    """
    Best-effort mapping from Odds API team name -> ESPN displayName
    """
    if not odds_team_name:
        return ""
    alias = TEAM_NAME_ALIASES.get(league, {}).get(odds_team_name)
    if alias and alias in espn_team_map:
        return alias
    # direct match
    if odds_team_name in espn_team_map:
        return odds_team_name
    # fallback: try stripping city punctuation / common variants
    return odds_team_name  # if not found, return as-is (abbr will be missing)

def fetch_espn_injuries(league: str) -> Tuple[set[str], dict]:
    """
    Returns:
      injured_names_norm: set of normalized player names that are OUT/INACTIVE/DOUBTFUL/etc.
      details: dict normalized_name -> (status, team_abbr_espn, raw_display_name)
    """
    team_map = fetch_espn_team_map(league)
    injured_norm = set()
    details = {}

    for team_name, meta in team_map.items():
        team_id = meta.get("id", "")
        team_abbr = meta.get("abbr", "")
        if not team_id:
            continue

        # ESPN team endpoint supports enable=injuries
        if league == "nba":
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}?enable=injuries"
        else:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}?enable=injuries"

        try:
            data = _safe_get_json(url)
            injuries = data.get("team", {}).get("injuries", []) or data.get("injuries", [])
            for inj in injuries:
                athlete = inj.get("athlete", {}) or {}
                raw_name = athlete.get("displayName") or ""
                status = (inj.get("status", {}) or {}).get("name") or inj.get("status") or ""
                status_upper = str(status).upper()

                # treat these as "do not play"
                if any(x in status_upper for x in ["OUT", "INACTIVE", "DOUBTFUL", "IR", "DNP"]):
                    nm = normalize_player_name(raw_name)
                    if nm:
                        injured_norm.add(nm)
                        details[nm] = (status, team_abbr, raw_name)
        except Exception:
            continue

    return injured_norm, details


# =============================================================================
# ODDS API: EVENTS + ODDS
# =============================================================================

def oddsapi_get_events(sport_key: str) -> list[dict]:
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def oddsapi_get_event_odds(sport_key: str, event_id: str, markets: list[str]) -> dict:
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def build_games_from_events(events: list[dict]) -> list[dict]:
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

def extract_main_lines(odds_json: dict) -> dict:
    """
    Returns: {"home_spread": float|None, "away_spread": float|None, "total": float|None}
    Best-effort from Odds API spreads/totals markets.
    """
    out = {"home_spread": None, "away_spread": None, "total": None}
    bookmakers = odds_json.get("bookmakers", []) or []
    if not bookmakers:
        return out

    # pick first bookmaker that has data
    for bm in bookmakers:
        markets = bm.get("markets", []) or []
        # spreads
        for m in markets:
            if m.get("key") == "spreads":
                for o in m.get("outcomes", []) or []:
                    name = o.get("name")
                    point = o.get("point")
                    if point is None:
                        continue
                    try:
                        point = float(point)
                    except Exception:
                        continue
                    # spread outcomes named by team
                    # We'll set later when we know home/away names
                    # Store both and map by name externally if needed
                # We'll handle mapping in caller (simpler)
        # totals
        for m in markets:
            if m.get("key") == "totals":
                # totals outcomes are Over/Under with point = total
                for o in m.get("outcomes", []) or []:
                    if o.get("name", "").lower() == "over" and o.get("point") is not None:
                        try:
                            out["total"] = float(o["point"])
                            break
                        except Exception:
                            pass
        if out["total"] is not None:
            break
    return out

def parse_player_props(odds_json: dict) -> list[dict]:
    """
    Returns list of:
      {"market": str, "player": str, "line": float, "over_price": int|None, "under_price": int|None}
    """
    parsed = []
    bookmakers = odds_json.get("bookmakers", []) or []
    for bm in bookmakers:
        for m in bm.get("markets", []) or []:
            market_key = m.get("key", "")
            for o in m.get("outcomes", []) or []:
                # Odds API player prop outcomes: typically have "description" as player, "name" as Over/Under
                player = o.get("description") or ""
                side = (o.get("name") or "").lower()
                point = o.get("point")

                if not player or point is None or side not in ("over", "under"):
                    continue

                try:
                    line = float(point)
                except Exception:
                    continue

                price = o.get("price")
                try:
                    price = int(price) if price is not None else None
                except Exception:
                    price = None

                # merge over+under into one record per (market, player, line)
                key = (market_key, player, line)
                existing = next((p for p in parsed if (p["market"], p["player"], p["line"]) == key), None)
                if existing is None:
                    rec = {"market": market_key, "player": player, "line": line, "over_price": None, "under_price": None}
                    parsed.append(rec)
                    existing = rec

                if side == "over":
                    existing["over_price"] = price
                else:
                    existing["under_price"] = price

    return parsed


# =============================================================================
# EDGE MODEL (NBA focus + general)
# =============================================================================

def nba_projection(player_data: dict, prop_type: str, ctx: dict) -> float:
    """
    Rules-based projection for NBA props (not a full model).
    Uses your player snapshots + context (pace, injuries, spread).
    """
    opp_def = OPPONENT_DEFENSE["nba"].get(ctx.get("opponent_abbr_def", ""), {})
    pace = float(opp_def.get("pace_adjust", 1.0))

    usage = float(player_data.get("usage_rate", 25.0))
    eff = float(player_data.get("efficiency", 0.58))
    rest = float(player_data.get("rest_days", 1))
    ha = float(player_data.get("home_away_split", 1.0))
    b2b = bool(player_data.get("back_to_back", False))
    load = bool(player_data.get("load_managed", False))

    # Base from recent stats
    if prop_type == "points":
        base = float(player_data.get("recent_ppg", 0))
    elif prop_type == "rebounds":
        base = float(player_data.get("recent_rpg", 0))
    elif prop_type == "assists":
        base = float(player_data.get("recent_apg", 0))
    elif prop_type == "3_pointers":
        base = float(player_data.get("recent_3pm", 0))
    elif prop_type == "steals":
        base = float(player_data.get("recent_stl", 0))
    elif prop_type == "blocks":
        base = float(player_data.get("recent_blk", 0))
    elif prop_type == "turnovers":
        # no snapshot in your db; estimate from usage
        base = 2.0 + (usage - 25.0) * 0.05
    elif prop_type == "field_goals":
        base = float(player_data.get("fgm", 0))
    elif prop_type == "free_throws":
        ft_rate = float(player_data.get("ft_rate", 0.25))
        ppg = float(player_data.get("recent_ppg", 0))
        ft_att = (ppg * ft_rate) / 0.75  # assume 75% FT%
        base = ft_att * 0.75
    elif prop_type == "pts_reb":
        base = float(player_data.get("recent_ppg", 0)) + float(player_data.get("recent_rpg", 0))
    elif prop_type == "pts_ast":
        base = float(player_data.get("recent_ppg", 0)) + float(player_data.get("recent_apg", 0))
    elif prop_type == "reb_ast":
        base = float(player_data.get("recent_rpg", 0)) + float(player_data.get("recent_apg", 0))
    elif prop_type == "pts_reb_ast":
        base = float(player_data.get("recent_ppg", 0)) + float(player_data.get("recent_rpg", 0)) + float(player_data.get("recent_apg", 0))
    else:
        base = 0.0

    mult = 1.0

    # Pace (small but meaningful)
    mult *= clamp(pace, 0.92, 1.10)

    # Usage & efficiency nudges (do not explode)
    mult *= clamp(0.94 + (usage - 25.0) * 0.008, 0.88, 1.12)
    mult *= clamp(0.96 + (eff - 0.58) * 0.60, 0.90, 1.10)

    # Rest / B2B / load management
    mult *= clamp(0.98 + 0.015 * rest, 0.96, 1.06)
    if b2b:
        mult *= 0.96
    if load:
        mult *= 0.93

    # Home/Away split baked in
    mult *= clamp(ha, 0.94, 1.08)

    # Injuries: treat as volume bump
    # (Counts are already from ESPN, so they’re consistent day-to-day)
    team_inj = float(ctx.get("team_inj_count", 0))
    opp_inj = float(ctx.get("opp_inj_count", 0))
    mult *= clamp(1.0 + team_inj * 0.010, 0.98, 1.08)
    mult *= clamp(1.0 + opp_inj * 0.006, 0.98, 1.06)

    # Favorite vs underdog usage change (small)
    if ctx.get("is_favorite") is True:
        mult *= 0.995
    elif ctx.get("is_favorite") is False:
        mult *= 1.010

    # Blowout risk: if spread big, stars lose late minutes
    spread_abs = ctx.get("spread_abs")
    if isinstance(spread_abs, (int, float)):
        if spread_abs >= 14:
            mult *= 0.95
        elif spread_abs >= 10:
            mult *= 0.97
        elif spread_abs >= 7:
            mult *= 0.985

    # Referee FT boost: mostly helps points/FT/FG
    if prop_type in ("points", "free_throws", "field_goals"):
        ft_boost = float(REFEREE_TENDENCIES["nba"].get("ft_rate_boost", 1.0))
        mult *= clamp(1.0 + (ft_boost - 1.0) * 0.35, 0.98, 1.05)

    return base * mult

def edge_score_from_projection(proj: float, line: float, prop_type: str, ctx: dict) -> Tuple[float, str, dict]:
    """
    Returns (score 0-100, side 'over'|'under', breakdown dict)
    """
    breakdown = {}
    if line <= 0:
        return 0.0, "over", breakdown

    delta = proj - line  # + means over lean
    # deadzone so we don't force picks on tiny differences
    dead = 0.25 if prop_type in ("steals", "blocks") else 0.50

    if abs(delta) < dead:
        breakdown["Model Δ vs Line"] = delta
        return 0.0, "over", breakdown

    side = "over" if delta > 0 else "under"

    # Convert delta into a base score shape
    # scale by line size (bigger lines need bigger edge)
    scale = max(1.5, line * 0.08)
    base = 50 + 45 * (2 * sigmoid(delta / scale) - 1)  # ~5..95

    breakdown["Model Δ vs Line"] = delta
    breakdown["Scaled Edge"] = (delta / scale)

    # Context bonuses/penalties (small)
    spread_abs = ctx.get("spread_abs")
    if isinstance(spread_abs, (int, float)):
        if spread_abs >= 14:
            base -= 6
            breakdown["Blowout Risk"] = -6
        elif spread_abs >= 10:
            base -= 4
            breakdown["Blowout Risk"] = -4
        elif spread_abs >= 7:
            base -= 2
            breakdown["Blowout Risk"] = -2

    # Underdog slight upside (more minutes, more “need”)
    if ctx.get("is_favorite") is False:
        base += 1.5
        breakdown["Underdog Usage"] = +1.5

    # Team injuries can push usage upward; opponent injuries can soften defense
    base += clamp(float(ctx.get("team_inj_count", 0)) * 0.7, 0, 4)
    breakdown["Teammate Inj Boost"] = clamp(float(ctx.get("team_inj_count", 0)) * 0.7, 0, 4)

    base += clamp(float(ctx.get("opp_inj_count", 0)) * 0.4, 0, 3)
    breakdown["Opp Inj Boost"] = clamp(float(ctx.get("opp_inj_count", 0)) * 0.4, 0, 3)

    score = clamp(base, 0, 100)
    return score, side, breakdown


# =============================================================================
# TEAM + GAME CONTEXT BUILDING
# =============================================================================

def build_game_context(
    league: str,
    g: dict,
    espn_team_map: dict,
    injury_details: dict,
    main_lines: dict | None
) -> dict:
    """
    Builds a context dict with:
    - ESPN abbr for injuries/team counts
    - normalized defense abbr for OPPONENT_DEFENSE
    - spread_abs and favorite flag (if we have spreads)
    """
    league_key = "nba" if league == "nba" else "nfl"

    home_disp = resolve_espn_display_name(league_key, g["home_team"], espn_team_map)
    away_disp = resolve_espn_display_name(league_key, g["away_team"], espn_team_map)

    home_abbr_espn = espn_team_map.get(home_disp, {}).get("abbr", "")
    away_abbr_espn = espn_team_map.get(away_disp, {}).get("abbr", "")

    # injury counts by ESPN abbr
    team_inj_counts = {}
    for nm, (_status, team_abbr, _raw) in injury_details.items():
        team_inj_counts[team_abbr] = team_inj_counts.get(team_abbr, 0) + 1

    # normalized for defense
    home_abbr_def = normalize_team_abbr(league_key, home_abbr_espn)
    away_abbr_def = normalize_team_abbr(league_key, away_abbr_espn)

    # spread handling (optional)
    spread_abs = None
    is_home_fav = None
    if main_lines:
        # main_lines may not include spreads; we’ll compute in scorer if possible
        spread_abs = main_lines.get("spread_abs")
        is_home_fav = main_lines.get("home_fav")

    return {
        "home_abbr_espn": home_abbr_espn,
        "away_abbr_espn": away_abbr_espn,
        "home_abbr_def": home_abbr_def,
        "away_abbr_def": away_abbr_def,
        "team_inj_counts": team_inj_counts,
        "spread_abs": spread_abs,
        "home_is_fav": is_home_fav,
    }

def choose_team_context_for_player(
    league: str,
    player_name: str,
    g: dict,
    game_ctx: dict
) -> dict:
    """
    We don't have roster/team per player from Odds API, so we choose:
    - If player exists in your player_db and you later extend to player->team, use that.
    - For now: treat as neutral and use opponent based on "home vs away" unknown.
    This keeps the system working without mis-assigning players to the wrong team.
    """
    # If you later add player->team mapping, you would set these properly.
    # For now we evaluate matchup effects using BOTH sides lightly by picking the weaker/more neutral approach.
    # We'll assume "opponent" is the home team defense when evaluating (conservative).
    league_key = "nba" if league == "nba" else "nfl"
    return {
        "team_abbr_espn": game_ctx["away_abbr_espn"],
        "opponent_abbr_espn": game_ctx["home_abbr_espn"],
        "team_abbr_def": game_ctx["away_abbr_def"],
        "opponent_abbr_def": game_ctx["home_abbr_def"],
        "team_inj_count": float(game_ctx["team_inj_counts"].get(game_ctx["away_abbr_espn"], 0)),
        "opp_inj_count": float(game_ctx["team_inj_counts"].get(game_ctx["home_abbr_espn"], 0)),
        "spread_abs": game_ctx.get("spread_abs"),
        "is_favorite": None if game_ctx.get("home_is_fav") is None else (not game_ctx["home_is_fav"]),
    }


# =============================================================================
# TOP PICKS GENERATION
# =============================================================================

def generate_top_props_for_league(league: str, injured_norm: set[str], injury_details: dict) -> list[dict]:
    if league == "nba":
        sport_key = NBA_SPORT_KEY
        markets = NBA_MARKETS
        market_to_prop = NBA_MARKET_TO_PROP
        player_db = NBA_PLAYERS_DATA
        keep_top = 8
        league_key = "nba"
    else:
        sport_key = NFL_SPORT_KEY
        markets = NFL_MARKETS
        market_to_prop = NFL_MARKET_TO_PROP
        player_db = NFL_PLAYERS_DATA
        keep_top = 8
        league_key = "nfl"

    espn_team_map = fetch_espn_team_map(league_key)

    events = oddsapi_get_events(sport_key)
    games = build_games_from_events(events)

    picks = []

    for g in games:
        event_id = g.get("id")
        if not event_id:
            continue

        # Optional main lines for blowout/script logic
        main_lines = {"spread_abs": None, "home_fav": None}
        try:
            main_odds = oddsapi_get_event_odds(sport_key, event_id, MAIN_LINE_MARKETS)
            # We’ll try to infer spread_abs/home_fav from spreads market if present
            # (Odds API spread outcomes are team names with point values)
            home = g["home_team"]
            away = g["away_team"]
            home_spread = None
            away_spread = None

            for bm in main_odds.get("bookmakers", []) or []:
                for m in bm.get("markets", []) or []:
                    if m.get("key") != "spreads":
                        continue
                    for o in m.get("outcomes", []) or []:
                        name = o.get("name")
                        point = o.get("point")
                        if point is None:
                            continue
                        try:
                            point = float(point)
                        except Exception:
                            continue
                        if name == home:
                            home_spread = point
                        elif name == away:
                            away_spread = point
                if home_spread is not None or away_spread is not None:
                    break

            if home_spread is not None:
                main_lines["spread_abs"] = abs(home_spread)
                main_lines["home_fav"] = (home_spread < 0)
            elif away_spread is not None:
                main_lines["spread_abs"] = abs(away_spread)
                # if away spread is negative, away favored -> home_fav False
                main_lines["home_fav"] = not (away_spread < 0)

        except Exception:
            pass

        game_ctx = build_game_context(league_key, g, espn_team_map, injury_details, main_lines)

        try:
            odds = oddsapi_get_event_odds(sport_key, event_id, markets)
        except Exception:
            continue

        prop_rows = parse_player_props(odds)

        for row in prop_rows:
            market = row["market"]
            player = row["player"]
            line = row["line"]

            prop_type = market_to_prop.get(market)
            if not prop_type:
                continue

            # Injury filter (normalized)
            if normalize_player_name(player) in injured_norm:
                continue

            # Context (team/opponent/abbr) — neutral if we don’t know player team
            ctx = choose_team_context_for_player(league_key, player, g, game_ctx)

            # Projection
            pdata = player_db.get(player, {})
            if league_key == "nba":
                proj = nba_projection(pdata, prop_type, ctx) if pdata else line  # fallback: neutral
            else:
                # NFL fallback: neutral unless you extend it like nba_projection
                proj = line

            score, side, breakdown = edge_score_from_projection(proj, line, prop_type, ctx)

            # Keep only meaningful edges
            if score < 62:
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
                "breakdown": breakdown,
            })

    picks.sort(key=lambda x: x["edge_score"], reverse=True)
    return picks[:keep_top]


# =============================================================================
# HTML GENERATION
# =============================================================================

def generate_factor_html(breakdown: dict) -> str:
    html = '<div class="factor-breakdown">'
    sorted_factors = sorted(breakdown.items(), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 0, reverse=True)[:6]

    for name, val in sorted_factors:
        try:
            score = float(val)
        except Exception:
            score = 0.0

        # convert to a 0-100-ish bar
        norm = int(clamp(50 + score * 12, 0, 100))

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
                    <div class="factor-score-fill" style="width:{norm}%; background:{gradient};">{norm}</div>
                </div>
            </div>
        """

    html += "</div>"
    return html

def generate_prediction_card(prop: dict) -> str:
    edge = float(prop["edge_score"])
    confidence_color = "high" if edge >= 80 else ("medium" if edge >= 70 else "low")
    confidence_text = f"{int(edge)}% EDGE"

    prop_display = f"{prop['player']} {prop['prop_type'].replace('_',' ').title()} {prop['side'].title()} {prop['line']}"

    return f"""
        <div class="prediction-card {confidence_color}-confidence">
            <div class="prediction-header">
                <div>
                    <div class="prediction-title">{prop_display}</div>
                    <div style="color: var(--color-text-secondary); font-size: 0.9em; margin-top: 5px;">
                        {prop['matchup']} | {prop['time']} | Model proj: {prop['proj']:.2f}
                    </div>
                </div>
                <div class="confidence-badge {confidence_color}">{confidence_text}</div>
            </div>

            {generate_factor_html(prop['breakdown'])}

            <div class="ai-reasoning">
                <strong>📊 Real Line + Model Edge:</strong>
                Side (Over/Under) chosen from model projection vs real line, then adjusted by context:
                pace, usage, efficiency, rest/B2B, injuries, favorite/underdog, and blowout risk (when spreads available).
            </div>

            <span class="risk-indicator {'low' if confidence_color == 'high' else 'medium'}-risk">Edge-based selection</span>
        </div>
    """

def generate_html(nba_props: list[dict], nfl_props: list[dict]) -> str:
    now = dt.now().astimezone()
    today_date = now.strftime("%B %d, %Y")
    last_updated = now.strftime("%B %d, %Y at %I:%M %p %Z")

    nba_cards = "".join(generate_prediction_card(p) for p in nba_props) if nba_props else '<p style="color: var(--color-text-secondary);">No high-edge NBA props identified today.</p>'
    nfl_cards = "".join(generate_prediction_card(p) for p in nfl_props) if nfl_props else '<p style="color: var(--color-text-secondary);">No high-edge NFL props identified today.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Advanced Prop Dashboard</title>
<style>
:root {{
  --color-bg: #0a0e27;
  --color-surface: #1a1f3a;
  --color-border: #2d3748;
  --color-text: #f1f5f9;
  --color-text-secondary: #cbd5e1;
  --shadow: 0 4px 12px rgba(0,0,0,0.5);
}}
* {{ box-sizing: border-box; margin:0; padding:0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: linear-gradient(135deg, var(--color-bg) 0%, #0f1729 100%);
  color: var(--color-text);
  padding: 20px;
  min-height: 100vh;
}}
.header {{ text-align:center; margin-bottom:30px; border-bottom: 2px solid var(--color-border); padding-bottom: 16px; }}
.header h1 {{
  font-size: 2.2em;
  margin-bottom: 8px;
  background: linear-gradient(135deg, #00d4ff, #0099ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.header p {{ color: var(--color-text-secondary); }}
.container {{ max-width: 1400px; margin:0 auto; }}
.controls-section {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
  box-shadow: var(--shadow);
}}
.league-tabs {{ display:flex; gap:10px; flex-wrap:wrap; }}
.league-tab {{
  padding: 10px 16px;
  border: 2px solid var(--color-border);
  background: transparent;
  color: var(--color-text);
  cursor:pointer;
  border-radius: 8px;
  font-weight: 700;
}}
.league-tab.active {{
  background: linear-gradient(135deg, #00d4ff, #0099ff);
  border-color: #00d4ff;
  color: #000;
}}
.league-content {{ display:none; }}
.league-content.active {{ display:block; }}

.prediction-card {{
  background: var(--color-surface);
  border: 2px solid var(--color-border);
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 16px;
  transition: all 0.2s ease;
}}
.prediction-card:hover {{
  border-color: #00d4ff;
  box-shadow: 0 8px 24px rgba(0, 212, 255, 0.1);
  transform: translateY(-1px);
}}
.prediction-card.high-confidence {{ border-left: 5px solid #00ff88; }}
.prediction-card.medium-confidence {{ border-left: 5px solid #ffaa00; }}
.prediction-card.low-confidence {{ border-left: 5px solid #ff6b6b; }}

.prediction-header {{ display:flex; justify-content:space-between; gap:12px; }}
.prediction-title {{ font-size: 1.15em; font-weight: 800; }}

.confidence-badge {{
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 0.9em;
  font-weight: 800;
  color: #fff;
  white-space: nowrap;
}}
.confidence-badge.high {{ background: linear-gradient(135deg, #00ff88, #00cc66); }}
.confidence-badge.medium {{ background: linear-gradient(135deg, #ffaa00, #ff8800); }}
.confidence-badge.low {{ background: linear-gradient(135deg, #ff6b6b, #cc0000); }}

.factor-breakdown {{
  display:grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin: 14px 0;
}}
.factor-item {{
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.2);
  padding: 10px;
  border-radius: 8px;
}}
.factor-name {{
  font-size: 0.8em;
  font-weight: 700;
  color: #00d4ff;
  text-transform: uppercase;
  margin-bottom: 6px;
}}
.factor-score-bar {{
  background: rgba(0,0,0,0.3);
  height: 18px;
  border-radius: 4px;
  overflow:hidden;
}}
.factor-score-fill {{
  height:100%;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size: 0.75em;
  font-weight: 900;
  color: #000;
}}
.ai-reasoning {{
  background: rgba(0, 212, 255, 0.05);
  border-left: 3px solid #00d4ff;
  padding: 10px;
  border-radius: 8px;
  margin-top: 10px;
  color: var(--color-text-secondary);
  line-height: 1.45;
}}
.risk-indicator {{
  display:inline-block;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 0.85em;
  font-weight: 700;
  margin-top: 10px;
  background: rgba(0, 255, 136, 0.12);
  color: #00ff88;
}}

@media (max-width: 768px) {{
  .prediction-header {{ flex-direction: column; }}
}}
</style>
</head>
<body>
  <div class="header">
    <h1>Advanced Prop Scouting Dashboard</h1>
    <p>{today_date} • NBA picks: {len(nba_props)} • NFL picks: {len(nfl_props)}</p>
    <p style="margin-top:6px; font-size:0.95em;">Last updated: {last_updated}</p>
  </div>

  <div class="container">
    <div class="controls-section">
      <div class="league-tabs">
        <button class="league-tab active" data-league="nba">🏀 NBA</button>
        <button class="league-tab" data-league="nfl">🏈 NFL</button>
      </div>
    </div>

    <div id="nba" class="league-content active">
      <h2 style="margin: 10px 0 14px 0;">NBA Top Plays</h2>
      {nba_cards}
    </div>

    <div id="nfl" class="league-content">
      <h2 style="margin: 10px 0 14px 0;">NFL Top Plays</h2>
      {nfl_cards}
    </div>

    <div style="text-align:center; margin: 30px 0; color: var(--color-text-secondary); font-size: 0.9em;">
      <p>Disclaimer: informational only. Always do your own research.</p>
    </div>
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
    print("🚀 Starting dashboard generation...")
    print(f"⏰ Time: {dt.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # injuries
    nba_injured_norm, nba_injury_details = fetch_espn_injuries("nba")
    nfl_injured_norm, nfl_injury_details = fetch_espn_injuries("nfl")

    print(f"🩺 NBA injured count: {len(nba_injured_norm)}")
    print(f"🩺 NFL injured count: {len(nfl_injured_norm)}")

    nba_props = generate_top_props_for_league("nba", nba_injured_norm, nba_injury_details)
    nfl_props = generate_top_props_for_league("nfl", nfl_injured_norm, nfl_injury_details)

    html = generate_html(nba_props, nfl_props)
    with open("AI_Prediction_Engine.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Wrote AI_Prediction_Engine.html")
    print(f"🏀 NBA picks: {len(nba_props)} | 🏈 NFL picks: {len(nfl_props)}")

if __name__ == "__main__":
    main()
