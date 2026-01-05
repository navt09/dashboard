#!/usr/bin/env python3
"""
Automated Prop-Bet Scouting Dashboard (NBA + NFL) — ALL PLAYERS VERSION

What it does:
- Pulls REAL player prop lines from The Odds API (free tier + api key required)
- Pulls TODAY's events from The Odds API
- Builds ESPN team map + rosters for teams playing today to resolve:
    player name -> team abbr -> opponent abbr -> correct matchup
- Pulls ESPN injuries and removes OUT/INACTIVE/IR/DOUBTFUL players
- Scores BOTH Over and Under using a rules-based "edge" model
- Adds requested macro factors:
    * Blowout risk (star sits in 4th)
    * Underdog vs favorite usage changes
    * NFL run-heavy vs pass-heavy scripts
    * Garbage-time inflation/deflation
- Generates AI_Prediction_Engine.html

Notes:
- You can keep your existing static player dictionaries. This script uses them as a boost/override when present.
- For players NOT in your static dictionaries, it uses a "fallback profile" built from the prop line + context
  (so you can still evaluate all players without paying for a full stats API).
"""

import os
import math
import json
import statistics
from datetime import datetime as dt, timezone
import requests

# =============================================================================
# YOUR EXISTING STATIC DATA (PASTE YOUR FULL DICTS HERE)
# =============================================================================
# Keep exactly as you have them now (no changes needed).
# If you already have these in your repo file, paste them as-is.

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

NBA_SPORT_KEY = "basketball_nba"
NFL_SPORT_KEY = "americanfootball_nfl"

# Player prop markets (Odds API)
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
    "player_pass_rush_yds",
    "player_rush_reception_yds",
    "player_pass_rush_reception_yds",
]

# Main markets for spread/total to infer game script
MAIN_MARKETS = ["spreads", "totals"]

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

CACHE_DIR = "cache"
ROSTER_CACHE_NBA = os.path.join(CACHE_DIR, "nba_rosters.json")
ROSTER_CACHE_NFL = os.path.join(CACHE_DIR, "nfl_rosters.json")
TEAMMAP_CACHE_NBA = os.path.join(CACHE_DIR, "nba_teammap.json")
TEAMMAP_CACHE_NFL = os.path.join(CACHE_DIR, "nfl_teammap.json")
INJURY_CACHE_NBA = os.path.join(CACHE_DIR, "nba_injuries.json")
INJURY_CACHE_NFL = os.path.join(CACHE_DIR, "nfl_injuries.json")

# =============================================================================
# HELPERS
# =============================================================================

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))

def ensure_cache_dir():
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

def _safe_get_json(url, timeout=15, headers=None, params=None):
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, timeout=timeout, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    fixes = {
        "Shai Gilgeous Alexander": "Shai Gilgeous-Alexander",
    }
    return fixes.get(s, s)

def format_time_local(iso_time: str):
    try:
        t = dt.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone(timezone.utc)
        return t.strftime("%I:%M %p UTC")
    except Exception:
        return iso_time

# =============================================================================
# ESPN: TEAM MAP + ROSTERS + INJURIES
# =============================================================================

def espn_team_map(league: str, use_cache=True):
    """
    Returns dict: displayName -> {"id": "...", "abbr": "..."}
    """
    ensure_cache_dir()
    cache_path = TEAMMAP_CACHE_NBA if league == "nba" else TEAMMAP_CACHE_NFL
    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
           if league == "nba"
           else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")
    data = _safe_get_json(url)

    out = {}
    sports = data.get("sports", [])
    if not sports:
        return out
    leagues = sports[0].get("leagues", [])
    if not leagues:
        return out

    for t in leagues[0].get("teams", []):
        team = t.get("team", {})
        name = team.get("displayName", "")
        out[name] = {"id": team.get("id", ""), "abbr": team.get("abbreviation", "")}

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    except Exception:
        pass

    return out

def espn_team_roster(team_id: str, league: str):
    """
    Returns list of {"name": displayName, "athlete_id": id}
    """
    if league == "nba":
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
    else:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster"

    data = _safe_get_json(url)
    athletes = []

    # ESPN roster structures vary; handle common cases
    roster = data.get("athletes") or data.get("team", {}).get("athletes") or []
    if isinstance(roster, list):
        # may be grouped by position in "athletes"
        for group in roster:
            if isinstance(group, dict) and "items" in group:
                for a in group.get("items", []):
                    name = a.get("displayName")
                    aid = a.get("id")
                    if name and aid:
                        athletes.append({"name": name, "athlete_id": str(aid)})
            elif isinstance(group, dict) and group.get("displayName") and group.get("id"):
                athletes.append({"name": group["displayName"], "athlete_id": str(group["id"])})
    return athletes

