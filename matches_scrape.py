import os
import sys




import requests
from bs4 import BeautifulSoup
import pandas as pd
import datetime



def get_rows(base_URL, month):
    URL =base_URL + "/" + month
    r = requests.get(URL)
    soup = BeautifulSoup(r.content, 'html5lib')
    table = soup.find('div', id="fixtures-results-refreshable")
    print("Table found:", table is not None)
    rows = table.find_all("tr")
    print("Rows found:", rows is not None)
    return rows

def split_match(match):
    try:
        parts = match.split(" v ")
        home = parts[0].strip()
        away = parts[1].strip()
        return (home, away)
    except:
        return (match, None)

def convert_datetime(input):
    parts = input.split(" ")
    return datetime.date(int(parts[3]), int(month_to_number(parts[2])), int(parts[1][:-2]))

def month_to_number(month):
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12
    }
    return months.get(month.lower())

def number_to_month(number):
    months = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    if 1 <= number <= 12:
        return months[number -1]
    return None


def scrape_data(url, league):
    month_int = datetime.datetime.now().month + 0
    if month_int <= 10:
        month = number_to_month(month_int)
    elif month_int == 11:
        month = number_to_month(1)
    elif month_int == 12:
        month = number_to_month(1)
    print(month)

    unsorted_rows = get_rows(url, month)
    print(unsorted_rows[0])

    schedule = {}
    current_date = ""
    adding = False


    for row in unsorted_rows:
        class_row = row.get("class", [])
        if "title" in row.get("class", []):
            current_date = row.get("title")
            schedule[current_date] = []
        elif "first" in row.get("class", []):
            schedule[current_date].append(split_match(row.get("title")))
            adding = True
            continue
        elif "spacer" in row.get("class", []):
            adding = False

        if adding:
            schedule[current_date].append(split_match(row.get("title")))
    result =[]
    for key, value in schedule.items():
        for home,away in value:
            if home != None and away != None and is_weekend_or_monday(convert_datetime(key)):
                result.append({"Date": convert_datetime(key), "Home" : home, "Away" : away, "League" : league})

    return result

def is_weekend_or_monday(date):
    """
    Takes a date as input and returns True if the day is Friday/Saturday/Sunday/Monday,
    False otherwise.
    """
    # Get the day of the week (0=Monday, 1=Tuesday, ..., 6=Sunday)
    day_of_week = date.weekday()
    
    # Monday=0, Friday=4, Saturday=5, Sunday=6
    return day_of_week in [0, 4, 5, 6]

urls = {
    "Premier League": "https://www.footballwebpages.co.uk/premier-league/fixtures-results",
    "Championship": "https://www.footballwebpages.co.uk/championship/fixtures-results",
    "League 1": "https://www.footballwebpages.co.uk/league-one/fixtures-results",
    "League 2": "https://www.footballwebpages.co.uk/league-two/fixtures-results",
    "National League": "https://www.footballwebpages.co.uk/national-league/fixtures-results",
    "Scottish Premier_League": "https://www.footballwebpages.co.uk/scottish-premiership/fixtures-results",
    "Scottish Championship": "https://www.footballwebpages.co.uk/scottish-championship/fixtures-results",
    "Scottish League_1": "https://www.footballwebpages.co.uk/scottish-league-one/fixtures-results",
    "Scottish League_2": "https://www.footballwebpages.co.uk/scottish-league-two/fixtures-results"
    }



data = []
for key,value in urls.items():
    result = scrape_data(value, key)
    if isinstance(result, list):
        data.extend(result)  # Add each item from the list individually
    else:
        data.append(result)  # Just a single dictionary

df = pd.DataFrame(data)

os.makedirs('scraped_matches', exist_ok=True)
df.to_csv('scraped_matches/matches_aug.csv', index=False)
