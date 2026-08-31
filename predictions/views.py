from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from datetime import date, timedelta
import datetime
from .models import Match, Prediction, recompute_points
from django.contrib.auth.decorators import login_required
from . import forms
from django.http import Http404
from django.contrib.auth.models import User
from django.contrib import messages


# Display order for leagues within a match week, top to bottom.
LEAGUE_DISPLAY_ORDER = [
    "premier league",
    "championship",
    "league 1",
    "league 2",
    "national league",
    "scottish premier league",
    "scottish championship",
    "scottish league 1",
    "scottish league 2",
]


def _normalise_league(league_name):
    """Normalise a Match.league value for comparison.

    Different data sources have saved league names with different
    formatting (e.g. "Premier_League" vs "Premier League" vs
    "National_League" vs "National League"), so this collapses
    underscores/spacing/case before any comparison is made against it.
    """
    return " ".join((league_name or "").replace("_", " ").split()).lower()


def _league_sort_key(league_name):
    """Map a Match.league value to its position in LEAGUE_DISPLAY_ORDER.

    Anything not in the list sorts after all known leagues, alphabetically.
    """
    normalised = _normalise_league(league_name)
    try:
        return (0, LEAGUE_DISPLAY_ORDER.index(normalised))
    except ValueError:
        return (1, normalised)


def _is_national_league(match):
    return _normalise_league(match.league) == "national league"


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

    #filtering out other National League games if they've already predicted one that match week
    upcoming_matches_filtered_3 = []
    for match in upcoming_matches_filtered_2:
        if _is_national_league(match):
            week_start = get_match_week_start(match.match_date)
            already_predicted_national_league = any(
                _is_national_league(prediction.match)
                and get_match_week_start(prediction.match.match_date) == week_start
                for prediction in user_predictions
            )
            if already_predicted_national_league:
                continue
        upcoming_matches_filtered_3.append(match)

    #to lock the predictions on saturday, will remove the rest of that matchweek
    if today.weekday() in (5, 6, 0):  # Sat=5, Sun=6, Mon=0
        locked_week_start = get_match_week_start(today)
        upcoming_matches_filtered_3 = [
            m for m in upcoming_matches_filtered_3
            if get_match_week_start(m.match_date) != locked_week_start
        ]

    #goes through each match, works out the friday of the matchweek its in, adds it to the dict
    for match in upcoming_matches_filtered_3:
        week_start = get_match_week_start(match.match_date)
        if week_start in match_dict:
            match_dict[week_start].append(match)
        else:
            match_dict[week_start] = [match]

    # Build each match week as {start, end, matches}, with matches sorted by
    # league (in LEAGUE_DISPLAY_ORDER) then kickoff date - the template's
    # {% regroup %} by league only groups correctly if the list is already
    # sorted by that same key.
    weeks = []
    for week_start, week_matches in sorted(match_dict.items()):
        week_matches.sort(
            key=lambda m: (_league_sort_key(m.league), m.match_date, m.home_team)
        )
        weeks.append({
            "start": week_start,
            "end": week_start + timedelta(days=3),
            "matches": week_matches,
        })

    return render(request, 'predictions/upcoming_matches.html', {'weeks': weeks})

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

    # collect only current match week and onwards
    this_weeks_predictions = []
    for prediction in predictions:
        mw_start = get_match_week_start(prediction.match.match_date)
        if mw_start >= todays_game_week:
            # --- lock everything in that match week from Saturday 00:00 ---
            lock_date = mw_start + timedelta(days=1)     # Friday + 1 day = Saturday
            prediction.is_locked = today >= lock_date    # boolean flag for template
            this_weeks_predictions.append(prediction)

    # sort as before
    this_weeks_predictions.sort(key=lambda p: p.match.match_date)

    # build your output dict as before
    output = {todays_game_week: []}
    for prediction in this_weeks_predictions:
        mw_start = get_match_week_start(prediction.match.match_date)
        if mw_start in output:
            output[mw_start].append(prediction)
        else:
            output[mw_start] = [prediction]

    return render(
        request,
        "predictions/your_predictions.html",
        {"output": output, "today_date": today}
    )

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
        form = forms.EditPredictionForm(request.POST, instance=prediction)
        if form.is_valid():
            print(prediction.user)
            prediction = form.save(commit=False)
            prediction.user = request.user
            prediction.save()
            return redirect("predictions:your_predictions")
    else:
        form = forms.EditPredictionForm(instance=prediction)
    return render(request, "predictions/edit_prediction.html", ({"prediction": prediction, "form": form}))

@login_required(login_url="/users/login/")
def delete_prediction(request, prediction_id):
    prediction = get_object_or_404(Prediction, id=prediction_id, user=request.user)
    predictions = Prediction.objects.all()

    if request.method == 'POST':
        match = prediction.match
        prediction.delete()
        other_has_predicted = False
        for p in predictions:
            if p.match == match:
                other_has_predicted = True
        if not other_has_predicted:
            match.predicted = False
            match.save()
        return redirect('predictions:upcoming_matches')


@login_required(login_url="/users/login/")
def enter_scores(request):
    """Admin-only page to quickly enter results for matches that have been
    played but don't have a score yet.

    Only shows matches that: have kicked off (match_date <= today), were
    actually predicted by someone, don't already have a score, and aren't
    marked as postponed (a postponed match's original date can be in the
    past without the game having happened).
    """
    if not request.user.is_superuser:
        raise Http404

    today = timezone.now().date()

    if request.method == "POST":
        match_ids = request.POST.getlist("match_id")
        updated_pks = []
        for match_id in match_ids:
            home_raw = request.POST.get(f"home_score_{match_id}", "").strip()
            away_raw = request.POST.get(f"away_score_{match_id}", "").strip()
            if home_raw == "" or away_raw == "":
                continue  # left blank - not entered this time round

            try:
                home_score = int(home_raw)
                away_score = int(away_raw)
            except ValueError:
                messages.error(request, "Scores must be whole numbers - one match was skipped.")
                continue

            if home_score < 0 or away_score < 0:
                messages.error(request, "Scores can't be negative - one match was skipped.")
                continue

            match = Match.objects.filter(pk=match_id).first()
            if match is None:
                continue

            match.home_score = home_score
            match.away_score = away_score
            match.save(update_fields=["home_score", "away_score"])
            updated_pks.append(match.pk)

        if updated_pks:
            recompute_points(match_pks=updated_pks)
            messages.success(
                request,
                f"Saved {len(updated_pks)} score{'s' if len(updated_pks) != 1 else ''}.",
            )

        return redirect("predictions:enter_scores")

    matches = Match.objects.filter(
        match_date__lte=today,
        predicted=True,
        postponed=False,
        home_score__isnull=True,
        away_score__isnull=True,
    )
    matches = sorted(
        matches,
        key=lambda m: (m.match_date, _league_sort_key(m.league), m.home_team),
    )

    # Group into one section per day, in date order.
    days = []
    for match in matches:
        if not days or days[-1]["date"] != match.match_date:
            days.append({"date": match.match_date, "matches": []})
        days[-1]["matches"].append(match)

    return render(request, "predictions/enter_scores.html", {"days": days})