def build_today_roster_index(league: str, team_display_names: set[str], use_cache=True):
    """
    Builds:
      roster_index: {abbr: set(playerNames)}
      player_to_team: {playerName: abbr}
      player_to_athlete_id: {playerName: athlete_id}
    Only for teams playing today.
    """
    ensure_cache_dir()
    cache_path = ROSTER_CACHE_NBA if league == "nba" else ROSTER_CACHE_NFL

    team_map = espn_team_map(league, use_cache=use_cache)

    # Load roster cache file if present
    cached = {}
    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)  # {abbr: {"updated": "...", "players": [{"name":..,"athlete_id":..}, ...]}}
        except Exception:
            cached = {}

    roster_index = {}
    player_to_team = {}
    player_to_athlete_id = {}

    for team_name in team_display_names:
        meta = team_map.get(team_name)
        if not meta:
            continue
        abbr = meta.get("abbr", "")
        tid = meta.get("id", "")
        if not abbr or not tid:
            continue

        roster_list = None
        if use_cache and abbr in cached and isinstance(cached[abbr], dict) and "players" in cached[abbr]:
            roster_list = cached[abbr]["players"]

        if roster_list is None:
            try:
                roster_list = espn_team_roster(tid, league)
            except Exception:
                roster_list = []

            # update cache
            cached[abbr] = {"updated": dt.now(timezone.utc).isoformat(), "players": roster_list}

        names = set()
        for p in roster_list:
            nm = p.get("name")
            aid = p.get("athlete_id")
            if not nm:
                continue
            names.add(nm)
            player_to_team[nm] = abbr
            if aid:
                player_to_athlete_id[nm] = str(aid)

        roster_index[abbr] = names

    # Save updated cache
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=2)
    except Exception:
        pass

    return roster_index, player_to_team, player_to_athlete_id

def fetch_espn_injuries(league: str, use_cache=True):
    """
    Returns:
      injured_set: set(playerName)
      player_status: dict playerName -> {"status": "...", "team": "ABBR"}
      team_injured_counts: dict abbr -> count
    """
    ensure_cache_dir()
    cache_path = INJURY_CACHE_NBA if league == "nba" else INJURY_CACHE_NFL

    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            injured = set(blob.get("injured", []))
            status = blob.get("status", {})
            team_counts = blob.get("team_counts", {})
            return injured, status, team_counts
        except Exception:
            pass

    team_map = espn_team_map(league, use_cache=True)

    injured = set()
    status = {}
    team_counts = {}

    for team_name, meta in team_map.items():
        tid = meta.get("id", "")
        abbr = meta.get("abbr", "")
        if not tid or not abbr:
            continue

        if league == "nba":
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{tid}?enable=injuries"
        else:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}?enable=injuries"

        try:
            data = _safe_get_json(url)
            inj_list = data.get("team", {}).get("injuries", []) or data.get("injuries", []) or []
            for inj in inj_list:
                athlete = inj.get("athlete", {}) or {}
                name = athlete.get("displayName")
                st = inj.get("status", {}).get("name") or inj.get("status") or ""
                st_upper = str(st).upper()

                # Treat these as "do not play"
                if any(x in st_upper for x in ["OUT", "INACTIVE", "DOUBTFUL", "DNP", "IR"]):
                    if name:
                        injured.add(name)
                        status[name] = {"status": st, "team": abbr}
                        team_counts[abbr] = team_counts.get(abbr, 0) + 1
        except Exception:
            continue

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {"updated": dt.now(timezone.utc).isoformat(),
                 "injured": sorted(list(injured)),
                 "status": status,
                 "team_counts": team_counts},
                f,
                indent=2
            )
    except Exception:
        pass

    return injured, status, team_counts

# =============================================================================
# THE ODDS API: EVENTS + ODDS
# =============================================================================

def require_api_key():
    if not ODDS_API_KEY:
        raise RuntimeError("Missing ODDS_API_KEY. Add it as a GitHub Secret or env var.")

def oddsapi_get_events(sport_key: str):
    """
    /v4/sports/{sport}/events
    """
    require_api_key()
    url = f"{ODDS_API_HOST}/v4/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY, "dateFormat": "iso"}
    return requests.get(url, params=params, timeout=20).json()

def oddsapi_get_event_odds(sport_key: str, event_id: str, markets: list[str]):
    """
    /v4/sports/{sport}/events/{eventId}/odds
    """
    require_api_key()
    url = f"{ODDS_API_HOST}/v4/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

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

def parse_player_prop_lines(event_odds_json: dict):
    """
    Returns list of items:
      {player, market_key, consensus_line, points_list, over_prices, under_prices}
    Uses median point across books for consensus line.
    """
    lines_by = {}   # (player, market_key) -> list(points)
    prices_by = {}  # (player, market_key, side, point) -> list(prices)

    for book in event_odds_json.get("bookmakers", []):
        for m in book.get("markets", []):
            mkey = m.get("key")
            for out in m.get("outcomes", []):
                player = normalize_player_name(out.get("description") or out.get("name") or "")
                side = (out.get("name") or "").strip().lower()  # over/under
                point = out.get("point", None)
                price = out.get("price", None)
                if not player or point is None or side not in ("over", "under"):
                    continue
                k = (player, mkey)
                lines_by.setdefault(k, []).append(float(point))
                prices_by.setdefault((player, mkey, side, float(point)), []).append(price)

    parsed = []
    for (player, mkey), pts in lines_by.items():
        if not pts:
            continue
        consensus = float(statistics.median(pts))
        stdev = float(statistics.pstdev(pts)) if len(pts) >= 2 else 0.0

        # Use most common point to fetch a representative price (optional)
        point_mode = max(set(pts), key=pts.count)
        over_prices = prices_by.get((player, mkey, "over", float(point_mode)), [])
        under_prices = prices_by.get((player, mkey, "under", float(point_mode)), [])

        parsed.append({
            "player": player,
            "market_key": mkey,
            "line": consensus,
            "line_stdev": stdev,
            "over_price": over_prices[0] if over_prices else None,
            "under_price": under_prices[0] if under_prices else None,
        })
    return parsed

