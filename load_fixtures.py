import csv
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")
import django
django.setup()
from predictions.models import Match

def run():
    with open('scraped_matches/matches_aug.csv', newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            print(row)
            Match.objects.create(
                home_team = row["Home"],
                away_team = row["Away"],
                match_date = row["Date"],
                league = row["League"]
            )
if __name__ == "__main__":
    run()