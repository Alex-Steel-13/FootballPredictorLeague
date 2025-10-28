from django.shortcuts import render
from django.shortcuts import render, get_object_or_404
from . import Evaluate_Scores
from .models import LeaderboardEntry
from predictions.models import Prediction
from datetime import timedelta
import datetime
from django.utils import timezone
from operator import itemgetter
from django.contrib.auth.models import User


# Create your views here.

def create_leaderboard(leaderboard, predictions=Prediction.objects.all(), last_week=False):
    today = timezone.now()

    for prediction in predictions:
        #Adds the user into the leaderboard
        if not prediction.user.can_participate:
            continue
        if not(check_user_in_leaderboard(prediction, leaderboard)):
            leaderboard.append({"user":prediction.user, 
                                "number_of_predictions": 0,
                                "number_of_played_predictions": 0, 
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
                                "distance_to_placed_position": 0,
                                "points_from_previous_weeks":0,
                                "wb_color": "hsl(0, 0, 0)",
                                "cp_color": "hsl(0, 0, 0)",
                                "non_string_ratio": 0
                                })
        for entry in leaderboard:
            if prediction.user == entry["user"]:
                #increases the number of predictions by 1
                entry["number_of_predictions"] += 1
                if not (prediction.match.home_score is None):
                    entry["number_of_played_predictions"] += 1
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
                #points this week
                match_date = prediction.match.match_date
                start_date = make_previous_friday(today).date()
                end_date = (start_date + datetime.timedelta(days=6))
                if start_date <= match_date <= end_date:
                    entry["points_this_week"] += prediction_points
                #postponed games
                if prediction.match.postponed:
                    entry["postponed_games"] += 1
                
                if get_match_week_start(prediction.match.match_date) <= get_match_week_start((today) - timedelta(days=7)).date():
                    entry["points_from_previous_weeks"] += prediction_points
                
        
    #new loop for stats that don't need a prediction
    pts_min = 1000000000000
    pts_max = 0
    cor_min = 1000000000000
    cor_max = 0
    for entry in leaderboard:
        if entry["points_this_week"] > pts_max:
            pts_max = entry["points_this_week"]
        if entry["perfect_predictions"] > cor_max:
            cor_max = entry["perfect_predictions"]
        if entry["points_this_week"] < pts_min:
            pts_min = entry["points_this_week"]
        if entry["perfect_predictions"] < cor_min:
            cor_min = entry["perfect_predictions"]

        entry["average_points_per_game"] =  round(entry["score"] / entry["number_of_played_predictions"]) if entry["number_of_played_predictions"] else 0

        entry["win_prediction_ratio"] = str(round(entry["correct_winner"] / entry["number_of_played_predictions"], 2)*100) + "%" if entry["number_of_played_predictions"] else 0

        entry["non_string_ratio"] = round(entry["correct_winner"] / entry["number_of_played_predictions"], 2)*100 if entry["number_of_played_predictions"] else 0   

    sorted_leaderboard = order_leaderboard(leaderboard)
    for entry in sorted_leaderboard:
        
        entry["distance_to_first"] = sorted_leaderboard[0]["score"] - entry["score"]

        entry["distance_to_position_above"] = 0 if sorted_leaderboard.index(entry) == 0 else (sorted_leaderboard[sorted_leaderboard.index(entry) - 1]["score"] - entry["score"])
        entry["distance_to_placed_position"] = 0 if sorted_leaderboard.index(entry) <= 4 else (sorted_leaderboard[4]["score"] - entry["score"]) 
    
    #time to do colours

    for entry in sorted_leaderboard:
        entry["wb_color"] = scale_color(
            entry["points_this_week"], 
            pts_min,
            pts_max,
            [(0, 85, 60), (60, 85, 60), (120, 85, 60)]
        )
        entry["cp_color"] = scale_color(
            entry["perfect_predictions"],
            cor_min,
            cor_max,
            [(220, 85, 90), (220, 85, 40)],  # hue fixed at 220, lightness fades
            fixed_hue=True
        )
    predictions_without_this_week = Prediction.objects.filter(match__match_date__lt=get_match_week_start(today))
    
    if not(last_week):
        last_week_leaderboard = []
        last_week_leaderboard = create_leaderboard(last_week_leaderboard,predictions_without_this_week, last_week=True)
        for entry in last_week_leaderboard:
            for x in sorted_leaderboard:
                if entry["user"] == x["user"]:
                    x["position_last_week"] = last_week_leaderboard.index(entry) + 1
    return sorted_leaderboard