def parse_main_lines(event_odds_json: dict, home_team: str, away_team: str):
    """
    Extract spread (from perspective of home/away) and total if available.
    Returns:
      {"spread_home": float|None, "spread_away": float|None, "total": float|None}
    """
    spread_home = None
    spread_away = None
    total = None

    # Search across all books; pick median if multiple available
    home_spreads = []
    away_spreads = []
    totals = []

    for book in event_odds_json.get("bookmakers", []):
        for m in book.get("markets", []):
            key = m.get("key")
            if key == "spreads":
                for out in m.get("outcomes", []):
                    nm = out.get("name")
                    pt = out.get("point", None)
                    if pt is None or not nm:
                        continue
                    if nm == home_team:
                        home_spreads.append(float(pt))
                    elif nm == away_team:
                        away_spreads.append(float(pt))
            elif key == "totals":
                for out in m.get("outcomes", []):
                    nm = (out.get("name") or "").lower()
                    pt = out.get("point", None)
                    if pt is None:
                        continue
                    # totals outcomes are usually Over/Under, same point
                    if nm in ("over", "under"):
                        totals.append(float(pt))

    if home_spreads:
        spread_home = float(statistics.median(home_spreads))
    if away_spreads:
        spread_away = float(statistics.median(away_spreads))
    if totals:
        total = float(statistics.median(totals))

    return {"spread_home": spread_home, "spread_away": spread_away, "total": total}

# =============================================================================
# TEAM ABBR LOOKUP FOR OPPONENT_DEFENSE TABLES
# =============================================================================

def abbreviate_team(team_name: str, league: str) -> str:
    """
    Minimal mapping.
    Expand this for better coverage. If unknown, returns "".
    """
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

# =============================================================================
# SCRIPT / BLOWOUT / GARBAGE TIME FACTORS
# =============================================================================

def compute_blowout_risk(spread_abs: float | None) -> float:
    """
    0..1 based on spread magnitude.
    """
    if spread_abs is None:
        return 0.25
    # 0 at ~0, ~0.5 at 10, ~0.8 at 18+
    return float(clamp((spread_abs / 18.0), 0.0, 1.0))

def nba_game_script_multiplier(is_favorite: bool, blowout_risk: float, is_star: bool):
    """
    Returns multiplier that deflates stars in high blowout risk (4Q sit),
    and slightly boosts underdogs (more usage / catch-up).
    """
    mult = 1.0

    # Star sit deflation if favorite and blowout risk high
    if is_star and is_favorite:
        mult *= (1.0 - 0.10 * blowout_risk)  # up to -10%
    # Underdog stars can see higher usage (catch-up offense)
    if is_star and (not is_favorite):
        mult *= (1.0 + 0.06 * blowout_risk)  # up to +6%

    return mult

def nfl_script_adjustments(is_favorite: bool, spread_abs: float | None):
    """
    Returns tuple (pass_mult, rush_mult) for expected script.
    Favored big -> run-heavy. Underdog big -> pass-heavy.
    """
    if spread_abs is None:
        return 1.0, 1.0

    # Normalize 0..1 across ~0..14
    x = float(clamp(spread_abs / 14.0, 0.0, 1.0))
    if is_favorite:
        # run-heavy: less pass volume, more rush
        pass_mult = 1.0 - 0.10 * x
        rush_mult = 1.0 + 0.10 * x
    else:
        # pass-heavy: more pass volume, less rush
        pass_mult = 1.0 + 0.12 * x
        rush_mult = 1.0 - 0.08 * x
    return pass_mult, rush_mult

def garbage_time_multiplier(blowout_risk: float, is_star: bool):
    """
    Generic adjustment:
    - Stars deflate in garbage time
    - Non-stars can inflate slightly (more late run)
    """
    if is_star:
        return 1.0 - 0.06 * blowout_risk
    return 1.0 + 0.04 * blowout_risk

# =============================================================================
# EDGE MODEL (projection + score)
# =============================================================================

