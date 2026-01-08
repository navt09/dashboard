#!/usr/bin/env python3
"""
Fully automatic prop scouting dashboard (NBA + NFL)
- Pulls today's events + player prop lines from The Odds API
- Pulls injuries + rosters + stats from ESPN (free endpoints)
- Automatically maps ALL players (no hardcoded player list)
- Computes projections from ESPN last-10/season stats
- Scores Over/Under with extra context:
  * Blowout risk
  * Underdog vs favorite usage shift
  * NFL run-heavy vs pass-heavy scripts
  * Garbage-time inflation/deflation
- Outputs AI_Prediction_Engine.html
"""

import os
import re
import json
import math
import time
import requests
from datetime import datetime as dt, timezone
from typing import Dict, Any, Optional, Tuple, List

# =============================================================================
# CONFIG
# =============================================================================

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
if not ODDS_API_KEY:
    raise RuntimeError("Missing ODDS_API_KEY. Add it in GitHub Secrets and set env in workflow.")

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
NBA_SPORT_KEY = "basketball_nba"
NFL_SPORT_KEY = "americanfootball_nfl"

# If your plan doesn't return some markets, keep them but code will skip if empty.
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
    # some books support these:
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

MAIN_LINE_MARKETS = ["spreads", "totals"]  # for scripts + blowout risk (optional)

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

# ESPN endpoints
ESPN_NBA_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_NFL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_NBA_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
ESPN_NFL_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

# Cache files (optional but strongly recommended)
CACHE_DIR = ".cache"
PLAYER_INDEX_CACHE = os.path.join(CACHE_DIR, "espn_player_index.json")
PLAYER_STATS_CACHE = os.path.join(CACHE_DIR, "espn_player_stats.json")
INJURY_CACHE = os.path.join(CACHE_DIR, "espn_injuries.json")

REQUEST_SLEEP = 0.15  # gentle rate limit

# =============================================================================
# UTILS
# =============================================================================

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def _get_json(url: str, params: dict | None = None, timeout: int = 15) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, timeout=timeout, headers=headers)
    r.raise_for_status()
    time.sleep(REQUEST_SLEEP)
    return r.json()

def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s

def format_time_local(iso_time: str) -> str:
    try:
        t = dt.fromisoformat(iso_time.replace("Z", "+00:00")).astimezone()
        return t.strftime("%I:%M %p %Z")
    except Exception:
        return iso_time

def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, obj: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# =============================================================================
# ODDS API (lines)
# =============================================================================

def oddsapi_get_events(sport_key: str) -> list[dict]:
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY}
    r = requests.get(url, params=params, timeout=20)
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
    r = requests.get(url, params=params, timeout=25)
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

