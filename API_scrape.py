"""
update_matches.py
==================
Single script combining two jobs, designed to be run together (e.g. every Tuesday
on PythonAnywhere):

  Part A  - Fetch the match week (Fri-Mon) that is 5 weeks ahead and create those
            matches in the database (scores left blank).
  Part B  - Find last week's match week (Fri-Mon), pull final scores, and write
            them onto the existing Match rows.

Both parts hit the same API-Football endpoint (/fixtures) with a date range.

Setup notes
-----------
* Set your key in the environment:  export API_FOOTBALL_KEY="xxxx"
* If you call API-Football directly, the host below is correct. If you go via
  RapidAPI, switch HOST / header (see AUTH section).
* This is written as a Django management-style standalone script. To run it on
  PythonAnywhere as a scheduled task, either turn it into a management command
  or keep the django.setup() bootstrap at the top (adjust the settings module).
"""

import os
import sys
import time
import logging
import datetime

import requests

# ---------------------------------------------------------------------------
# Django bootstrap
# ---------------------------------------------------------------------------
# Point this at your project's settings module, then `Match` can be imported.
# On PythonAnywhere the project root is usually on sys.path already; if not,
# uncomment and adjust the insert line.
#
# sys.path.insert(0, "/home/YOURUSER/yourproject")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")

import django  # noqa: E402
django.setup()

from predictions.models import Match  # noqa: E402  <-- adjust app/model path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
#API_KEY = os.environ.get("API_FOOTBALL_KEY")
API_KEY = "d9fb527f0dbbae0c5c988276217ee9b9"

# Direct API-Football (api-sports.io):
BASE_URL = "https://v3.football.api-sports.io"
AUTH_HEADERS = {"x-apisports-key": API_KEY or ""}
# --- If using RapidAPI instead, comment the two lines above and use: ---
# BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"
# AUTH_HEADERS = {
#     "x-rapidapi-key": API_KEY or "",
#     "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
# }

# API-Football league IDs. VERIFY THESE against /leagues before first run -
# IDs are stable but you should confirm National League + Scottish tiers.
LEAGUE_IDS = {
    "Premier_League": 39,
    "Championship": 40,
    "League_1": 41,
    "League_2": 42,
    "National_League": 43,
    "Scottish_Premier_League": 179,
    "Scottish_Championship": 180,
    "Scottish_League_1": 183,
    "Scottish_League_2": 184,
}

# Statuses that mean the match is over and the score is final.
FINISHED = {"FT", "AET", "PEN"}
# Statuses that mean it won't be played as scheduled.
POSTPONED_STATES = {"PST", "CANC", "ABD", "SUSP", "AWD", "WO"}

WEEKS_AHEAD = 5
REQUEST_PAUSE = 1.0  # seconds between calls, polite + stays under rate limit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("update_matches")


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def upcoming_friday(today=None):
    """The next Friday on or after `today` (today if today is already Friday)."""
    today = today or datetime.date.today()
    # Monday=0 ... Friday=4 ... Sunday=6
    days_until_friday = (4 - today.weekday()) % 7
    return today + datetime.timedelta(days=days_until_friday)


def week_window(friday):
    """Given a Friday, return (friday, monday) covering Fri-Sat-Sun-Mon."""
    return friday, friday + datetime.timedelta(days=3)


def season_for(date):
    """
    API-Football keys a season by its starting year. A 2025-26 season is
    season=2025. Aug-Dec -> that year; Jan-Jul -> previous year.
    """
    return date.year if date.month >= 8 else date.year - 1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def get_fixtures(league_id, season, date_from, date_to, retries=3):
    """Return the raw `response` list of fixtures for a league + date range."""
    params = {
        "league": league_id,
        "season": season,
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "timezone": "Europe/London",
    }
    url = f"{BASE_URL}/fixtures"
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=AUTH_HEADERS, params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
            # API-Football reports problems in an "errors" object, not HTTP codes.
            if payload.get("errors"):
                log.error("API errors for league %s: %s", league_id, payload["errors"])
                return []
            return payload.get("response", [])
        except requests.RequestException as exc:
            log.warning(
                "Request failed (league %s, attempt %s/%s): %s",
                league_id, attempt, retries, exc,
            )
            time.sleep(2 * attempt)
    log.error("Giving up on league %s after %s attempts", league_id, retries)
    return []