def projection_from_profile(profile: dict, prop_type: str, league: str):
    """
    If we have a profile (static db), use it.
    Otherwise return None and rely on fallback.
    """
    if not profile:
        return None

    if league == "nba":
        if prop_type == "points":
            return profile.get("recent_ppg", None)
        if prop_type == "rebounds":
            return profile.get("recent_rpg", None)
        if prop_type == "assists":
            return profile.get("recent_apg", None)
        if prop_type == "3_pointers":
            return profile.get("recent_3pm", None)
        if prop_type == "steals":
            return profile.get("recent_stl", None)
        if prop_type == "blocks":
            return profile.get("recent_blk", None)
        if prop_type == "field_goals":
            return profile.get("fgm", None)
        if prop_type == "free_throws":
            ft_rate = profile.get("ft_rate", 0.25)
            ppg = profile.get("recent_ppg", 0)
            ft_att = (ppg * ft_rate) / 0.75
            return ft_att * 0.75
        if prop_type == "pts_reb":
            return (profile.get("recent_ppg", 0) + profile.get("recent_rpg", 0))
        if prop_type == "pts_ast":
            return (profile.get("recent_ppg", 0) + profile.get("recent_apg", 0))
        if prop_type == "reb_ast":
            return (profile.get("recent_rpg", 0) + profile.get("recent_apg", 0))
        if prop_type == "pts_reb_ast":
            return (profile.get("recent_ppg", 0) + profile.get("recent_rpg", 0) + profile.get("recent_apg", 0))
        if prop_type == "stl_blk":
            return (profile.get("recent_stl", 0) + profile.get("recent_blk", 0))
        if prop_type == "turnovers":
            # approximate using usage if present
            usage = profile.get("usage_rate", 25)
            return 2.5 + (usage - 25) / 20.0
        return None

    # NFL
    if prop_type == "pass_yards":
        return profile.get("recent_pass_yds", None)
    if prop_type == "pass_td":
        return profile.get("recent_pass_td", None)
    if prop_type == "int":
        return profile.get("recent_int", None)
    if prop_type == "rush_yards":
        return profile.get("recent_rush_yds", None)
    if prop_type == "carries":
        ry = profile.get("recent_rush_yds", None)
        return (ry / 4.5) if ry is not None else None
    if prop_type == "receptions":
        return profile.get("recent_rec", None)
    if prop_type == "rec_yards":
        return profile.get("recent_rec_yds", None)
    if prop_type == "rec_td":
        return profile.get("recent_rec_td", None)
    if prop_type == "pass_rush_yards":
        return (profile.get("recent_pass_yds", 0) + profile.get("recent_rush_yds", 0))
    if prop_type == "rush_rec_yards":
        return (profile.get("recent_rush_yds", 0) + profile.get("recent_rec_yds", 0))
    if prop_type == "pass_rush_rec_yards":
        return (profile.get("recent_pass_yds", 0) + profile.get("recent_rush_yds", 0) + profile.get("recent_rec_yds", 0))
    return None

def apply_context_multipliers(proj: float, league: str, prop_type: str, ctx: dict, profile: dict | None):
    """
    Apply matchup/script/blowout/garbage-time/injury-based adjustments.
    """
    if proj is None:
        return None

    opp_abbr = ctx.get("opponent_abbr", "")
    is_favorite = ctx.get("is_favorite", None)
    spread_abs = ctx.get("spread_abs", None)
    blowout_risk = compute_blowout_risk(spread_abs)

    # "star" heuristic (if we know usage/per_minute)
    is_star = False
    if profile:
        usage = float(profile.get("usage_rate", 0) or 0)
        per_min = float(profile.get("per_minute", 0) or 0)
        is_star = (usage >= 28.0) or (per_min >= 1.75)

    # opponent pace
    if league == "nba":
        pace_adj = OPPONENT_DEFENSE["nba"].get(opp_abbr, {}).get("pace_adjust", 1.0)
        proj *= float(pace_adj)

        # favorite/underdog usage changes + blowout sit
        if is_favorite is not None:
            proj *= nba_game_script_multiplier(is_favorite, blowout_risk, is_star)

        # garbage time
        proj *= garbage_time_multiplier(blowout_risk, is_star)

        # team injury usage bump: more injured teammates => more volume for remaining players
        team_inj = float(ctx.get("team_inj_count", 0))
        proj *= (1.0 + min(0.08, team_inj * 0.02))  # up to +8%

        # opponent injury bump: weaker defense => small boost
        opp_inj = float(ctx.get("opp_inj_count", 0))
        proj *= (1.0 + min(0.05, opp_inj * 0.015))  # up to +5%

        # referee FT boost slightly helps scoring props
        if prop_type in ("points", "pts_reb", "pts_ast", "pts_reb_ast", "free_throws", "field_goals"):
            ft_boost = float(REFEREE_TENDENCIES["nba"].get("ft_rate_boost", 1.0))
            proj *= (1.0 + (ft_boost - 1.0) * 0.35)

    else:
        # NFL: run-heavy vs pass-heavy script
        if is_favorite is not None:
            pass_mult, rush_mult = nfl_script_adjustments(is_favorite, spread_abs)
        else:
            pass_mult, rush_mult = (1.0, 1.0)

        # apply by prop type
        if prop_type in ("pass_yards",):
            proj *= pass_mult
        elif prop_type in ("pass_td",):
            proj *= (1.0 + (pass_mult - 1.0) * 0.6)
        elif prop_type in ("rush_yards", "carries"):
            proj *= rush_mult

        # garbage time: if heavy underdog, pass volume can inflate late
        blowout_risk = compute_blowout_risk(spread_abs)
        if is_favorite is not None and (not is_favorite):
            if prop_type in ("pass_yards", "receptions", "rec_yards"):
                proj *= (1.0 + 0.06 * blowout_risk)

        # injuries: same idea
        team_inj = float(ctx.get("team_inj_count", 0))
        proj *= (1.0 + min(0.06, team_inj * 0.02))
        opp_inj = float(ctx.get("opp_inj_count", 0))
        proj *= (1.0 + min(0.04, opp_inj * 0.015))

        # referee DPI (pass-friendliness) helps pass props a bit
        if prop_type in ("pass_yards", "receptions", "rec_yards"):
            dpi = float(REFEREE_TENDENCIES["nfl"].get("dpi_rate", 0.30))
            proj *= (1.0 + (dpi - 0.25) * 0.25)

        # weather impact if present
        if profile:
            weather = float(profile.get("weather_impact", 1.0))
            proj *= weather

    return proj

