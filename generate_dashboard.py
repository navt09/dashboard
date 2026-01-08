#!/usr/bin/env python3
"""
Automated NBA+NFL Prop Scouting Dashboard (All players, all props, Over+Under)

DATA:
- Lines/markets: The Odds API (free tier dependent)
- Teams/rosters: ESPN (free)
- Injuries: ESPN (free)
- Stats: ESPN athlete profile + last-10 gamelog fallback (free)

OUTPUT:
- AI_Prediction_Engine.html
"""

import os
import re
import json
import math
import time
import difflib
import requests
from datetime import datetime as dt, timezone
from typing import Dict, Any, Optional, Tuple, List

# =============================================================================
# REQUIRED SECRET
# =============================================================================
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
if not ODDS_API_KEY:
    raise RuntimeError("Missing ODDS_API_KEY. Add it to GitHub Secrets and pass it as env to the workflow step.")

# =============================================================================
# CONFIG
# =============================================================================
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

NBA_SPORT_KEY = "basketball_nba"
NFL_SPORT_KEY = "americanfootball_nfl"

# Try lots of markets. If your plan doesn’t include some, they just return empty.
NBA_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
    "player_turnovers",
    "player_points_rebounds_assists",  # PRA
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
    # some books/plans:
    "player_double_double",
    "player_triple_double",
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

MAIN_LINE_MARKETS = ["spreads", "totals"]  # for blowout/script

NBA_MARKET_TO_PROP = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "threes",
    "player_steals": "steals",
    "player_blocks": "blocks",
    "player_turnovers": "turnovers",
    "player_points_rebounds_assists": "pra",
    "player_points_rebounds": "pr",
    "player_points_assists": "pa",
    "player_rebounds_assists": "ra",
    "player_double_double": "double_double",
    "player_triple_double": "triple_double",
}

NFL_MARKET_TO_PROP = {
    "player_pass_yds": "pass_yards",
    "player_pass_tds": "pass_tds",
    "player_pass_interceptions": "interceptions",
    "player_rush_yds": "rush_yards",
    "player_rush_tds": "rush_tds",
    "player_receptions": "receptions",
    "player_reception_yds": "rec_yards",
    "player_reception_tds": "rec_tds",
}

# ESPN endpoints
ESPN_NBA_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
ESPN_NFL_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

# Cache files
CACHE_DIR = ".cache"
PLAYER_INDEX_CACHE = os.path.join(CACHE_DIR, "espn_player_index.json")
INJURY_CACHE = os.path.join(CACHE_DIR, "espn_injuries.json")
PLAYER_STATS_CACHE = os.path.join(CACHE_DIR, "espn_player_stats.json")

REQUEST_SLEEP = 0.12
FUZZY_CUTOFF = 0.86  # if mapping fails too much, drop to 0.82

# =============================================================================
# UTIL
# =============================================================================

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def _get_json(url: str, params: dict | None = None, timeout: int = 20) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, timeout=timeout, headers=headers)
    r.raise_for_status()
    time.sleep(REQUEST_SLEEP)
    return r.json()

def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, obj: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

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

# =============================================================================
# ODDS API
# =============================================================================

def oddsapi_get_events(sport_key: str) -> list[dict]:
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY}
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def oddsapi_get_event_odds(sport_key: str, event_id: str, markets: list[str]) -> dict:
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us,us2",  # broader coverage
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "bookmakers": "draftkings,fanduel,betmgm,pointsbetus,caesars",  # helps avoid empty results
    }
    r = requests.get(url, params=params, timeout=30)
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
    Returns list of dicts:
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

