from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from datetime import date, timedelta
import datetime
from .models import Match, Prediction
from django.contrib.auth.decorators import login_required
from . import forms
from django.http import Http404
from django.contrib.auth.models import User
from django.contrib import messages


# Create your views here.
@login_required(login_url="/users/login/")
def upcoming_matches(request):
    today = timezone.now().date()
    upcoming_matches = Match.objects.filter(match_date__gte=today)
    match_dict = {}
    user_predictions = Prediction.objects.filter(user=request.user)

    #filtering if they have predicted that team in the month
    upcoming_matches_filtered = []
    for match in upcoming_matches:
        week_start = get_match_week_start(match.match_date)
        month = week_start.month
        not_predicted = True

        for prediction in user_predictions:
            if get_match_week_start(prediction.match.match_date).month == month:
                teams = (prediction.match.home_team, prediction.match.away_team)
                if match.home_team in teams or match.away_team in teams:
                    not_predicted = False
        if not_predicted:
            upcoming_matches_filtered.append(match)
    
    #filtering if they have predicted 2 matches in that match week
    upcoming_matches_filtered_2 = []
    for match in upcoming_matches_filtered:
        week_start = get_match_week_start(match.match_date)
        count = 0
        for prediction in user_predictions:
            if week_start == get_match_week_start(prediction.match.match_date):
                count += 1
        if count <= 1:
            upcoming_matches_filtered_2.append(match)

                

    #goes through each match, works out the friday of the matchweek its in, adds it to the dict
    for match in upcoming_matches_filtered_2:
        week_start = get_match_week_start(match.match_date)
        if week_start in match_dict:
            match_dict[week_start].append(match)
        else:
            match_dict[week_start] = [match]
    
    #to lock the predictions on saturday, will remove the rest of that matchweek
    if today.weekday() == 0 or today.weekday() >= 5:
        value = match_dict.pop(get_match_week_start(today),None)
    return render(request, 'predictions/upcoming_matches.html', {'matches': match_dict.items()})

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

def make_date_next_tuesday(d):
    weekday = d.weekday()  
    days_until_next_tuesday = (1 - weekday + 7) % 7
    days_until_next_tuesday = 7 if days_until_next_tuesday == 0 else days_until_next_tuesday
    return d + timedelta(days=days_until_next_tuesday)



@login_required(login_url="/users/login/")
def predict(request, match_id):
    print("User:", request.user)
    print("Authenticated:", request.user.is_authenticated)

    match = get_object_or_404(Match, pk=match_id)

    if request.method == "POST":
        form = forms.PredictionForm(request.POST)
        form.instance.user = request.user
        form.instance.match = match
        if form.is_valid():
            form.save()
            match.predicted = True
            match.save()
            return redirect('predictions:upcoming_matches')
        else:
            prediction = form.save(commit=False)
            error_in_prediction = prediction.error()
            messages.error(request, error_in_prediction)
            return redirect("predictions:predict_match", match_id=match.id)

    else:
        form = forms.PredictionForm(initial={"match" : match})
        print(form.errors)
        
    return render(request, "predictions/predict_match.html", {"form" : form, "match" : match})

@login_required(login_url="/users/login/")
def your_predictions(request):
    user = request.user
    predictions = Prediction.objects.filter(user=user)
    today = timezone.now().date()
    todays_game_week = get_match_week_start(today)

    this_weeks_predictions = [] #actually this all the predictions that are in the current match week and onwards
    for prediction in predictions:
        if get_match_week_start(prediction.match.match_date) >= todays_game_week:
            this_weeks_predictions.append(prediction)
    this_weeks_predictions.sort(key = lambda prediction: prediction.match.match_date)
    output = {todays_game_week : []}
    for prediction in this_weeks_predictions:
        if get_match_week_start(prediction.match.match_date) in output.keys():
            output[get_match_week_start(prediction.match.match_date)].append(prediction)
        else:
            output[get_match_week_start(prediction.match.match_date)] = [prediction]


    return render(request, "predictions/your_predictions.html", {"output" : output, "today_date" : today})

@login_required(login_url="/users/login/")
def your_past_predictions(request):
    user = request.user
    today = timezone.now().date()
    todays_game_week = get_match_week_start(today)
    predictions = Prediction.objects.filter(user=user)


    this_weeks_predictions = [] #actually this all the predictions that are in the current match week and onwards
    for prediction in predictions:
        if get_match_week_start(prediction.match.match_date) < todays_game_week:
            this_weeks_predictions.append(prediction)
    this_weeks_predictions.sort(key = lambda prediction: prediction.match.match_date, reverse=True)
    output = {}
    for prediction in this_weeks_predictions:
        if get_match_week_start(prediction.match.match_date) in output.keys():
            output[get_match_week_start(prediction.match.match_date)].append(prediction)
        else:
            output[get_match_week_start(prediction.match.match_date)] = [prediction]


    return render(request, "predictions/your_past_predictions.html", {"output" : output, "today_date" : today})

@login_required(login_url="/users/login/")
def edit_prediction(request, prediction_id):
    prediction = get_object_or_404(Prediction, id=prediction_id, user=request.user)

    if request.method == "POST":
        form = forms.EditPredictionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("predictions:your_predictions")
    else:
        form = forms.EditPredictionForm(instance=prediction)
    return render(request, "predictions/edit_prediction.html", ({"prediction": prediction, "form": form}))

@login_required(login_url="/users/login/")
def delete_prediction(request, prediction_id):
    prediction = get_object_or_404(Prediction, id=prediction_id, user=request.user)

    if request.method == 'POST':
        prediction.delete()
        return redirect('predictions:upcoming_matches')