def edge_score_from_projection(proj: float, line: float, side: str, line_stdev: float = 0.0):
    """
    Convert projection difference into a 0-100 edge score for that side.
    Adds a penalty if the line is very noisy across books (high stdev).
    """
    if line <= 0:
        return 0.0

    diff = proj - line
    if side == "under":
        diff = -diff

    # Typical variance scaling
    scale = max(1.0, line * 0.12)
    z = diff / scale

    p = sigmoid(z)
    score = 100.0 * p

    # If books disagree on the line, reduce confidence
    # (You can flip this if you want to hunt disagreement, but most people prefer stability.)
    score *= (1.0 - min(0.20, line_stdev * 0.15))

    return float(clamp(score, 0.0, 100.0))

def score_prop(player: str, prop_type: str, line: float, league: str, ctx: dict, line_stdev: float):
    """
    Returns:
      (best_score, best_side, proj, breakdown)
    """
    breakdown = {}

    # choose profile:
    profile = None
    if league == "nba":
        profile = NBA_PLAYERS_DATA.get(player)
    else:
        profile = NFL_PLAYERS_DATA.get(player)

    base_proj = projection_from_profile(profile or {}, prop_type, league)

    # Fallback projection for players without a profile:
    # Start at line, then let context push it slightly.
    if base_proj is None:
        base_proj = float(line)

        # small nudge: pace/script/opponent defense
        opp_abbr = ctx.get("opponent_abbr", "")
        if league == "nba":
            pace = float(OPPONENT_DEFENSE["nba"].get(opp_abbr, {}).get("pace_adjust", 1.0))
            base_proj *= pace
        else:
            # pass defense / run defense ranks nudge volume props
            opp_def = OPPONENT_DEFENSE["nfl"].get(opp_abbr, {})
            if prop_type == "pass_yards":
                pass_rank = float(opp_def.get("pass_rank", 16))
                base_proj *= (1.0 + (pass_rank - 16.0) / 140.0)
            if prop_type in ("rush_yards", "carries"):
                run_rank = float(opp_def.get("run_rank", 16))
                base_proj *= (1.0 + (run_rank - 16.0) / 160.0)

        breakdown["Fallback Profile"] = 1.0

    # apply macro factors
    proj = apply_context_multipliers(base_proj, league, prop_type, ctx, profile)

    # breakdown visibility
    breakdown["Proj vs Line"] = (proj - line)
    breakdown["Line Stdev"] = line_stdev

    # include key script factors for display
    spread_abs = ctx.get("spread_abs", None)
    if spread_abs is not None:
        breakdown["Blowout Risk"] = compute_blowout_risk(spread_abs) * 10.0
    if ctx.get("is_favorite") is True:
        breakdown["Favorite"] = 2.0
    elif ctx.get("is_favorite") is False:
        breakdown["Underdog"] = 2.0

    breakdown["Team Injuries"] = float(ctx.get("team_inj_count", 0)) * 2.0
    breakdown["Opp Injuries"] = float(ctx.get("opp_inj_count", 0)) * 1.5

    # full model factors (if profile exists)
    if profile:
        if league == "nba":
            breakdown["Usage"] = min(10, float(profile.get("usage_rate", 25)) / 3.0)
            breakdown["Efficiency"] = min(8, float(profile.get("efficiency", 0.58)) * 12)
            breakdown["Rest"] = min(6, float(profile.get("rest_days", 1)) * 2.5)
        else:
            breakdown["Route Part"] = min(10, float(profile.get("route_participation", 0.80)) * 10)
            breakdown["Pressure Risk"] = -6 if float(profile.get("pressure_to_sack", 0.15)) > 0.20 else 2
            breakdown["Injury Risk"] = -6 if float(profile.get("injury_risk", 0.10)) > 0.15 else 2

    # score BOTH sides
    over = edge_score_from_projection(proj, line, "over", line_stdev)
    under = edge_score_from_projection(proj, line, "under", line_stdev)

    if under > over:
        return under, "UNDER", proj, breakdown
    return over, "OVER", proj, breakdown