def parse_spread_total(odds_json: dict, home_team: str, away_team: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Returns: (spread_abs, total_points, favorite_team_name)
    spread_abs is absolute spread, favorite inferred if spread found.
    """
    spread_abs = None
    total_pts = None
    favorite = None

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

                    # usually favorite has negative spread
                    if home_spread is not None:
                        spread_abs = abs(home_spread)
                        favorite = home_team if home_spread < 0 else away_team
                    elif away_spread is not None:
                        spread_abs = abs(away_spread)
                        favorite = away_team if away_spread < 0 else home_team

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

    return spread_abs, total_pts, favorite

# =============================================================================
# ESPN: TEAMS/ROSTERS/INDEX (name->id) with FUZZY MATCHING
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
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams" if league == "nba" \
        else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
    url = f"{base}/{team_id}/roster"
    data = _get_json(url)

    athletes = []
    for grp in data.get("athletes", []) or []:
        for a in grp.get("items", []) or []:
            athletes.append(a)
    if not athletes and data.get("athletes"):
        for grp in data["athletes"]:
            for a in grp.get("athletes", []) or []:
                athletes.append(a)

    return athletes

def build_player_index(league: str, force_refresh: bool = False) -> dict:
    """
    Creates dict:
      normalized_name -> {"id": athlete_id, "name": raw_display_name, "team_abbr": abbr}
    Also stores list of keys for fuzzy matching.
    """
    ensure_cache_dir()
    cache = load_json(PLAYER_INDEX_CACHE)
    today = dt.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{league}:{today}"

    if not force_refresh and key in cache:
        return cache[key]

    idx: Dict[str, dict] = {}
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
            if nm and nm not in idx:
                idx[nm] = {"id": athlete_id, "name": raw_name, "team_abbr": team_abbr}

    cache[key] = idx
    save_json(PLAYER_INDEX_CACHE, cache)
    return idx

def resolve_player_to_espn(normalized_name: str, player_index: dict, cutoff: float = FUZZY_CUTOFF) -> Optional[dict]:
    """
    Exact match first, then fuzzy match.
    """
    if normalized_name in player_index:
        return player_index[normalized_name]

    keys = list(player_index.keys())
    # difflib works well for small-to-medium lists
    hits = difflib.get_close_matches(normalized_name, keys, n=1, cutoff=cutoff)
    if hits:
        return player_index.get(hits[0])

    # extra trick: remove middle initials if any
    s = re.sub(r"\b[a-z]\b", "", normalized_name).strip()
    s = re.sub(r"\s+", " ", s)
    if s in player_index:
        return player_index[s]

    hits2 = difflib.get_close_matches(s, keys, n=1, cutoff=cutoff - 0.03)
    if hits2:
        return player_index.get(hits2[0])

    return None

# =============================================================================
# ESPN: INJURIES
# =============================================================================

def build_injury_set(league: str, force_refresh: bool = False) -> Tuple[set[str], dict]:
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

            # if not clearly active, treat as injured (conservative)
            if any(x in status_upper for x in ["OUT", "INACTIVE", "DOUBTFUL", "IR", "DNP", "SUSP", "PUP"]):
                nm = normalize_player_name(raw_name)
                if nm:
                    injured.add(nm)
                    details[nm] = {"status": str(status), "team_abbr": team_abbr, "raw": raw_name}

    cache[key] = {"injured": sorted(list(injured)), "details": details}
    save_json(INJURY_CACHE, cache)
    return injured, details

# =============================================================================
# ESPN: STATS (profile + last10 gamelog fallback)
# =============================================================================

def fetch_athlete_profile(league: str, athlete_id: str) -> dict:
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes" if league == "nba" \
        else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes"
    url = f"{base}/{athlete_id}"
    return _get_json(url)

def fetch_athlete_gamelog(league: str, athlete_id: str) -> dict:
    # ESPN gamelog endpoint works like:
    # /athletes/{id}/gamelog
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes" if league == "nba" \
        else "https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes"
    url = f"{base}/{athlete_id}/gamelog"
    return _get_json(url)

def _scan_profile_stats(profile: dict) -> dict:
    """
    Very defensive scan through profile["statistics"].
    Returns dict of commonly needed fields when found.
    """
    stats = profile.get("statistics") or []
    out: Dict[str, float] = {}

    def visit_stat(name: str, abbr: str, value: Any):
        if value is None:
            return
        try:
            v = float(value)
        except Exception:
            return
        key = (abbr or name or "").lower().strip()
        key = key.replace(" ", "")
        # Keep some common abbreviations
        if key in ("ppg", "pts", "pointspergame"):
            out["ppg"] = v
        elif key in ("rpg", "reb", "reboundspergame"):
            out["rpg"] = v
        elif key in ("apg", "ast", "assistspergame"):
            out["apg"] = v
        elif key in ("spg", "stl", "stealspergame"):
            out["spg"] = v
        elif key in ("bpg", "blk", "blockspergame"):
            out["bpg"] = v
        elif key in ("tpg", "to", "turnoverspergame"):
            out["tpg"] = v
        elif key in ("3pm", "3ptm", "threepointersmadepergame"):
            out["3pm"] = v

        elif key in ("passyds", "passingyards", "py"):
            out["pass_yds"] = v
        elif key in ("passtd", "passingtd", "ptd"):
            out["pass_tds"] = v
        elif key in ("int", "interceptions"):
            out["ints"] = v
        elif key in ("rushyds", "rushingyards", "ry"):
            out["rush_yds"] = v
        elif key in ("rushtd", "rushingtd", "rtd"):
            out["rush_tds"] = v
        elif key in ("rec", "receptions"):
            out["rec"] = v
        elif key in ("recyards", "receivingyards", "recy"):
            out["rec_yds"] = v
        elif key in ("rectd", "receivingtd"):
            out["rec_tds"] = v

    for block in stats:
        for cat in block.get("categories", []) or []:
            for st in cat.get("stats", []) or []:
                visit_stat(st.get("displayName") or st.get("name") or "", st.get("abbreviation") or "", st.get("value"))

    return out

def _compute_last10_from_gamelog(league: str, gamelog: dict) -> dict:
    """
    Attempts to compute last 10 averages from ESPN gamelog.
    Works best-effort across ESPN variations.
    """
    out: Dict[str, float] = {}

    # Many ESPN gamelog payloads contain events[].stats (array)
    events = gamelog.get("events") or []
    if not events:
        # Some are nested deeper
        events = gamelog.get("gamelog", {}).get("events") or []

    # Parse last 10 entries
    rows = []
    for ev in events[:10]:
        stats = ev.get("stats")
        if isinstance(stats, list) and stats:
            rows.append(stats)

    if not rows:
        return out

    # NBA typical stat order often includes: MIN, FG, 3PT, FT, OREB, DREB, REB, AST, STL, BLK, TO, PF, +/-, PTS
    # NFL varies by position; we’ll compute only what we can detect safely:
    def safe_float(x):
        try:
            return float(x)
        except Exception:
            return None

    if league == "nba":
        pts, reb, ast, stl, blk, to, threes = [], [], [], [], [], [], []
        for stats in rows:
            # best-effort: look for dict form
            if stats and isinstance(stats[0], dict):
                # not common here, but handle
                pass
            # common: list of strings
            if isinstance(stats, list):
                # try from end: PTS is usually last
                p = safe_float(stats[-1]) if len(stats) >= 1 else None
                if p is not None: pts.append(p)

                # REB often at index -6 or around; AST -5; STL -4; BLK -3; TO -2; but varies.
                # We'll do a heuristic: scan numeric entries and pick some common positions if length >= 13
                if len(stats) >= 13:
                    r = safe_float(stats[6])  # REB often index 6 (0-based) if order includes OREB/DREB/REB
                    a = safe_float(stats[7])
                    s = safe_float(stats[8])
                    b = safe_float(stats[9])
                    t = safe_float(stats[10])
                    if r is not None: reb.append(r)
                    if a is not None: ast.append(a)
                    if s is not None: stl.append(s)
                    if b is not None: blk.append(b)
                    if t is not None: to.append(t)

                # threes: from "3PT" string like "3-8"
                if len(stats) >= 3:
                    three_str = stats[2]
                    if isinstance(three_str, str) and "-" in three_str:
                        made = safe_float(three_str.split("-")[0])
                        if made is not None:
                            threes.append(made)

        def avg(vs): return sum(vs) / len(vs) if vs else None
        if avg(pts) is not None: out["ppg"] = avg(pts)
        if avg(reb) is not None: out["rpg"] = avg(reb)
        if avg(ast) is not None: out["apg"] = avg(ast)
        if avg(stl) is not None: out["spg"] = avg(stl)
        if avg(blk) is not None: out["bpg"] = avg(blk)
        if avg(to) is not None: out["tpg"] = avg(to)
        if avg(threes) is not None: out["3pm"] = avg(threes)

    else:
        # NFL: we can’t reliably parse all positions, but for props returned by odds,
        # the athlete is usually QB/RB/WR/TE. We'll approximate from common QB rows where stats include:
        # CMP/ATT, YDS, TD, INT, CAR, YDS, TD (varies).
        pass_yds, pass_tds, ints, rush_yds, rush_tds, rec, rec_yds, rec_tds = [], [], [], [], [], [], [], []
        for stats in rows:
            if not isinstance(stats, list):
                continue
            # Try to find numbers that look like yards/TDs/INT in typical QB or skill player logs.
            # If stats has "YDS" columns, they tend to be large-ish.
            nums = [safe_float(x) for x in stats if safe_float(x) is not None]
            if not nums:
                continue

            # Heuristics:
            # - passing yards is often the largest number in row (excluding snap counts)
            # - rushing/receiving yards are medium
            # - TDs are small ints
            maxv = max(nums)
            if maxv >= 120:
                pass_yds.append(maxv)

            # Try to find small integers that could be TDs/INTs (0-5)
            small = [n for n in nums if 0 <= n <= 6 and float(n).is_integer()]
            if small:
                # not perfect, but helps
                # push most common small as TD proxy
                pass_tds.append(small[0])

        def avg(vs): return sum(vs) / len(vs) if vs else None
        if avg(pass_yds) is not None: out["pass_yds"] = avg(pass_yds)
        if avg(pass_tds) is not None: out["pass_tds"] = avg(pass_tds)
        # (NFL gamelog parsing is inherently weaker; profile stats often cover it)

    return out

def get_player_stats(league: str, athlete_id: str, force_refresh: bool = False) -> dict:
    """
    Cached by date+athlete_id. Returns a stat bundle with keys used by projections.
    """
    ensure_cache_dir()
    cache = load_json(PLAYER_STATS_CACHE)
    today = dt.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{league}:{today}:{athlete_id}"

    if not force_refresh and key in cache:
        return cache[key]

    bundle: Dict[str, float] = {}
    try:
        profile = fetch_athlete_profile(league, athlete_id)
        bundle.update(_scan_profile_stats(profile))
    except Exception:
        pass

    # If missing key stats, try gamelog last-10
    need_keys = ["ppg", "rpg", "apg"] if league == "nba" else ["pass_yds", "rush_yds", "rec_yds", "rec"]
    if not any(k in bundle for k in need_keys):
        try:
            gl = fetch_athlete_gamelog(league, athlete_id)
            bundle.update(_compute_last10_from_gamelog(league, gl))
        except Exception:
            pass

    cache[key] = bundle
    save_json(PLAYER_STATS_CACHE, cache)
    return bundle

# =============================================================================
# GAME SCRIPT CONTEXT
# =============================================================================

def build_context(spread_abs: Optional[float], total_pts: Optional[float], favorite: Optional[str], league: str, player_team: Optional[str]) -> dict:
    ctx = {"spread_abs": spread_abs, "total": total_pts, "favorite": favorite}

    # Blowout risk
    if spread_abs is None:
        ctx["blowout_risk"] = 0.15
    else:
        if spread_abs >= 14:
            ctx["blowout_risk"] = 0.90
        elif spread_abs >= 10:
            ctx["blowout_risk"] = 0.65
        elif spread_abs >= 7:
            ctx["blowout_risk"] = 0.40
        else:
            ctx["blowout_risk"] = 0.18

    # Underdog vs favorite usage shift (simple heuristic)
    # Underdogs often concentrate usage in stars; favorites distribute more.
    if favorite and player_team:
        if player_team != favorite:
            ctx["underdog_usage"] = 0.65 if (spread_abs or 0) >= 6 else 0.35
            ctx["favorite_usage"] = 0.0
        else:
            ctx["favorite_usage"] = 0.40 if (spread_abs or 0) >= 6 else 0.20
            ctx["underdog_usage"] = 0.0
    else:
        ctx["underdog_usage"] = 0.0
        ctx["favorite_usage"] = 0.0

    # NFL run vs pass script
    if league == "nfl":
        if total_pts is not None and spread_abs is not None:
            if total_pts <= 41 and spread_abs >= 7:
                ctx["script_run_heavy"] = 0.75
                ctx["script_pass_heavy"] = 0.20
            elif total_pts >= 50:
                ctx["script_run_heavy"] = 0.25
                ctx["script_pass_heavy"] = 0.70
            else:
                ctx["script_run_heavy"] = 0.35
                ctx["script_pass_heavy"] = 0.35
        else:
            ctx["script_run_heavy"] = 0.35
            ctx["script_pass_heavy"] = 0.35

    return ctx

# =============================================================================
# PROJECTIONS
# =============================================================================

def projection_from_stats(league: str, prop_type: str, stats: dict) -> Optional[float]:
    if league == "nba":
        ppg = stats.get("ppg")
        rpg = stats.get("rpg")
        apg = stats.get("apg")
        spg = stats.get("spg")
        bpg = stats.get("bpg")
        tpg = stats.get("tpg")
        threes = stats.get("3pm")

        if prop_type == "points": return ppg
        if prop_type == "rebounds": return rpg
        if prop_type == "assists": return apg
        if prop_type == "steals": return spg
        if prop_type == "blocks": return bpg
        if prop_type == "turnovers": return tpg
        if prop_type == "threes": return threes

        if prop_type == "pra":
            if ppg is None and rpg is None and apg is None: return None
            return (ppg or 0) + (rpg or 0) + (apg or 0)
        if prop_type == "pr":
            if ppg is None and rpg is None: return None
            return (ppg or 0) + (rpg or 0)
        if prop_type == "pa":
            if ppg is None and apg is None: return None
            return (ppg or 0) + (apg or 0)
        if prop_type == "ra":
            if rpg is None and apg is None: return None
            return (rpg or 0) + (apg or 0)

        # DD/TD: no clean ESPN average, skip unless you want a separate model
        if prop_type in ("double_double", "triple_double"):
            return None

    else:
        pass_yds = stats.get("pass_yds") or stats.get("pass_yds")
        pass_tds = stats.get("pass_tds")
        ints = stats.get("ints")
        rush_yds = stats.get("rush_yds")
        rush_tds = stats.get("rush_tds")
        rec = stats.get("rec")
        rec_yds = stats.get("rec_yds")
        rec_tds = stats.get("rec_tds")

        if prop_type == "pass_yards": return pass_yds
        if prop_type == "pass_tds": return pass_tds
        if prop_type == "interceptions": return ints
        if prop_type == "rush_yards": return rush_yds
        if prop_type == "rush_tds": return rush_tds
        if prop_type == "receptions": return rec
        if prop_type == "rec_yards": return rec_yds
        if prop_type == "rec_tds": return rec_tds

    return None

# =============================================================================
# ADJUSTMENTS + EDGE
# =============================================================================

def apply_context_adjustments(league: str, prop_type: str, proj: float, ctx: dict) -> Tuple[float, dict]:
    b = {}
    blowout = float(ctx.get("blowout_risk", 0.2))
    underdog_usage = float(ctx.get("underdog_usage", 0.0))
    favorite_usage = float(ctx.get("favorite_usage", 0.0))

    # Blowout: volume stats slightly down
    if prop_type in ("points", "rebounds", "assists", "pra", "pr", "pa", "ra", "pass_yards", "rush_yards", "receptions", "rec_yards"):
        mult = 1.0 - 0.06 * blowout
        proj *= mult
        b["Blowout mult"] = round(mult, 3)

    # Garbage time: volatile defensive stats slightly up when blowout high
    if blowout >= 0.65 and prop_type in ("steals", "blocks", "turnovers", "interceptions"):
        mult = 1.0 + 0.04
        proj *= mult
        b["Garbage vol"] = +0.04

    # Underdog usage bump: stars often handle more
    if underdog_usage > 0 and prop_type in ("points", "assists", "pra", "pa"):
        mult = 1.0 + 0.03 * underdog_usage
        proj *= mult
        b["Underdog usage"] = round(mult, 3)

    # Favorite usage spread: slightly lower concentrated usage
    if favorite_usage > 0 and prop_type in ("points", "assists", "pra", "pa"):
        mult = 1.0 - 0.02 * favorite_usage
        proj *= mult
        b["Favorite spread"] = round(mult, 3)

    # NFL script
    if league == "nfl":
        run_heavy = float(ctx.get("script_run_heavy", 0.35))
        pass_heavy = float(ctx.get("script_pass_heavy", 0.35))

        if prop_type == "pass_yards":
            mult = 1.0 - 0.08 * run_heavy + 0.05 * pass_heavy
            proj *= mult
            b["Script pass"] = round(mult, 3)

        if prop_type == "rush_yards":
            mult = 1.0 + 0.07 * run_heavy - 0.03 * pass_heavy
            proj *= mult
            b["Script rush"] = round(mult, 3)

        if prop_type in ("receptions", "rec_yards"):
            mult = 1.0 + 0.04 * pass_heavy - 0.02 * run_heavy
            proj *= mult
            b["Script rec"] = round(mult, 3)

    return proj, b

def compute_edge_score(proj: float, line: float, prop_type: str) -> Tuple[float, str]:
    """
    Returns edge_score 0..100, and preferred side ("over" or "under").
    """
    if line <= 0:
        return 0.0, "over"

    delta = proj - line
    side = "over" if delta > 0 else "under"

    # Prop-dependent deadzone
    dead = 0.25 if prop_type in ("steals", "blocks", "interceptions", "pass_tds", "rush_tds", "rec_tds") else 0.50
    if abs(delta) < dead:
        return 0.0, side

    # Scale by line so big lines aren’t overly confident
    scale = max(1.5, line * 0.09)
    base = 50 + 45 * (2 * sigmoid(delta / scale) - 1)
    base += clamp(abs(delta) / max(1.0, scale) * 2.0, 0, 8)

    return clamp(base, 0, 100), side

# =============================================================================
# MAIN PICK GENERATION
# =============================================================================

def generate_picks_for_league(league: str, top_n: int = 12) -> Tuple[List[dict], dict]:
    """
    Builds picks across ALL players included in the odds feed for today's events.
    Auto-relaxes threshold if it finds none.
    """
    if league == "nba":
        sport_key = NBA_SPORT_KEY
        markets = NBA_MARKETS
        map_market = NBA_MARKET_TO_PROP
    else:
        sport_key = NFL_SPORT_KEY
        markets = NFL_MARKETS
        map_market = NFL_MARKET_TO_PROP

    player_index = build_player_index(league)
    injured_set, _inj_details = build_injury_set(league)

    events = oddsapi_get_events(sport_key)
    games = build_games_from_events(events)

    dbg = {
        "games": len(games),
        "events_with_props_odds": 0,
        "bookmakers_empty": 0,
        "prop_rows_total": 0,
        "skipped_injured": 0,
        "skipped_no_espn_match": 0,
        "skipped_no_stats": 0,
        "skipped_low_edge": 0,
        "kept": 0,
    }

    candidates: List[dict] = []

    for g in games:
        eid = g.get("id")
        if not eid:
            continue

        # spread/total context
        spread_abs, total_pts, favorite = None, None, None
        try:
            main_odds = oddsapi_get_event_odds(sport_key, eid, MAIN_LINE_MARKETS)
            spread_abs, total_pts, favorite = parse_spread_total(main_odds, g["home_team"], g["away_team"])
        except Exception:
            pass

        try:
            odds = oddsapi_get_event_odds(sport_key, eid, markets)
        except Exception:
            continue

        dbg["events_with_props_odds"] += 1
        if not (odds.get("bookmakers") or []):
            dbg["bookmakers_empty"] += 1

        prop_rows = parse_player_props(odds)
        dbg["prop_rows_total"] += len(prop_rows)

        for row in prop_rows:
            market = row["market"]
            prop_type = map_market.get(market)
            if not prop_type:
                continue

            raw_player = row["player"]
            line = float(row["line"])
            nm = normalize_player_name(raw_player)

            # injury filter
            if nm in injured_set:
                dbg["skipped_injured"] += 1
                continue

            # ESPN mapping (fuzzy)
            info = resolve_player_to_espn(nm, player_index)
            if not info:
                dbg["skipped_no_espn_match"] += 1
                continue

            athlete_id = info["id"]
            team_abbr = info.get("team_abbr")

            ctx = build_context(spread_abs, total_pts, favorite, league, g["home_team"] if team_abbr else None)

            stats = get_player_stats(league, athlete_id)
            base_proj = projection_from_stats(league, prop_type, stats)
            if base_proj is None:
                dbg["skipped_no_stats"] += 1
                continue

            adj_proj, breakdown = apply_context_adjustments(league, prop_type, float(base_proj), ctx)

            # Score both sides
            over_score, _ = compute_edge_score(adj_proj, line, prop_type)
            under_score, _ = compute_edge_score(line - (adj_proj - line), line, prop_type)  # symmetric under edge

            # choose best side
            if over_score >= under_score:
                score = over_score
                side = "over"
            else:
                score = under_score
                side = "under"

            candidates.append({
                "player": info["name"],
                "prop_type": prop_type,
                "side": side,
                "line": line,
                "proj": adj_proj,
                "edge_score": score,
                "matchup": g["matchup"],
                "time": g["time"],
                "breakdown": breakdown,
            })

    # Auto-relax threshold so you don't get blank dashboards
    thresholds = [70, 65, 62, 58, 54, 50]
    picks: List[dict] = []
    used_threshold = thresholds[-1]

    candidates.sort(key=lambda x: x["edge_score"], reverse=True)

    for t in thresholds:
        picks = [c for c in candidates if c["edge_score"] >= t]
        used_threshold = t
        if len(picks) >= max(6, top_n // 2):
            break

    picks = picks[:top_n]
    dbg["kept"] = len(picks)
    dbg["used_threshold"] = used_threshold
    dbg["candidate_count"] = len(candidates)

    # Count "low edge" skips relative to final threshold
    dbg["skipped_low_edge"] = max(0, len(candidates) - len([c for c in candidates if c["edge_score"] >= used_threshold]))

    return picks, dbg

# =============================================================================
# HTML
# =============================================================================

def generate_factor_html(breakdown: dict) -> str:
    # Show a few helpful adjustments
    items = list(breakdown.items())[:6]
    html = '<div class="factor-breakdown">'
    for name, val in items:
        try:
            vv = float(val)
        except Exception:
            vv = 0.0
        norm = int(clamp(50 + vv * 120, 0, 100))
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
        </div>"""
    html += "</div>"
    return html

def card(p: dict) -> str:
    e = float(p["edge_score"])
    conf = "high" if e >= 80 else ("medium" if e >= 70 else "low")
    badge = f"{int(e)} EDGE"
    title = f"{p['player']} — {p['prop_type'].replace('_',' ').upper()} {p['side'].upper()} {p['line']}"
    subtitle = f"{p['matchup']} | {p['time']} | proj {p['proj']:.2f}"
    return f"""
    <div class="prediction-card {conf}-confidence">
      <div class="prediction-header">
        <div>
          <div class="prediction-title">{title}</div>
          <div class="prediction-sub">{subtitle}</div>
        </div>
        <div class="confidence-badge {conf}">{badge}</div>
      </div>
      {generate_factor_html(p["breakdown"])}
    </div>
    """

def generate_html(nba_picks: list[dict], nfl_picks: list[dict], nba_dbg: dict, nfl_dbg: dict) -> str:
    now = dt.now().astimezone()
    updated = now.strftime("%B %d, %Y at %I:%M %p %Z")

    nba_cards = "".join(card(p) for p in nba_picks) if nba_picks else "<p>No picks returned.</p>"
    nfl_cards = "".join(card(p) for p in nfl_picks) if nfl_picks else "<p>No picks returned.</p>"

    dbg_block = f"""
    <details style="margin-top:16px;color:#cbd5e1;">
      <summary style="cursor:pointer;font-weight:900;">Debug summary (why picks may be low)</summary>
      <pre style="white-space:pre-wrap;background:#0b1226;border:1px solid #2d3748;border-radius:10px;padding:12px;margin-top:10px;">
NBA: {json.dumps(nba_dbg, indent=2)}
NFL: {json.dumps(nfl_dbg, indent=2)}
      </pre>
    </details>
    """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Prop Dashboard</title>
<style>
:root {{
  --bg:#0a0e27; --surface:#1a1f3a; --border:#2d3748; --text:#f1f5f9; --muted:#cbd5e1;
}}
*{{box-sizing:border-box}}
body{{margin:0;padding:20px;font-family:system-ui,-apple-system,Segoe UI,Roboto;background:linear-gradient(135deg,var(--bg),#0f1729);color:var(--text)}}
.header{{text-align:center;border-bottom:2px solid var(--border);padding-bottom:12px;margin-bottom:18px}}
h1{{margin:0;font-size:2rem;background:linear-gradient(135deg,#00d4ff,#0099ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
small{{color:var(--muted)}}
.tabs{{display:flex;gap:10px;justify-content:center;margin:16px 0}}
.tab{{padding:10px 16px;border:2px solid var(--border);background:transparent;color:var(--text);border-radius:12px;font-weight:900;cursor:pointer}}
.tab.active{{background:linear-gradient(135deg,#00d4ff,#0099ff);border-color:#00d4ff;color:#000}}
.section{{display:none;max-width:1400px;margin:0 auto}}
.section.active{{display:block}}
.prediction-card{{background:var(--surface);border:2px solid var(--border);border-radius:14px;padding:14px;margin:12px 0}}
.prediction-header{{display:flex;justify-content:space-between;gap:12px}}
.prediction-title{{font-weight:1000;font-size:1.05rem}}
.prediction-sub{{color:var(--muted);font-size:0.9rem;margin-top:6px}}
.confidence-badge{{padding:8px 12px;border-radius:999px;font-weight:1000;color:#fff;white-space:nowrap}}
.confidence-badge.high{{background:linear-gradient(135deg,#00ff88,#00cc66)}}
.confidence-badge.medium{{background:linear-gradient(135deg,#ffaa00,#ff8800)}}
.confidence-badge.low{{background:linear-gradient(135deg,#ff6b6b,#cc0000)}}
.factor-breakdown{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-top:12px}}
.factor-item{{background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2);padding:10px;border-radius:10px}}
.factor-name{{font-size:0.78rem;font-weight:1000;color:#00d4ff;text-transform:uppercase}}
.factor-score-bar{{height:18px;border-radius:6px;background:rgba(0,0,0,0.3);overflow:hidden;margin-top:6px}}
.factor-score-fill{{height:100%;display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:1000;color:#000}}
</style>
</head>
<body>
  <div class="header">
    <h1>Automated Prop Scouting Dashboard</h1>
    <small>Last updated: {updated}</small>
    <div class="tabs">
      <button class="tab active" data-tab="nba">🏀 NBA</button>
      <button class="tab" data-tab="nfl">🏈 NFL</button>
    </div>
  </div>

  <div id="nba" class="section active">
    <h2>NBA Best Value (Over/Under)</h2>
    {nba_cards}
  </div>

  <div id="nfl" class="section">
    <h2>NFL Best Value (Over/Under)</h2>
    {nfl_cards}
  </div>

  <div style="max-width:1400px;margin:0 auto;">
    {dbg_block}
  </div>

<script>
document.querySelectorAll(".tab").forEach(btn => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
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

    nba_picks, nba_dbg = generate_picks_for_league("nba", top_n=12)
    nfl_picks, nfl_dbg = generate_picks_for_league("nfl", top_n=12)

    print("DEBUG NBA:", json.dumps(nba_dbg, indent=2))
    print("DEBUG NFL:", json.dumps(nfl_dbg, indent=2))

    html = generate_html(nba_picks, nfl_picks, nba_dbg, nfl_dbg)
    with open("AI_Prediction_Engine.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Wrote AI_Prediction_Engine.html")
    print(f"NBA picks: {len(nba_picks)} | NFL picks: {len(nfl_picks)}")

if __name__ == "__main__":
    main()
