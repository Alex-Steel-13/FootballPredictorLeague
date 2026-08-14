"""
update_matches.py
==================
Single script combining two jobs, designed to be run together.

  Part A  - Fetch all match weeks (Fri-Mon) from this upcoming Friday up to 
            4 weeks ahead and create those matches in the database (scores left blank).
            Because it uses update_or_create, it safely handles overlaps on subsequent runs.
  Part B  - Find last week's match week (Fri-Mon), pull final scores, and write
            them onto the existing Match rows.

Both parts hit TheSportsDB API endpoint (/eventsseason.php) to retrieve 
all events for the season, and filter locally by date.
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
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")

import django  # noqa: E402
django.setup()

from predictions.models import Match  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Replace with your TheSportsDB API key or load from env.
API_KEY = os.environ.get("THESPORTSDB_API_KEY", "123")

# TheSportsDB Base URL (v1)
BASE_URL = "https://www.thesportsdb.com/api/v1/json"

# TheSportsDB league IDs
LEAGUE_IDS = {
    "Premier_League": 4328,
    "Championship": 4329,
    "League_1": 4396,
    "League_2": 4397,
    "National_League": 4590, 
    "Scottish_Premier_League": 4330,
    "Scottish_Championship": 4395, 
    "Scottish_League_1": 4669, 
    "Scottish_League_2": 4670, 
}

# Number of weeks ahead to continuously fetch
WEEKS_AHEAD = 4
REQUEST_PAUSE = 1.0  # polite pause between calls to respect rate limits

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
    """The next Friday on or after `today`."""
    today = today or datetime.date.today()
    days_until_friday = (4 - today.weekday()) % 7
    return today + datetime.timedelta(days=days_until_friday)


def week_window(friday):
    """Given a Friday, return (friday, monday) covering Fri-Sat-Sun-Mon."""
    return friday, friday + datetime.timedelta(days=3)


def season_for(date):
    """
    TheSportsDB keys a season by the start and end years (e.g., 2026-2027).
    European football seasons generally kick off in July, so we roll over then.
    """
    start_year = date.year if date.month >= 7 else date.year - 1
    return f"{start_year}-{start_year + 1}"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def get_fixtures(league_id, season, retries=3):
    """Return the raw list of fixtures for a league and season from TheSportsDB."""
    params = {
        "id": league_id,
        "s": season,
    }
    url = f"{BASE_URL}/{API_KEY}/eventsseason.php"
    
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
            
            if payload and "events" in payload and payload["events"]:
                return payload["events"]
            return []
        except requests.RequestException as exc:
            log.warning(
                "Request failed (league %s, attempt %s/%s): %s",
                league_id, attempt, retries, exc,
            )
            time.sleep(2 * attempt)
            
    log.error("Giving up on league %s after %s attempts", league_id, retries)
    return []


# ---------------------------------------------------------------------------
# Part A - create fixtures 4 weeks ahead (Continuous window)
# ---------------------------------------------------------------------------
def part_a_fetch_ahead(today=None, test_from=None, test_to=None):
    if test_from and test_to:
        date_from, date_to = test_from, test_to
    else:
        # Start looking from this coming Friday
        date_from = upcoming_friday(today)
        # End looking 4 weeks from that Friday (plus 3 days to catch the final Monday)
        date_to = date_from + datetime.timedelta(weeks=WEEKS_AHEAD, days=3)
        
    season = season_for(date_from)
    
    print(f"\n--- PART A: Fetching upcoming fixtures from {date_from} to {date_to} (Season {season}) ---")
    log.info("PART A: fetching fixtures %s -> %s (season %s)", date_from, date_to, season)

    created = updated = skipped = 0
    for name, league_id in LEAGUE_IDS.items():
        events = get_fixtures(league_id, season)
        
        for fx in events:
            date_str = fx.get("dateEvent")
            if not date_str:
                continue
                
            try:
                match_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                continue
                
            # Only process matches that fall inside our continuous 4-week window
            if not (date_from <= match_date <= date_to):
                continue

            # Guard: only Fri/Sat/Sun/Mon 
            if match_date.weekday() not in (4, 5, 6, 0):
                skipped += 1
                continue

            home_team = fx.get("strHomeTeam", "")
            away_team = fx.get("strAwayTeam", "")
            
            print(f"[Upcoming] {match_date}: {home_team} vs {away_team} (League: {name})")

            obj, was_created = Match.objects.update_or_create(
                match_id=fx["idEvent"],
                defaults={
                    "home_team": home_team,
                    "away_team": away_team,
                    "match_date": match_date,
                    "league": name,
                },
            )
            created += was_created
            updated += (not was_created)
            
        time.sleep(REQUEST_PAUSE)

    print(f"--- PART A DONE: {created} created, {updated} updated, {skipped} skipped ---\n")
    log.info("PART A done: %s created, %s updated, %s skipped", created, updated, skipped)


# ---------------------------------------------------------------------------
# Part B - backfill last week's scores
# ---------------------------------------------------------------------------
def part_b_update_scores(today=None, test_from=None, test_to=None):
    changed_matches = []
    if test_to and test_from:
        date_from, date_to = test_from, test_to
    else:
        this_friday = upcoming_friday(today)
        last_friday = this_friday - datetime.timedelta(weeks=1)
        date_from, date_to = week_window(last_friday)
        
    season = season_for(date_from)

    print(f"--- PART B: Updating past scores from {date_from} to {date_to} (Season {season}) ---")
    log.info("PART B: updating scores %s -> %s (season %s)", date_from, date_to, season)

    scored = postponed = missing = 0
    for name, league_id in LEAGUE_IDS.items():
        events = get_fixtures(league_id, season)
        
        for fx in events:
            date_str = fx.get("dateEvent")
            if not date_str:
                continue
                
            try:
                match_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                continue
                
            if not (date_from <= match_date <= date_to):
                continue
                
            match_id = fx["idEvent"]
            status = fx.get("strStatus", "")
            home_team = fx.get("strHomeTeam", "")
            away_team = fx.get("strAwayTeam", "")

            try:
                match = Match.objects.get(match_id=match_id)
            except Match.DoesNotExist:
                missing += 1
                continue

            if status and status.lower() == "postponed":
                print(f"[Postponed] {match_date}: {home_team} vs {away_team} (League: {name})")
                match.postponed = True
                match.save(update_fields=["postponed"])
                postponed += 1
                continue

            home_score = fx.get("intHomeScore")
            away_score = fx.get("intAwayScore")
            
            if home_score is None or away_score is None:
                continue

            if match.home_score is None or match.away_score is None:
                print(f"[Score Updated] {match_date}: {home_team} {home_score} - {away_score} {away_team} (League: {name})")
                match.home_score = int(home_score)
                match.away_score = int(away_score)
                match.postponed = False
                match.save(update_fields=["home_score", "away_score", "postponed"])
                changed_matches.append(match.pk)
                scored += 1
                
        time.sleep(REQUEST_PAUSE)

    if changed_matches:
        from predictions.models import recompute_points
        n = recompute_points(changed_matches)
        log.info("Recomputed points for %s predictions", n)

    print(f"--- PART B DONE: {scored} scored, {postponed} postponed, {missing} not-in-db ---\n")
    log.info("PART B done: %s scored, %s postponed, %s not-in-db", scored, postponed, missing)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if not API_KEY or API_KEY == "YOUR_API_KEY_GOES_HERE":
        log.error("API KEY not set. Aborting.")
        sys.exit(1)

    part_a_fetch_ahead()
    part_b_update_scores()


if __name__ == "__main__":
    main()