# =============================================================================
# PROP COLLECTION (ALL PLAYERS, REAL LINES)
# =============================================================================

def resolve_player_team(player_name: str, player_to_team: dict, home_abbr: str, away_abbr: str):
    """
    Resolve player -> team abbr, but only accept if it's one of the teams in this game.
    """
    team = player_to_team.get(player_name)
    if team in (home_abbr, away_abbr):
        return team
    return None

def pick_opponent(team_abbr: str, home_abbr: str, away_abbr: str):
    if team_abbr == home_abbr:
        return away_abbr
    if team_abbr == away_abbr:
        return home_abbr
    return ""

def is_team_favorite(team_abbr: str, home_abbr: str, away_abbr: str, spread_home: float | None, spread_away: float | None):
    """
    Determine favorite using spreads:
      negative spread for a team typically means favorite
    """
    if team_abbr == home_abbr and spread_home is not None:
        return (spread_home < 0)
    if team_abbr == away_abbr and spread_away is not None:
        return (spread_away < 0)
    return None

def generate_top_props_for_league(league: str, keep_top: int = 8):
    """
    Pull events -> build today's roster mapping -> pull injuries -> pull odds -> parse -> score -> top picks.
    """
    if league == "nba":
        sport_key = NBA_SPORT_KEY
        markets = NBA_MARKETS
        market_to_prop = NBA_MARKET_TO_PROP
    else:
        sport_key = NFL_SPORT_KEY
        markets = NFL_MARKETS
        market_to_prop = NFL_MARKET_TO_PROP

    print(f"📅 Fetching {league.upper()} events from Odds API...")
    events = oddsapi_get_events(sport_key)
    games = build_games_from_events(events)

    # Teams playing today (by display name, because ESPN team map uses displayName)
    teams_today = set()
    for g in games:
        if g["home_team"]:
            teams_today.add(g["home_team"])
        if g["away_team"]:
            teams_today.add(g["away_team"])

    # Build roster mapping for TODAY'S teams
    print(f"👥 Building {league.upper()} roster index (today's teams only)...")
    team_map = espn_team_map(league, use_cache=True)
    name_to_abbr = get_team_abbr_map(league)
    # Note: we pass team display names; ESPN map is keyed by displayName
    roster_index, player_to_team, player_to_athlete_id = build_today_roster_index(
        league,
        team_display_names=teams_today,
        use_cache=True
    )

    # Injuries
    print(f"🩺 Fetching {league.upper()} injuries...")
    injured_set, injured_status, team_inj_counts = fetch_espn_injuries(league, use_cache=True)

    picks = []

    for g in games:
        event_id = g["id"]
        if not event_id:
            continue

        # Team abbreviations for opponent-defense tables + internal matching
        # (If abbreviate_team doesn't know the team, we still can do rosters + matchups correctly,
        #  but OPPONENT_DEFENSE boosts won't apply.)
        home_abbr = abbreviate_team(g["home_team"], league, name_to_abbr)
        away_abbr = abbreviate_team(g["away_team"], league, name_to_abbr)


        # Pull main lines (spreads/totals) once per event
        try:
            main_odds = oddsapi_get_event_odds(sport_key, event_id, MAIN_MARKETS)
            main_lines = parse_main_lines(main_odds, g["home_team"], g["away_team"])
        except Exception:
            main_lines = {"spread_home": None, "spread_away": None, "total": None}

        spread_home = main_lines.get("spread_home")
        spread_away = main_lines.get("spread_away")
        spread_abs = None
        if spread_home is not None:
            spread_abs = abs(float(spread_home))
        elif spread_away is not None:
            spread_abs = abs(float(spread_away))

        # Pull player prop lines
        try:
            odds = oddsapi_get_event_odds(sport_key, event_id, markets)
        except Exception:
            continue

        lines = parse_player_prop_lines(odds)

        for item in lines:
            player = item["player"]
            market_key = item["market_key"]
            line = float(item["line"])
            line_stdev = float(item.get("line_stdev", 0.0))

            if market_key not in market_to_prop:
                continue

            prop_type = market_to_prop[market_key]

            # Resolve player -> team -> opponent (correct matchup)
            # First: try exact, then try a basic fallback: scan rosters for substring match (rare name mismatches)
            player_team = resolve_player_team(player, player_to_team, home_abbr, away_abbr)
            if player_team is None:
                # Attempt simple roster fuzzy: normalize and compare lowercase without punctuation
                pl = player.lower().replace(".", "").replace("-", " ").strip()
                found = None
                for abbr in (home_abbr, away_abbr):
                    roster_names = roster_index.get(abbr, set())
                    for rn in roster_names:
                        rl = rn.lower().replace(".", "").replace("-", " ").strip()
                        if rl == pl:
                            found = abbr
                            break
                    if found:
                        break
                player_team = found

            if player_team is None:
                # Can't confidently place player in this game -> skip
                continue

            # Injury filter
            if player in injured_set:
                continue

            opp_abbr = pick_opponent(player_team, home_abbr, away_abbr)

            # favorite/underdog
            fav = is_team_favorite(player_team, home_abbr, away_abbr, spread_home, spread_away)

            ctx = {
                "team_abbr": player_team,
                "opponent_abbr": opp_abbr,
                "is_favorite": fav,
                "spread_abs": spread_abs,
                "total": main_lines.get("total"),
                "team_inj_count": float(team_inj_counts.get(player_team, 0)),
                "opp_inj_count": float(team_inj_counts.get(opp_abbr, 0)),
            }

            score, side, proj, breakdown = score_prop(
                player=player,
                prop_type=prop_type,
                line=line,
                league=league,
                ctx=ctx,
                line_stdev=line_stdev
            )

            # Keep only meaningful edges
            if score < 65:
                continue

            # Build correct matchup string
            matchup = g["matchup"]
            time_str = g["time"]

            picks.append({
                "player": player,
                "prop_type": prop_type,
                "line": line,
                "side": side,
                "proj": proj,
                "edge_score": score,
                "matchup": matchup,
                "time": time_str,
                "breakdown": breakdown,
            })

    picks.sort(key=lambda x: x["edge_score"], reverse=True)
    return picks[:keep_top]