# ---------------------------------------------------------------------------
# Part A - create fixtures 5 weeks ahead
# ---------------------------------------------------------------------------
def part_a_fetch_ahead(today=None, test_from=None, test_to=None):
    if test_from and test_to:
        date_from, date_to = test_from, test_to
    else:
        friday = upcoming_friday(today)
        target_friday = friday + datetime.timedelta(weeks=WEEKS_AHEAD)
        date_from, date_to = week_window(target_friday)
    season = season_for(date_from)

    log.info("PART A: fetching fixtures %s -> %s (season %s)",
             date_from, date_to, season)

    created = updated = skipped = 0
    for name, league_id in LEAGUE_IDS.items():
        fixtures = get_fixtures(league_id, season, date_from, date_to)
        log.info("  %s: %s fixtures returned", name, len(fixtures))
        for fx in fixtures:
            match_date = datetime.date.fromisoformat(fx["fixture"]["date"][:10])
            # Guard: only Fri/Sat/Sun/Mon (drops any midweek reschedules in range)
            if match_date.weekday() not in (4, 5, 6, 0):
                skipped += 1
                continue

            obj, was_created = Match.objects.update_or_create(
                match_id=fx["fixture"]["id"],
                defaults={
                    "home_team": fx["teams"]["home"]["name"],
                    "away_team": fx["teams"]["away"]["name"],
                    "match_date": match_date,
                    "league": name,
                },
            )
            created += was_created
            updated += (not was_created)
        time.sleep(REQUEST_PAUSE)

    log.info("PART A done: %s created, %s updated, %s skipped (non-window)",
             created, updated, skipped)


# ---------------------------------------------------------------------------
# Part B - backfill last week's scores
# ---------------------------------------------------------------------------
def part_b_update_scores(today=None, test_from=None, test_to=None):
    # Last week's Friday = the Friday before the upcoming one, minus a week.
    changed_matches = []
    if test_to and test_from:
        date_from, date_to = test_from, test_to
    else:
        this_friday = upcoming_friday(today)
        last_friday = this_friday - datetime.timedelta(weeks=1)
        date_from, date_to = week_window(last_friday)
    season = season_for(date_from)

    log.info("PART B: updating scores %s -> %s (season %s)",
             date_from, date_to, season)

    scored = postponed = missing = 0
    for name, league_id in LEAGUE_IDS.items():
        fixtures = get_fixtures(league_id, season, date_from, date_to)
        for fx in fixtures:
            match_id = fx["fixture"]["id"]
            status = fx["fixture"]["status"]["short"]

            try:
                match = Match.objects.get(match_id=match_id)
            except Match.DoesNotExist:
                # We never created it in Part A (e.g. midweek game) - skip.
                missing += 1
                continue

            if status in POSTPONED_STATES:
                match.postponed = True
                match.save(update_fields=["postponed"])
                postponed += 1
                continue

            if status not in FINISHED:
                # Not finished yet - leave it, next run will catch it.
                continue

            # Idempotent: only write if not already scored.
            if match.home_score is None or match.away_score is None:
                match.home_score = fx["goals"]["home"]
                match.away_score = fx["goals"]["away"]
                match.postponed = False
                match.save(update_fields=["home_score", "away_score", "postponed"])
                changed_matches.append(match.pk)
                scored += 1
        time.sleep(REQUEST_PAUSE)

    if changed_matches:
        from predictions.models import recompute_points
        n = recompute_points(changed_matches)
        log.info("Recomputed points for %s predictions", n)

    log.info("PART B done: %s scored, %s postponed, %s not-in-db",
             scored, postponed, missing)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if not API_KEY:
        log.error("API_FOOTBALL_KEY environment variable not set. Aborting.")
        sys.exit(1)

    # Part B first (close out last week), then Part A (open the new week).
    # Order doesn't strictly matter since they touch different weeks.
    part_a_fetch_ahead()
    part_b_update_scores()
    


if __name__ == "__main__":
    main()