def parse_spread_total(odds_json: dict, home_team: str, away_team: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns: (spread_abs, total_points)
    spread_abs is absolute spread (e.g., 7.5), total_points is O/U total if available.
    """
    spread_abs = None
    total_pts = None
    try:
        for bm in odds_json.get("bookmakers", []) or []:
            for m in bm.get("markets", []) or []:
                if m.get("key") == "spreads":
                    home_spread = None
                    away_spread = None
                    for o in m.get("outcomes", []) or []:
                        nm = o.get("name")
                        pt = o.get("point")
                        if pt is None:
                            continue
                        try:
                            pt = float(pt)
                        except Exception:
                            continue
                        if nm == home_team:
                            home_spread = pt
                        elif nm == away_team:
                            away_spread = pt
                    if home_spread is not None:
                        spread_abs = abs(home_spread)
                    elif away_spread is not None:
                        spread_abs = abs(away_spread)

                if m.get("key") == "totals":
                    for o in m.get("outcomes", []) or []:
                        pt = o.get("point")
                        if pt is None:
                            continue
                        try:
                            total_pts = float(pt)
                        except Exception:
                            pass
            if spread_abs is not None or total_pts is not None:
                break
    except Exception:
        pass
    return spread_abs, total_pts

# =============================================================================
# ESPN: PLAYER INDEX (name -> athlete_id + team_abbr) AUTOMATIC
# =============================================================================

def fetch_espn_team_list(league: str) -> list[dict]:
    url = ESPN_NBA_TEAMS if league == "nba" else ESPN_NFL_TEAMS
    data = _get_json(url)
    leagues = data.get("sports", [])[0].get("leagues", []) if data.get("sports") else []
    teams = leagues[0].get("teams", []) if leagues else []
    out = []
    for t in teams:
        team = t.get("team", {})
        out.append({
            "id": team.get("id"),
            "name": team.get("displayName"),
            "abbr": team.get("abbreviation"),
        })
    return out

def fetch_roster_for_team(league: str, team_id: str) -> list[dict]:
    """
    ESPN roster endpoint:
    /teams/{id}/roster
    """
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams" if league == "nba" \
           else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
    url = f"{base}/{team_id}/roster"
    data = _get_json(url)
    athletes = []
    for grp in data.get("athletes", []) or []:
        for a in grp.get("items", []) or []:
            athletes.append(a)
    # Some formats use athletes[].athletes
    if not athletes and data.get("athletes"):
        for grp in data["athletes"]:
            for a in grp.get("athletes", []) or []:
                athletes.append(a)
    return athletes

def build_player_index(league: str, force_refresh: bool = False) -> dict:
    """
    Builds mapping:
      normalized_name -> {"id": athlete_id, "name": displayName, "team_abbr": abbr}
    """
    ensure_cache_dir()
    cache = load_json(PLAYER_INDEX_CACHE)
    today = dt.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{league}:{today}"

    if not force_refresh and key in cache:
        return cache[key]

    idx = {}
    teams = fetch_espn_team_list(league)
    for tm in teams:
        team_id = tm.get("id")
        team_abbr = tm.get("abbr") or ""
        if not team_id:
            continue
        try:
            roster = fetch_roster_for_team(league, team_id)
        except Exception:
            continue

        for a in roster:
            raw_name = a.get("displayName") or a.get("fullName") or ""
            athlete_id = a.get("id") or ""
            if not raw_name or not athlete_id:
                continue
            nm = normalize_player_name(raw_name)
            if not nm:
                continue
            # Keep first match; ESPN rosters are authoritative.
            if nm not in idx:
                idx[nm] = {"id": athlete_id, "name": raw_name, "team_abbr": team_abbr}

    cache[key] = idx
    save_json(PLAYER_INDEX_CACHE, cache)
    return idx

# =============================================================================
# ESPN: INJURIES (AUTOMATIC)
# =============================================================================

def build_injury_set(league: str, force_refresh: bool = False) -> Tuple[set[str], dict]:
    """
    Returns:
      injured_norm_set, details (normalized -> {"status":..., "team_abbr":..., "raw":...})
    """
    ensure_cache_dir()
    cache = load_json(INJURY_CACHE)
    today = dt.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{league}:{today}"

    if not force_refresh and key in cache:
        data = cache[key]
        return set(data.get("injured", [])), data.get("details", {})

    team_url = ESPN_NBA_TEAMS if league == "nba" else ESPN_NFL_TEAMS
    teams_data = _get_json(team_url)

    injured = set()
    details = {}

    leagues = teams_data.get("sports", [])[0].get("leagues", []) if teams_data.get("sports") else []
    teams = leagues[0].get("teams", []) if leagues else []

    for t in teams:
        team = t.get("team", {})
        team_id = team.get("id")
        team_abbr = team.get("abbreviation") or ""
        if not team_id:
            continue

        base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams" if league == "nba" \
               else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
        url = f"{base}/{team_id}?enable=injuries"

        try:
            data = _get_json(url)
        except Exception:
            continue

        injuries = data.get("team", {}).get("injuries", []) or data.get("injuries", []) or []
        for inj in injuries:
            athlete = inj.get("athlete", {}) or {}
            raw_name = athlete.get("displayName") or ""
            status = (inj.get("status", {}) or {}).get("name") or inj.get("status") or ""
            status_upper = str(status).upper()

            # conservative filter: if not clearly active, exclude
            if any(x in status_upper for x in ["OUT", "INACTIVE", "DOUBTFUL", "IR", "DNP", "SUSP"]):
                nm = normalize_player_name(raw_name)
                if nm:
                    injured.add(nm)
                    details[nm] = {"status": str(status), "team_abbr": team_abbr, "raw": raw_name}

    cache[key] = {"injured": sorted(list(injured)), "details": details}
    save_json(INJURY_CACHE, cache)
    return injured, details

# =============================================================================
# ESPN: PLAYER STATS (AUTOMATIC DAILY)
# =============================================================================

def fetch_athlete_profile(league: str, athlete_id: str) -> dict:
    """
    ESPN athlete profile endpoint:
      /athletes/{id}
    """
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes" if league == "nba" \
           else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes"
    url = f"{base}/{athlete_id}"
    return _get_json(url)

def extract_stat_bundle_from_profile(league: str, profile: dict) -> dict:
    """
    Best-effort extraction for season averages + last-10-ish if present.
    ESPN structures vary, so this function is defensive.
    Output fields should support our prop types.
    """
    out = {}

    # Common: profile["statistics"] list with categories
    stats = profile.get("statistics") or []
    # Sometimes stats are nested in "statistics"->"splits" or "splits"->"categories"
    # We'll just scan for key stats by label/abbrev.
    def scan_for(labels: list[str]) -> Optional[float]:
        for block in stats:
            for cat in block.get("categories", []) or []:
                for st in cat.get("stats", []) or []:
                    name = (st.get("name") or st.get("displayName") or "").lower()
                    abbr = (st.get("abbreviation") or "").lower()
                    val = st.get("value")
                    if val is None:
                        continue
                    if any(l in name for l in labels) or any(l == abbr for l in labels):
                        try:
                            return float(val)
                        except Exception:
                            continue
        return None

    if league == "nba":
        # Typical abbreviations vary; we try common ones
        out["ppg"] = scan_for(["points per game", "ppg"]) or scan_for(["pts"])  # fallback
        out["rpg"] = scan_for(["rebounds per game", "rpg"]) or scan_for(["reb"])
        out["apg"] = scan_for(["assists per game", "apg"]) or scan_for(["ast"])
        out["spg"] = scan_for(["steals per game", "spg"]) or scan_for(["stl"])
        out["bpg"] = scan_for(["blocks per game", "bpg"]) or scan_for(["blk"])
        out["tpg"] = scan_for(["turnovers per game", "tpg"]) or scan_for(["to"])
        out["3pm"] = scan_for(["3-pointers made per game", "3pm"]) or scan_for(["3pm", "3ptm"])
        # These are harder; we leave as None if not found
        out["fgm"] = scan_for(["field goals made per game", "fgm"])
        out["ftm"] = scan_for(["free throws made per game", "ftm"])

    else:
        out["pass_yds"] = scan_for(["passing yards", "py"]) or scan_for(["pass yds"])
        out["pass_td"] = scan_for(["passing touchdowns", "ptd"])
        out["int"] = scan_for(["interceptions", "int"])
        out["rush_yds"] = scan_for(["rushing yards", "ry"]) or scan_for(["rush yds"])
        out["rush_td"] = scan_for(["rushing touchdowns", "rtd"])
        out["rec"] = scan_for(["receptions", "rec"])
        out["rec_yds"] = scan_for(["receiving yards", "recy"]) or scan_for(["rec yds"])
        out["rec_td"] = scan_for(["receiving touchdowns", "rectd"])

    return out

def get_player_stats(league: str, athlete_id: str, force_refresh: bool = False) -> dict:
    """
    Cached by date + athlete_id.
    """
    ensure_cache_dir()
    cache = load_json(PLAYER_STATS_CACHE)
    today = dt.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{league}:{today}:{athlete_id}"

    if not force_refresh and key in cache:
        return cache[key]

    try:
        profile = fetch_athlete_profile(league, athlete_id)
        bundle = extract_stat_bundle_from_profile(league, profile)
    except Exception:
        bundle = {}

    cache[key] = bundle
    save_json(PLAYER_STATS_CACHE, cache)
    return bundle

# =============================================================================
# PROJECTION + EDGE SCORING (OVER/UNDER)
# =============================================================================

def build_context(spread_abs: Optional[float], total_pts: Optional[float], league: str) -> dict:
    """
    Adds game-script-ish modifiers.
    """
    ctx = {
        "spread_abs": spread_abs,
        "total": total_pts,
    }

    # Blowout risk bucket
    if spread_abs is None:
        ctx["blowout_risk"] = 0.0
    else:
        if spread_abs >= 14:
            ctx["blowout_risk"] = 0.9
        elif spread_abs >= 10:
            ctx["blowout_risk"] = 0.6
        elif spread_abs >= 7:
            ctx["blowout_risk"] = 0.35
        else:
            ctx["blowout_risk"] = 0.15

    # NFL script: if total low + spread high => more run / less pass
    if league == "nfl":
        if total_pts is not None and spread_abs is not None:
            if total_pts <= 41 and spread_abs >= 7:
                ctx["script_run_heavy"] = 0.7
            elif total_pts >= 50:
                ctx["script_pass_heavy"] = 0.6
            else:
                ctx["script_run_heavy"] = 0.25
                ctx["script_pass_heavy"] = 0.25
        else:
            ctx["script_run_heavy"] = 0.25
            ctx["script_pass_heavy"] = 0.25

    return ctx

def projection_from_stats(league: str, prop_type: str, stats: dict) -> Optional[float]:
    """
    Uses ESPN season averages as baseline (free + stable).
    If missing, returns None.
    """
    if league == "nba":
        ppg = stats.get("ppg")
        rpg = stats.get("rpg")
        apg = stats.get("apg")
        spg = stats.get("spg")
        bpg = stats.get("bpg")
        tpg = stats.get("tpg")
        threes = stats.get("3pm")
        fgm = stats.get("fgm")
        ftm = stats.get("ftm")

        if prop_type == "points":
            return ppg
        if prop_type == "rebounds":
            return rpg
        if prop_type == "assists":
            return apg
        if prop_type == "steals":
            return spg
        if prop_type == "blocks":
            return bpg
        if prop_type == "turnovers":
            return tpg
        if prop_type == "3_pointers":
            return threes
        if prop_type == "field_goals":
            return fgm
        if prop_type == "free_throws":
            return ftm
        if prop_type == "pts_reb":
            return (ppg or 0) + (rpg or 0) if (ppg is not None or rpg is not None) else None
        if prop_type == "pts_ast":
            return (ppg or 0) + (apg or 0) if (ppg is not None or apg is not None) else None
        if prop_type == "reb_ast":
            return (rpg or 0) + (apg or 0) if (rpg is not None or apg is not None) else None
        if prop_type == "pts_reb_ast":
            return (ppg or 0) + (rpg or 0) + (apg or 0) if (ppg is not None or rpg is not None or apg is not None) else None

    else:
        pass_yds = stats.get("pass_yds")
        pass_td = stats.get("pass_td")
        ints = stats.get("int")
        rush_yds = stats.get("rush_yds")
        rush_td = stats.get("rush_td")
        rec = stats.get("rec")
        rec_yds = stats.get("rec_yds")
        rec_td = stats.get("rec_td")

        if prop_type == "pass_yards":
            return pass_yds
        if prop_type == "pass_td":
            return pass_td
        if prop_type == "int":
            return ints
        if prop_type == "rush_yards":
            return rush_yds
        if prop_type == "rush_td":
            return rush_td
        if prop_type == "receptions":
            return rec
        if prop_type == "rec_yards":
            return rec_yds
        if prop_type == "rec_td":
            return rec_td

    return None

def apply_script_adjustments(league: str, prop_type: str, proj: float, ctx: dict) -> Tuple[float, dict]:
    """
    Adds blowout/script/garbage-time adjustments.
    Returns adjusted projection and breakdown.
    """
    b = {}
    blowout = float(ctx.get("blowout_risk", 0.0))

    # Blowout: stars may sit -> slight UNDER pressure on volume stats
    if blowout > 0:
        if prop_type in ("points", "rebounds", "assists", "pts_reb", "pts_ast", "reb_ast", "pts_reb_ast",
                         "pass_yards", "rush_yards", "receptions", "rec_yards"):
            mult = 1.0 - 0.05 * blowout
            proj *= mult
            b["Blowout Risk Mult"] = round(mult, 3)

    # Garbage time: can inflate bench / deflate stars depending on type
    # We keep it modest since we don't know starter/bench automatically.
    if blowout >= 0.6:
        if prop_type in ("turnovers", "steals", "blocks"):
            # volatility props can spike late
            mult = 1.0 + 0.02
            proj *= mult
            b["Garbage Volatility"] = +0.02

    if league == "nfl":
        run_heavy = float(ctx.get("script_run_heavy", 0.25))
        pass_heavy = float(ctx.get("script_pass_heavy", 0.25))

        if prop_type in ("pass_yards",):
            mult = 1.0 - 0.06 * run_heavy + 0.04 * pass_heavy
            proj *= mult
            b["NFL Script PassYds"] = round(mult, 3)

        if prop_type in ("rush_yards",):
            mult = 1.0 + 0.05 * run_heavy - 0.02 * pass_heavy
            proj *= mult
            b["NFL Script RushYds"] = round(mult, 3)

        if prop_type in ("receptions", "rec_yards"):
            mult = 1.0 + 0.03 * pass_heavy - 0.02 * run_heavy
            proj *= mult
            b["NFL Script Rec"] = round(mult, 3)

    return proj, b

def compute_edge(proj: float, line: float, prop_type: str, extra_breakdown: dict) -> Tuple[float, str, dict]:
    """
    Returns (edge_score 0-100, side over/under, breakdown dict)
    """
    breakdown = dict(extra_breakdown)

    if line <= 0:
        return 0.0, "over", breakdown

    delta = proj - line
    dead = 0.25 if prop_type in ("steals", "blocks", "int", "rush_td", "pass_td", "rec_td") else 0.50
    breakdown["Model Δ"] = round(delta, 3)

    if abs(delta) < dead:
        return 0.0, "over", breakdown

    side = "over" if delta > 0 else "under"

    scale = max(1.5, line * 0.08)
    base = 50 + 45 * (2 * sigmoid(delta / scale) - 1)

    # Extra small confidence bump when delta is large
    base += clamp(abs(delta) / max(1.0, scale) * 2.0, 0, 6)

    score = clamp(base, 0, 100)
    breakdown["Scaled"] = round(delta / scale, 3)
    breakdown["EdgeScore"] = round(score, 2)
    return score, side, breakdown

# =============================================================================
# PIPELINE: BUILD PICKS (ALL PLAYERS IN ODDS FEED)
# =============================================================================

def generate_picks_for_league(league: str, top_n: int = 12) -> list[dict]:
    """
    1) Get events from Odds API
    2) For each event, pull player props
    3) For each player in props:
       - injury filter (ESPN)
       - map to ESPN athlete id (roster index)
       - pull stats (ESPN)
       - compute projection + edge for over/under
    """
    if league == "nba":
        sport_key = NBA_SPORT_KEY
        markets = NBA_MARKETS
        market_to_prop = NBA_MARKET_TO_PROP
    else:
        sport_key = NFL_SPORT_KEY
        markets = NFL_MARKETS
        market_to_prop = NFL_MARKET_TO_PROP

    # Build player index + injuries once per run (cached by day)
    player_index = build_player_index(league)
    injured_set, injured_details = build_injury_set(league)

    events = oddsapi_get_events(sport_key)
    games = build_games_from_events(events)

    picks = []

    for g in games:
        event_id = g.get("id")
        if not event_id:
            continue

        # Spread/total context (optional)
        spread_abs = None
        total_pts = None
        try:
            main_odds = oddsapi_get_event_odds(sport_key, event_id, MAIN_LINE_MARKETS)
            spread_abs, total_pts = parse_spread_total(main_odds, g["home_team"], g["away_team"])
        except Exception:
            pass

        ctx = build_context(spread_abs, total_pts, league)

        # Player props odds
        try:
            odds = oddsapi_get_event_odds(sport_key, event_id, markets)
        except Exception:
            continue

        prop_rows = parse_player_props(odds)

        for row in prop_rows:
            market = row["market"]
            raw_player = row["player"]
            line = row["line"]

            prop_type = market_to_prop.get(market)
            if not prop_type:
                continue

            nm = normalize_player_name(raw_player)

            # injury filter
            if nm in injured_set:
                continue

            # map to ESPN athlete id via roster index
            info = player_index.get(nm)
            if not info:
                # If name doesn't match roster spelling exactly, skip (or add fuzzy later)
                continue

            athlete_id = info["id"]
            stats = get_player_stats(league, athlete_id)

            base_proj = projection_from_stats(league, prop_type, stats)
            if base_proj is None:
                continue

            proj, add_breakdown = apply_script_adjustments(league, prop_type, float(base_proj), ctx)
            score, side, breakdown = compute_edge(proj, float(line), prop_type, add_breakdown)

            # keep only meaningful edges
            if score < 62:
                continue

            picks.append({
                "player": info["name"],
                "prop_type": prop_type,
                "line": float(line),
                "side": side,
                "proj": float(proj),
                "edge_score": float(score),
                "matchup": g["matchup"],
                "time": g["time"],
                "breakdown": breakdown,
            })

    picks.sort(key=lambda x: x["edge_score"], reverse=True)
    return picks[:top_n]

# =============================================================================
# HTML OUTPUT
# =============================================================================

def generate_factor_html(breakdown: dict) -> str:
    items = list(breakdown.items())
    # Show a few helpful breakdown fields
    show = []
    for k, v in items:
        if k in ("EdgeScore",):
            continue
        show.append((k, v))
    show = show[:6]

    html = '<div class="factor-breakdown">'
    for name, val in show:
        try:
            vv = float(val) if isinstance(val, (int, float, str)) else 0.0
        except Exception:
            vv = 0.0

        # normalize display 0-100
        norm = int(clamp(50 + vv * 10, 0, 100))
        if norm >= 75:
            grad = "linear-gradient(90deg, #00ff88, #00cc66)"
        elif norm >= 50:
            grad = "linear-gradient(90deg, #00d4ff, #0099ff)"
        else:
            grad = "linear-gradient(90deg, #ffaa00, #ff8800)"

        html += f"""
        <div class="factor-item">
          <div class="factor-name">{name}</div>
          <div class="factor-score-bar">
            <div class="factor-score-fill" style="width:{norm}%; background:{grad};">{norm}</div>
          </div>
        </div>
        """
    html += "</div>"
    return html

def generate_prediction_card(p: dict) -> str:
    edge = float(p["edge_score"])
    conf = "high" if edge >= 80 else ("medium" if edge >= 70 else "low")
    badge = f"{int(edge)}% EDGE"
    title = f"{p['player']} {p['prop_type'].replace('_',' ').title()} {p['side'].title()} {p['line']}"
    subtitle = f"{p['matchup']} | {p['time']} | Proj: {p['proj']:.2f}"

    return f"""
    <div class="prediction-card {conf}-confidence">
      <div class="prediction-header">
        <div>
          <div class="prediction-title">{title}</div>
          <div style="color: var(--color-text-secondary); font-size: 0.9em; margin-top: 5px;">{subtitle}</div>
        </div>
        <div class="confidence-badge {conf}">{badge}</div>
      </div>
      {generate_factor_html(p['breakdown'])}
      <div class="ai-reasoning">
        <strong>Model logic:</strong> ESPN season averages → script adjustment (blowout / NFL run-pass) → edge vs line.
        Shows Over/Under based on projection difference.
      </div>
    </div>
    """

def generate_html(nba_picks: list[dict], nfl_picks: list[dict]) -> str:
    now = dt.now().astimezone()
    today = now.strftime("%B %d, %Y")
    updated = now.strftime("%B %d, %Y at %I:%M %p %Z")

    nba_cards = "".join(generate_prediction_card(p) for p in nba_picks) if nba_picks else '<p style="color:#cbd5e1;">No high-edge NBA props found.</p>'
    nfl_cards = "".join(generate_prediction_card(p) for p in nfl_picks) if nfl_picks else '<p style="color:#cbd5e1;">No high-edge NFL props found.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Prop Scouting Dashboard</title>
<style>
:root {{
  --color-bg:#0a0e27; --color-surface:#1a1f3a; --color-border:#2d3748;
  --color-text:#f1f5f9; --color-text-secondary:#cbd5e1;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:linear-gradient(135deg,var(--color-bg) 0%, #0f1729 100%);
color:var(--color-text); padding:20px;}}
.header{{text-align:center;margin-bottom:18px;border-bottom:2px solid var(--color-border);padding-bottom:14px;}}
.header h1{{font-size:2.2em;margin-bottom:6px;background:linear-gradient(135deg,#00d4ff,#0099ff);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.header p{{color:var(--color-text-secondary)}}
.container{{max-width:1400px;margin:0 auto}}
.league-tabs{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:12px 0 18px;}}
.league-tab{{padding:10px 18px;border:2px solid var(--color-border);background:transparent;color:var(--color-text);
border-radius:10px;cursor:pointer;font-weight:800;}}
.league-tab.active{{background:linear-gradient(135deg,#00d4ff,#0099ff);border-color:#00d4ff;color:#000}}
.league-content{{display:none}}
.league-content.active{{display:block}}
.prediction-card{{background:var(--color-surface);border:2px solid var(--color-border);border-radius:12px;padding:16px;margin-bottom:14px;}}
.prediction-header{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;}}
.prediction-title{{font-size:1.1em;font-weight:900}}
.confidence-badge{{padding:8px 14px;border-radius:999px;font-weight:900;color:#fff;white-space:nowrap}}
.confidence-badge.high{{background:linear-gradient(135deg,#00ff88,#00cc66)}}
.confidence-badge.medium{{background:linear-gradient(135deg,#ffaa00,#ff8800)}}
.confidence-badge.low{{background:linear-gradient(135deg,#ff6b6b,#cc0000)}}
.factor-breakdown{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:14px 0;}}
.factor-item{{background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2);padding:10px;border-radius:10px}}
.factor-name{{font-size:0.8em;font-weight:800;color:#00d4ff;text-transform:uppercase;margin-bottom:6px}}
.factor-score-bar{{background:rgba(0,0,0,0.3);height:18px;border-radius:4px;overflow:hidden}}
.factor-score-fill{{height:100%;display:flex;align-items:center;justify-content:center;font-size:0.75em;font-weight:900;color:#000}}
.ai-reasoning{{background:rgba(0,212,255,0.05);border-left:3px solid #00d4ff;padding:10px;border-radius:10px;color:var(--color-text-secondary);line-height:1.45}}
</style>
</head>
<body>
  <div class="header">
    <h1>Automated Prop Scouting Dashboard</h1>
    <p>{today} • NBA picks: {len(nba_picks)} • NFL picks: {len(nfl_picks)}</p>
    <p style="margin-top:6px;font-size:0.95em;">Last updated: {updated}</p>

    <div class="league-tabs">
      <button class="league-tab active" data-league="nba">🏀 NBA</button>
      <button class="league-tab" data-league="nfl">🏈 NFL</button>
    </div>
  </div>

  <div class="container">
    <div id="nba" class="league-content active">
      <h2 style="margin: 10px 0 12px;">NBA Top Value Picks</h2>
      {nba_cards}
    </div>

    <div id="nfl" class="league-content">
      <h2 style="margin: 10px 0 12px;">NFL Top Value Picks</h2>
      {nfl_cards}
    </div>

    <div style="text-align:center;margin:26px 0;color:var(--color-text-secondary);font-size:0.9em;">
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
    ensure_cache_dir()
    print("🚀 Starting dashboard generation...")
    print(f"⏰ {dt.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    print("📌 Building ESPN indexes (players + injuries) ...")
    # caches are built on-demand inside generate_picks_for_league

    print("🏀 Generating NBA picks from ALL players in odds feed ...")
    nba_picks = generate_picks_for_league("nba", top_n=12)

    print("🏈 Generating NFL picks from ALL players in odds feed ...")
    nfl_picks = generate_picks_for_league("nfl", top_n=12)

    html = generate_html(nba_picks, nfl_picks)
    with open("AI_Prediction_Engine.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Wrote AI_Prediction_Engine.html")
    print(f"NBA picks: {len(nba_picks)} | NFL picks: {len(nfl_picks)}")

if __name__ == "__main__":
    main()
