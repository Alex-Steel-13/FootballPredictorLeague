import csv
from predictions.models import Match

def run():
    with open('matches.csv', newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            Match.objects.create(
                home_team = row["Home"],
                away_team = row["Away"],
                match_date = row["Date"],
                league = row["League"]
            )