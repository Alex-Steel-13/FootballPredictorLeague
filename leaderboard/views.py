from django.shortcuts import render
from . import Evaluate_Scores
from .models import LeaderboardEntry
from predictions.models import Prediction
from datetime import timedelta
import datetime
from django.utils import timezone

# Create your views here.
def leaderboard(request):
    leaderboard_entry = {"user", "number_of_predictions", "postponed_games", "points_this_week", "score", "average_points_per_game", "distance_to_first", "distance_to_position_above", "perfect_predictions", "win_prediction_ratio", "position_last_week", "correct_winner", "distance_to_placed_position"}
    today = timezone.now()
    leaderboard = []

    predictions = Prediction.objects.all()

    for prediction in predictions:
        #Adds the user into the leaderboard
        if not(check_user_in_leaderboard(prediction, leaderboard)):
            leaderboard.append({"user":prediction.user, 
                                "number_of_predictions": 0, 
                                "postponed_games": 0, 
                                "points_this_week": 0, 
                                "score": 0, 
                                "average_points_per_game": 0, 
                                "distance_to_first": 0, 
                                "distance_to_position_above": 0, 
                                "perfect_predictions": 0, 
                                "win_prediction_ratio": 0, 
                                "position_last_week": 0, 
                                "correct_winner": 0,
                                "distance_to_placed_position": 0})
        for entry in leaderboard:
            if prediction.user == entry["user"]:
                #increases the number of predictions by 1
                entry["number_of_predictions"] += 1
                #increases score
                prediction_points = evaluate_score(prediction)
                entry["score"] += prediction_points
                #increases points this week
                if get_match_week_start(prediction.match.match_date) == get_match_week_start(today):
                    entry["points_this_week"] += prediction_points
                #Perfect predictions counter
                if prediction_points >= 100:
                    entry["perfect_predictions"] += 1
                #Adds one if predicts correct winner, needed for other stat
                if prediction_points != 0:
                    entry["correct_winner"] += 1
    
    #ordering
    leaderboard.sort(key = lambda entry: entry["score"])
    """
    for entry in leaderboard.sort(key = lambda entry: entry["score"]):
        #here to do dealing with ties
        break
    """


        
    #new loop for stats that don't need a prediction
    for entry in leaderboard:
        entry["average_points_per_game"] = round(entry["score"] / entry["number_of_predictions"])
        entry["win_prediction_ratio"] = round(entry["correct_winner"] / entry["number_of_predictions"], 2)
        entry["distance_to_first"] = leaderboard[0]["score"] - entry["score"]
        entry["distance_to_position_above"] = 0 if leaderboard.index(entry) == 0 else (leaderboard[leaderboard.index(entry) - 1]["score"] - entry["score"])
        entry["distance_to_placed_position"] = 0 if leaderboard.index(entry) <= 2 else (leaderboard[2]["score"] - entry["score"])    

    return render(request, "leaderboard/table.html", {"leaderboard": leaderboard})

def check_user_in_leaderboard(prediction, leaderboard):
    user = prediction.user
    for entry in leaderboard:
        if entry["user"] == user:
            return True
    return False

def evaluate_score(prediction):
    score = 0
    if prediction.match.home_score == None or prediction.match.away_score == None:
        return score
    home_team_won = home_won(prediction.match.home_score, prediction.match.away_score)
    predicted_home_won = home_won(prediction.predicted_home_score, prediction.predicted_away_score)
    if home_team_won and predicted_home_won:
        score += 50
    elif not(home_team_won) and not(predicted_home_won):
        score += 75
    if prediction.predicted_home_score == prediction.match.home_score and prediction.predicted_away_score == prediction.match.away_score:
        score +=50
    return score

def home_won(home_score, away_score):
    if home_score > away_score:
        return True


def predictions(request):
    predictions = Prediction.objects.select_related("match")
    match_week = get_match_week_start(make_previous_saturday(timezone.now().date()))
    predictions_this_week = []
    for prediction in predictions:
        if match_week == get_match_week_start(prediction.match.match_date):
            predictions_this_week.append(prediction)
    

    return render(request, "leaderboard/predictions.html", {"predictions": predictions_this_week})

def get_match_week_start(d):
    """Returns the Friday of the week the date falls in (Friday–Monday window)."""
    weekday = d.weekday()  # Monday=0 ... Sunday=6

    if weekday <= 3 and weekday != 0:  # Tuesday (1) to Thursday (3)
        # These should be considered part of the *next* match week
        days_until_friday = 4 - weekday
        return d + timedelta(days=days_until_friday)

    else:  # Friday (4), Saturday (5), Sunday (6), Monday(0)
        # These belong to the *current* match week
        days_since_friday = (weekday - 4) % 7
        return d - timedelta(days=days_since_friday)

def make_previous_saturday(d):
    days_to_subtract = (d.weekday() - 5) % 7
    return d - datetime.timedelta(days=days_to_subtract)