def leaderboard(request):
    sorted_leaderboard = create_leaderboard([])
    return render(request, "leaderboard/table.html", {"leaderboard": sorted_leaderboard})

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
    
    actual_draw = draw(prediction.match.home_score, prediction.match.away_score)
    predicted_draw = draw(prediction.predicted_home_score, prediction.predicted_away_score)
    if actual_draw and predicted_draw:
        score += 75
    
    away_team_won = away_won(prediction.match.home_score, prediction.match.away_score)
    predicted_away_won = away_won(prediction.predicted_home_score, prediction.predicted_away_score)
    if away_team_won and predicted_away_won:
        score += 75

    if prediction.predicted_home_score == prediction.match.home_score and prediction.predicted_away_score == prediction.match.away_score:
        score +=50
    return score

def home_won(home_score, away_score):
    if home_score > away_score:
        return True
    else:
        return False

def draw(home_score, away_score):
    return home_score == away_score

def away_won(home_score, away_score):
    if home_score < away_score:
        return True
    else:
        return False


def predictions(request):
    predictions = Prediction.objects.select_related("match")
    today = timezone.now().date()
    match_week = get_match_week_start(make_previous_saturday(today)) 
    predictions_this_week = []
    for prediction in predictions:
        if match_week == get_match_week_start(prediction.match.match_date):
            predictions_this_week.append({"prediction":prediction})
    leaderboard = create_leaderboard()
    user_rankings = {}
    count = 1
    for entry in leaderboard:
        user_rankings[entry["user"].id] = count
        count += 1
    for prediction in predictions_this_week:
        prediction["rank"] = user_rankings[prediction["prediction"].user.id]
    predictions_this_week.sort(key=lambda item: item["rank"])

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

def make_previous_friday(d):
    days_to_subtract = (d.weekday() - 4) % 7
    return d - datetime.timedelta(days=days_to_subtract)

def order_leaderboard(leaderboard):
    return sorted(leaderboard, key=itemgetter("score", "non_string_ratio", "perfect_predictions"), reverse=True)

def scale_color(value, vmin, vmax, colors, fixed_hue=False):
    """Map a value to a color using a 2-stop or 3-stop gradient."""
    try:
        t = (float(value) - vmin) / (vmax - vmin) if vmax != vmin else 0
    except (TypeError, ValueError):
        t = 0
    t = max(0, min(1, t))  # clamp between 0 and 1

    if fixed_hue:
        # Keep hue from first color in list, vary lightness only
        hue, sat, light_start = colors[0]
        _, _, light_end = colors[-1]
        lightness = light_start + t * (light_end - light_start)
        return f"hsl({hue}, {sat}%, {lightness}%)"

    if len(colors) == 2:
        # Simple 2-color gradient
        (h1, s1, l1), (h2, s2, l2) = colors
        hue = h1 + t * (h2 - h1)
        sat = s1 + t * (s2 - s1)
        lig = l1 + t * (l2 - l1)
        return f"hsl({hue:.0f}, {sat:.0f}%, {lig:.0f}%)"

    elif len(colors) == 3:
        # 3-color gradient, split halfway
        if t <= 0.5:
            t2 = t / 0.5
            (h1, s1, l1), (h2, s2, l2) = colors[0], colors[1]
        else:
            t2 = (t - 0.5) / 0.5
            (h1, s1, l1), (h2, s2, l2) = colors[1], colors[2]
        hue = h1 + t2 * (h2 - h1)
        sat = s1 + t2 * (s2 - s1)
        lig = l1 + t2 * (l2 - l1)
        return f"hsl({hue:.0f}, {sat:.0f}%, {lig:.0f}%)"

    else:
        # Fallback: just return first color
        h, s, l = colors[0]
        return f"hsl({h}, {s}%, {l}%)"
    
def manager_of_month(request):
    table = []
    
    predictions = Prediction.objects.all()
    for prediction in predictions:
        if get_match_week_start(prediction.match.match_date).month == (get_match_week_start(timezone.now()).month-1):
            if not prediction.user.can_participate:
                continue
            if not(check_user_in_leaderboard(prediction, table)):
                table.append({
                                "user":prediction.user, 
                                "score": 0,   
                            })
            for entry in table:
                if entry["user"] == prediction.user:
                    entry["score"] += evaluate_score(prediction)
    
    ordered_table = sorted(table, key= lambda x: x["score"], reverse=True )
    return render(request, "leaderboard/manager_of_the_month.html", {"table": ordered_table})

def profile(request, username):
    today = timezone.now()
    profile_user = get_object_or_404(User, username=username)
    predictions = Prediction.objects.filter(user__username=username).order_by("-match__match_date")
    predictions_final = []
    for prediction in predictions:
        if not(get_match_week_start(prediction.match.match_date) == get_match_week_start(today)):
            predictions_final.append(prediction)
    context = {
        'profile_user': profile_user,
        'predictions': predictions_final,
    }
    return render(request, "leaderboard/profile.html", context)