# =============================================================================
# HTML OUTPUT
# =============================================================================

def generate_factor_html(breakdown):
    html = '<div class="factor-breakdown">'
    items = sorted(
        breakdown.items(),
        key=lambda x: abs(x[1]) if isinstance(x[1], (int, float)) else 0,
        reverse=True
    )[:6]

    for name, val in items:
        try:
            score = float(val)
        except Exception:
            score = 0.0

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

    return f"""
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
                <strong>📊 Real Line + Script-Aware Edge:</strong>
                Uses real sportsbook prop lines and chooses Over/Under based on projection vs line,
                adjusted for matchup, injuries, blowout risk, favorite/underdog usage, and (NFL) run/pass script.
            </div>

            <span class="risk-indicator {'low' if confidence_color == 'high' else 'medium'}-risk">Best-value selection</span>
        </div>
    """

def generate_html(nba_props, nfl_props):
    now = dt.now()
    today_date = now.strftime("%B %d, %Y")
    last_updated = now.strftime("%B %d, %Y at %I:%M %p")

    nba_cards = "".join(generate_prediction_card(p) for p in nba_props) \
        if nba_props else '<p style="color: var(--color-text-secondary);">No high-edge NBA props found.</p>'
    nfl_cards = "".join(generate_prediction_card(p) for p in nfl_props) \
        if nfl_props else '<p style="color: var(--color-text-secondary);">No high-edge NFL props found.</p>'

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>🤖 Advanced Prop Analyzer</title>
<style>
:root {
    --color-bg: #0a0e27;
    --color-surface: #1a1f3a;
    --color-border: #2d3748;
    --color-text: #f1f5f9;
    --color-text-secondary: #cbd5e1;
    --shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, var(--color-bg) 0%, #0f1729 100%);
    color: var(--color-text);
    padding: 20px;
    min-height: 100vh;
}
.header {
    text-align: center;
    margin-bottom: 40px;
    border-bottom: 2px solid var(--color-border);
    padding-bottom: 20px;
}
.header h1 {
    font-size: 2.4em;
    margin-bottom: 10px;
    background: linear-gradient(135deg, #00d4ff, #0099ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.header-badge {
    display: inline-block;
    background: rgba(0, 212, 255, 0.2);
    border: 1px solid #00d4ff;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 0.9em;
    color: #00d4ff;
    margin-bottom: 10px;
    font-weight: 600;
}
.methodology {
    background: rgba(0, 212, 255, 0.05);
    border: 1px solid rgba(0, 212, 255, 0.2);
    padding: 15px;
    border-radius: 8px;
    color: var(--color-text-secondary);
    font-size: 0.85em;
    margin-top: 10px;
    line-height: 1.6;
}
.container { max-width: 1600px; margin: 0 auto; }
.controls-section {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 30px;
    box-shadow: var(--shadow);
}
.league-tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
.league-tab {
    padding: 10px 20px;
    border: 2px solid var(--color-border);
    background: transparent;
    color: var(--color-text);
    cursor: pointer;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.3s ease;
}
.league-tab:hover {
    border-color: #00d4ff;
    background: rgba(0, 212, 255, 0.1);
}
.league-tab.active {
    background: linear-gradient(135deg, #00d4ff, #0099ff);
    border-color: #00d4ff;
    color: #000;
}
.league-content { display: none; }
.league-content.active { display: block; }

.prediction-card {
    background: var(--color-surface);
    border: 2px solid var(--color-border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    transition: all 0.3s ease;
}
.prediction-card:hover {
    border-color: #00d4ff;
    box-shadow: 0 8px 24px rgba(0, 212, 255, 0.1);
    transform: translateY(-2px);
}
.prediction-card.high-confidence { border-left: 5px solid #00ff88; }
.prediction-card.medium-confidence { border-left: 5px solid #ffaa00; }
.prediction-card.low-confidence { border-left: 5px solid #ff6b6b; }

.prediction-header {
    display: flex;
    justify-content: space-between;
    align-items: start;
    margin-bottom: 15px;
}
.prediction-title { font-size: 1.25em; font-weight: 700; }
.confidence-badge {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 0.9em;
    font-weight: 700;
    color: white;
}
.confidence-badge.high { background: linear-gradient(135deg, #00ff88, #00cc66); }
.confidence-badge.medium { background: linear-gradient(135deg, #ffaa00, #ff8800); }
.confidence-badge.low { background: linear-gradient(135deg, #ff6b6b, #cc0000); }

.factor-breakdown {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 12px;
    margin: 15px 0;
}
.factor-item {
    background: rgba(0, 212, 255, 0.05);
    border: 1px solid rgba(0, 212, 255, 0.2);
    padding: 12px;
    border-radius: 6px;
}
.factor-name {
    font-size: 0.85em;
    font-weight: 600;
    color: #00d4ff;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}
.factor-score-bar {
    background: rgba(0, 0, 0, 0.3);
    height: 20px;
    border-radius: 3px;
    overflow: hidden;
}
.factor-score-fill {
    height: 100%;
    width: 0%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7em;
    font-weight: 700;
    color: #000;
}
.ai-reasoning {
    background: rgba(0, 212, 255, 0.05);
    border-left: 3px solid #00d4ff;
    padding: 12px;
    border-radius: 6px;
    margin: 12px 0;
    font-size: 0.9em;
    line-height: 1.5;
    color: var(--color-text-secondary);
}
.risk-indicator {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: 600;
    margin-top: 10px;
    background: rgba(0, 255, 136, 0.15);
    color: #00ff88;
}
@media (max-width: 768px) {
    .header h1 { font-size: 1.8em; }
    .factor-breakdown { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="header">
    <div class="header-badge">🤖 ALL PLAYERS + REAL LINES</div>
    <h1>Advanced Prop Analyzer</h1>
    <p style="color: var(--color-text-secondary); font-size: 1.05em;">
        Scores Over + Under | Filters Injuries | Fixes Matchups | Script-Aware
    </p>
    <p style="color: var(--color-text-secondary); font-size: 0.95em; margin-top: 8px;">
        📊 __NBA_COUNT__ NBA Picks | 🏈 __NFL_COUNT__ NFL Picks
    </p>
    <div class="methodology">
        Picks are built from real sportsbook prop markets (Odds API), assigned to the correct game using ESPN rosters,
        filtered for OUT/IR/INACTIVE players via ESPN injuries, then scored using matchup + injury + script + blowout factors.
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
        <h2 style="font-size: 1.5em; margin: 30px 0 20px 0;">NBA Top Plays – __TODAY_DATE__</h2>
        __NBA_CARDS__
    </div>

    <div id="nfl" class="league-content">
        <h2 style="font-size: 1.5em; margin: 30px 0 20px 0;">NFL Top Plays – __TODAY_DATE__</h2>
        __NFL_CARDS__
    </div>
</div>

<div style="text-align: center; margin: 40px 0; color: var(--color-text-secondary); font-size: 0.9em;">
    <p>⚡ Updated Daily at 8:00 AM PST</p>
    <p>Last Updated: __LAST_UPDATED__</p>
    <p style="font-size: 0.85em; margin-top: 15px;">Disclaimer: informational only.</p>
</div>

<script>
document.querySelectorAll('.league-tab').forEach(tab => {
    tab.addEventListener('click', function() {
        const league = this.getAttribute('data-league');
        document.querySelectorAll('.league-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.league-content').forEach(c => c.classList.remove('active'));
        this.classList.add('active');
        document.getElementById(league).classList.add('active');
    });
});
</script>

</body>
</html>
"""

    html = (html
        .replace("__NBA_CARDS__", nba_cards)
        .replace("__NFL_CARDS__", nfl_cards)
        .replace("__TODAY_DATE__", today_date)
        .replace("__LAST_UPDATED__", last_updated)
        .replace("__NBA_COUNT__", str(len(nba_props)))
        .replace("__NFL_COUNT__", str(len(nfl_props)))
    )
    return html

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("🚀 Starting ALL-PLAYERS Prop Analyzer...")
    print(f"⏰ {dt.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not ODDS_API_KEY:
        raise RuntimeError("Set ODDS_API_KEY (GitHub Secret) before running.")

    print("🏀 Building NBA picks...")
    nba_top = generate_top_props_for_league("nba", keep_top=8)

    print("🏈 Building NFL picks...")
    nfl_top = generate_top_props_for_league("nfl", keep_top=8)

    html = generate_html(nba_top, nfl_top)

    out_file = "AI_Prediction_Engine.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Done. Wrote {out_file}")

if __name__ == "__main__":
    main()
