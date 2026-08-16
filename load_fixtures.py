import csv
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")
import django
django.setup()
from predictions.models import Match


def create_matches_from_rows(rows):
    """Create a Match row for each dict in `rows` (needs Home/Away/Date/League keys).

    Shared by the CSV-based `run()` below and scrape_and_upload.py, which
    passes scraped rows straight in without writing a CSV in between.
    Returns how many matches were created.
    """
    count = 0
    for row in rows:
        print(row)
        Match.objects.create(
            home_team=row["Home"],
            away_team=row["Away"],
            match_date=row["Date"],
            league=row["League"],
        )
        count += 1
    return count


def run():
    with open('scraped_matches/matches_aug.csv', newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        create_matches_from_rows(reader)


if __name__ == "__main__":
    run()