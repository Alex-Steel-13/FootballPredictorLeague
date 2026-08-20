import datetime

from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q, F
from django.utils import timezone

from .models import Prediction

User = get_user_model()

# ---------------------------------------------------------------------------
# Match-week helpers (Friday -> Monday window)
# ---------------------------------------------------------------------------
def get_match_week_start(d):
    """Return the Friday of the match week the date falls in (Fri-Mon window)."""
    weekday = d.weekday()  # Monday=0 ... Sunday=6
    if weekday != 0 and weekday <= 3:  # Tue(1)-Thu(3) belong to the NEXT week
        return d + datetime.timedelta(days=4 - weekday)
    # Fri(4), Sat(5), Sun(6), Mon(0) belong to the CURRENT match week
    days_since_friday = (weekday - 4) % 7
    return d - datetime.timedelta(days=days_since_friday)


def make_previous_friday(d):
    return d - datetime.timedelta(days=(d.weekday() - 4) % 7)


def make_previous_saturday(d):
    return d - datetime.timedelta(days=(d.weekday() - 5) % 7)


def current_week_window(today=None):
    """(start_date, end_date) for the current match week, as dates."""
    today = today or timezone.now()
    start = make_previous_friday(today).date()
    return start, start + datetime.timedelta(days=6)


# ---------------------------------------------------------------------------
# Colour scaling
# ---------------------------------------------------------------------------
def scale_color(value, vmin, vmax, colors, fixed_hue=False):
    """Map a value to a color using a 2-stop or 3-stop gradient."""
    try:
        t = (float(value) - vmin) / (vmax - vmin) if vmax != vmin else 0
    except (TypeError, ValueError):
        t = 0
    t = max(0, min(1, t))  # clamp between 0 and 1

    if fixed_hue:
        hue, sat, light_start = colors[0]
        _, _, light_end = colors[-1]
        lightness = light_start + t * (light_end - light_start)
        return f"hsl({hue}, {sat}%, {lightness}%)"

    if len(colors) == 2:
        (h1, s1, l1), (h2, s2, l2) = colors
        return (
            f"hsl({h1 + t * (h2 - h1):.0f}, "
            f"{s1 + t * (s2 - s1):.0f}%, {l1 + t * (l2 - l1):.0f}%)"
        )

    if len(colors) == 3:
        if t <= 0.5:
            t2 = t / 0.5
            (h1, s1, l1), (h2, s2, l2) = colors[0], colors[1]
        else:
            t2 = (t - 0.5) / 0.5
            (h1, s1, l1), (h2, s2, l2) = colors[1], colors[2]
        return (
            f"hsl({h1 + t2 * (h2 - h1):.0f}, "
            f"{s1 + t2 * (s2 - s1):.0f}%, {l1 + t2 * (l2 - l1):.0f}%)"
        )

    h, s, l = colors[0]
    return f"hsl({h}, {s}%, {l}%)"


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------
def build_leaderboard(today=None):
    """Build the full, sorted leaderboard.

    All the per-prediction work happens in the database via aggregation over
    the stored `points` column. Python only does the cheap O(n) post-processing
    (sorting, gap-to-rival stats, colours).
    """
    today = today or timezone.now()
    week_start, week_end = current_week_window(today)
    prev_week_cutoff = get_match_week_start(today - datetime.timedelta(days=7))
    if hasattr(prev_week_cutoff, "date"):
        prev_week_cutoff = prev_week_cutoff.date()

    # One query: group predictions by user, aggregate every stat we need.
    rows = (
        Prediction.objects
        .filter(user__can_participate=True)
        .values("user_id", "user__username")
        .annotate(
            number_of_predictions=Count("id"),
            number_of_played_predictions=Count(
                "id", filter=Q(match__home_score__isnull=False)
            ),
            postponed_games=Count("id", filter=Q(match__postponed=True)),
            score=Sum("points"),
            points_this_week=Sum(
                "points",
                filter=Q(match__match_date__gte=week_start,
                         match__match_date__lte=week_end),
            ),
            points_from_previous_weeks=Sum(
                "points", filter=Q(match__match_date__lt=week_start)
            ),
            perfect_predictions=Count(
                "id",
                filter=Q(
                    predicted_home_score=F("match__home_score"),
                    predicted_away_score=F("match__away_score"),
                ),
            ),
            correct_winner=Count("id", filter=Q(points__gt=0)),
        )
    )

    # Materialise into the dict shape the template expects, coercing the
    # SUM-of-nothing NULLs to 0.
    user_ids = [r["user_id"] for r in rows]
    users = User.objects.in_bulk(user_ids)

    leaderboard = []
    for r in rows:
        played = r["number_of_played_predictions"]
        correct = r["correct_winner"]
        non_string_ratio = round(correct / played, 2) * 100 if played else 0
        leaderboard.append({
            "user": users[r["user_id"]],
            "number_of_predictions": r["number_of_predictions"],
            "number_of_played_predictions": played,
            "postponed_games": r["postponed_games"],
            "points_this_week": r["points_this_week"] or 0,
            "score": r["score"] or 0,
            "points_from_previous_weeks": r["points_from_previous_weeks"] or 0,
            "perfect_predictions": r["perfect_predictions"],
            "correct_winner": correct,
            "average_points_per_game": (r["score"] or 0) // played if played else 0,
            "win_prediction_ratio": f"{round(correct / played * 100)}%" if played else "0%",
            "non_string_ratio": non_string_ratio,
            # filled in below
            "distance_to_first": 0,
            "distance_to_position_above": 0,
            "distance_to_placed_position": 0,
            "position_last_week": 0,
            "wb_color": "hsl(0, 0, 0)",
            "cp_color": "hsl(0, 0, 0)",
        })

    leaderboard.sort(
        key=lambda e: (e["score"], e["non_string_ratio"], e["perfect_predictions"]),
        reverse=True,
    )

    if not leaderboard:
        return leaderboard

    # Position last week: rank everyone by the cumulative score they had
    # *before* this week's matches (points_from_previous_weeks) - i.e. the
    # table as it stood after last week's games. Ties break alphabetically
    # so the ranking is stable.
    last_week_order = sorted(
        leaderboard,
        key=lambda e: (-e["points_from_previous_weeks"], e["user"].username),
    )
    for rank, entry in enumerate(last_week_order, start=1):
        entry["position_last_week"] = rank

    # Single O(n) pass for gap stats + colour ranges.
    first_score = leaderboard[0]["score"]
    fifth_score = leaderboard[4]["score"] if len(leaderboard) > 4 else leaderboard[-1]["score"]
    pts_values = [e["points_this_week"] for e in leaderboard]
    cor_values = [e["perfect_predictions"] for e in leaderboard]
    pts_min, pts_max = min(pts_values), max(pts_values)
    cor_min, cor_max = min(cor_values), max(cor_values)

    for i, entry in enumerate(leaderboard):
        entry["distance_to_first"] = first_score - entry["score"]
        entry["distance_to_position_above"] = (
            0 if i == 0 else leaderboard[i - 1]["score"] - entry["score"]
        )
        gap_to_fifth = fifth_score - entry["score"]
        entry["distance_to_placed_position"] = 0 if gap_to_fifth <= 0 else gap_to_fifth

        entry["wb_color"] = scale_color(
            entry["points_this_week"], pts_min, pts_max,
            [(0, 85, 60), (60, 85, 60), (120, 85, 60)],
        )
        entry["cp_color"] = scale_color(
            entry["perfect_predictions"], cor_min, cor_max,
            [(220, 85, 90), (220, 85, 40)], fixed_hue=True,
        )

    return leaderboard


def leaderboard_view(request):
    return render(
        request, "leaderboard/table.html",
        {"leaderboard": build_leaderboard()},
    )


# ---------------------------------------------------------------------------
# Manager of the month
# ---------------------------------------------------------------------------
def manager_of_month(request):
    today = timezone.now()
    target_month = (get_match_week_start(today).month - 1) or 12

    rows = (
        Prediction.objects
        .filter(user__can_participate=True,
                match__match_date__month=target_month)
        .values("user_id")
        .annotate(score=Sum("points"))
        .order_by("-score")
    )
    users = User.objects.in_bulk([r["user_id"] for r in rows])
    table = [{"user": users[r["user_id"]], "score": r["score"] or 0} for r in rows]

    return render(
        request, "leaderboard/manager_of_the_month.html", {"table": table},
    )


# ---------------------------------------------------------------------------
# Player stats (profile page)
# ---------------------------------------------------------------------------
# (metric key, ascending) - ascending=True means "lower is better" (rank 1
# goes to the smallest value), used only for incorrect_results. Everything
# else ranks highest-value-first.
_STATS_RANK_METRICS = [
    ("total_predictions", False),
    ("perfect_predictions", False),
    ("correct_results", False),
    ("incorrect_results", True),
    ("home_predictions", False),
    ("away_predictions", False),
    ("draw_predictions", False),
    ("perfect_home", False),
    ("perfect_away", False),
    ("perfect_draw", False),
    ("correct_home", False),
    ("correct_away", False),
    ("correct_draw", False),
]


def _rank(value, values, ascending=False):
    """Standard competition ranking (1, 2, 2, 4, ...) of `value` within `values`."""
    if ascending:
        beaten = sum(1 for v in values if v < value)
    else:
        beaten = sum(1 for v in values if v > value)
    return beaten + 1


def _pct(value, denominator):
    """Whole-number percentage, or None if there's nothing to divide by."""
    return round(value / denominator * 100) if denominator else None


def build_player_stats():
    """Per-user prediction stats + each user's rank on every stat.

    The ranked pool is every user with can_participate=True (whether or not
    they've made a prediction yet), matching the leaderboard's definition of
    "everyone". Returns (stats_by_user_id, total_participants).
    """
    users = (
        User.objects.filter(can_participate=True)
        .annotate(
            total_predictions=Count("prediction", distinct=True),
            played_predictions=Count(
                "prediction",
                filter=Q(prediction__match__home_score__isnull=False),
                distinct=True,
            ),
            perfect_predictions=Count(
                "prediction",
                filter=Q(
                    prediction__predicted_home_score=F("prediction__match__home_score"),
                    prediction__predicted_away_score=F("prediction__match__away_score"),
                ),
                distinct=True,
            ),
            correct_results=Count(
                "prediction", filter=Q(prediction__points__gt=0), distinct=True
            ),
            home_predictions=Count(
                "prediction",
                filter=Q(prediction__predicted_home_score__gt=F("prediction__predicted_away_score")),
                distinct=True,
            ),
            away_predictions=Count(
                "prediction",
                filter=Q(prediction__predicted_home_score__lt=F("prediction__predicted_away_score")),
                distinct=True,
            ),
            draw_predictions=Count(
                "prediction",
                filter=Q(prediction__predicted_home_score=F("prediction__predicted_away_score")),
                distinct=True,
            ),
            perfect_home=Count(
                "prediction",
                filter=Q(
                    prediction__predicted_home_score=F("prediction__match__home_score"),
                    prediction__predicted_away_score=F("prediction__match__away_score"),
                    prediction__predicted_home_score__gt=F("prediction__predicted_away_score"),
                ),
                distinct=True,
            ),
            perfect_away=Count(
                "prediction",
                filter=Q(
                    prediction__predicted_home_score=F("prediction__match__home_score"),
                    prediction__predicted_away_score=F("prediction__match__away_score"),
                    prediction__predicted_home_score__lt=F("prediction__predicted_away_score"),
                ),
                distinct=True,
            ),
            perfect_draw=Count(
                "prediction",
                filter=(
                    Q(prediction__predicted_home_score=F("prediction__match__home_score"))
                    & Q(prediction__predicted_away_score=F("prediction__match__away_score"))
                    & Q(prediction__predicted_home_score=F("prediction__predicted_away_score"))
                ),
                distinct=True,
            ),
            correct_home=Count(
                "prediction",
                filter=Q(
                    prediction__points__gt=0,
                    prediction__predicted_home_score__gt=F("prediction__predicted_away_score"),
                ),
                distinct=True,
            ),
            correct_away=Count(
                "prediction",
                filter=Q(
                    prediction__points__gt=0,
                    prediction__predicted_home_score__lt=F("prediction__predicted_away_score"),
                ),
                distinct=True,
            ),
            correct_draw=Count(
                "prediction",
                filter=Q(
                    prediction__points__gt=0,
                    prediction__predicted_home_score=F("prediction__predicted_away_score"),
                ),
                distinct=True,
            ),
        )
    )

    stats = {}
    for u in users:
        played = u.played_predictions
        perfect = u.perfect_predictions
        correct = u.correct_results
        incorrect = played - correct
        total = u.total_predictions

        stats[u.id] = {
            "username": u.username,
            "total_predictions": total,
            "played_predictions": played,
            "perfect_predictions": perfect,
            "perfect_pct": _pct(perfect, played),
            "correct_results": correct,
            "correct_pct": _pct(correct, played),
            "incorrect_results": incorrect,
            "incorrect_pct": _pct(incorrect, played),
            "home_predictions": u.home_predictions,
            "home_pct": _pct(u.home_predictions, total),
            "away_predictions": u.away_predictions,
            "away_pct": _pct(u.away_predictions, total),
            "draw_predictions": u.draw_predictions,
            "draw_pct": _pct(u.draw_predictions, total),
            "perfect_home": u.perfect_home,
            "perfect_home_pct": _pct(u.perfect_home, perfect),
            "perfect_away": u.perfect_away,
            "perfect_away_pct": _pct(u.perfect_away, perfect),
            "perfect_draw": u.perfect_draw,
            "perfect_draw_pct": _pct(u.perfect_draw, perfect),
            "correct_home": u.correct_home,
            "correct_home_pct": _pct(u.correct_home, correct),
            "correct_away": u.correct_away,
            "correct_away_pct": _pct(u.correct_away, correct),
            "correct_draw": u.correct_draw,
            "correct_draw_pct": _pct(u.correct_draw, correct),
        }

    total_participants = len(stats)
    for key, ascending in _STATS_RANK_METRICS:
        values = [row[key] for row in stats.values()]
        for row in stats.values():
            row[f"{key}_rank"] = _rank(row[key], values, ascending)

    return stats, total_participants


def _stats_table(stats, username):
    """Turn the flat stats dict into the grouped sections the template renders.

    Each row carries exactly what the table needs: a label, the raw value,
    an optional percentage (None renders as "—"), and this user's rank.
    """
    played = stats["played_predictions"]
    total = stats["total_predictions"]
    perfect = stats["perfect_predictions"]
    correct = stats["correct_results"]

    def row(label, value_key, pct_key=None):
        return {
            "label": label,
            "value": stats[value_key],
            "pct": stats.get(pct_key) if pct_key else None,
            "rank": stats[f"{value_key}_rank"],
        }

    return [
        {
            "title": "Overview",
            "note": f"Every prediction {username} has ever submitted "
                    f"({played} of them played so far).",
            "rows": [row("Total Predictions", "total_predictions")],
        },
        {
            "title": "Perfect Predictions",
            "note": f"Exact scoreline correct, as a share of {played} played predictions.",
            "rows": [row("Perfect Predictions", "perfect_predictions", "perfect_pct")],
        },
        {
            "title": "Correct Results",
            "note": f"Correct winner (or correctly-called draw), as a share of "
                    f"{played} played predictions.",
            "rows": [row("Correct Results", "correct_results", "correct_pct")],
        },
        {
            "title": "Incorrect Results",
            "note": "Wrong winner/draw call. Rank 1 = fewest incorrect results.",
            "rows": [row("Incorrect Results", "incorrect_results", "incorrect_pct")],
        },
        {
            "title": "Prediction Split",
            "note": f"What {username} tends to predict, as a share of all {total} predictions.",
            "rows": [
                row("Home Win Predictions", "home_predictions", "home_pct"),
                row("Away Win Predictions", "away_predictions", "away_pct"),
                row("Draw Predictions", "draw_predictions", "draw_pct"),
            ],
        },
        {
            "title": "Perfect Prediction Split",
            "note": f"Share of {username}'s {perfect} perfect predictions.",
            "rows": [
                row("Perfect Home Wins", "perfect_home", "perfect_home_pct"),
                row("Perfect Away Wins", "perfect_away", "perfect_away_pct"),
                row("Perfect Draws", "perfect_draw", "perfect_draw_pct"),
            ],
        },
        {
            "title": "Correct Result Split",
            "note": f"Share of {username}'s {correct} correct results.",
            "rows": [
                row("Correct Home Wins", "correct_home", "correct_home_pct"),
                row("Correct Away Wins", "correct_away", "correct_away_pct"),
                row("Correct Draws", "correct_draw", "correct_draw_pct"),
            ],
        },
    ]


def _match_week_reveal_date(match_date):
    """The date a match's prediction becomes visible to other users.

    Same Saturday-00:00 threshold used to lock predictions from editing
    (see your_predictions' lock_date) and the one "everyone's predictions
    this week" already relies on implicitly via its match-week window: once
    a match week's predictions are locked, nobody can change theirs after
    peeking at someone else's, so it's safe to reveal them.
    """
    return get_match_week_start(match_date) + datetime.timedelta(days=1)


def _prediction_is_public(prediction, today=None):
    """Whether a prediction should be visible to someone other than its owner.

    Two independent gates, both must pass:
    - the match has actually been played (has a recorded score) - otherwise
      there's nothing real to show yet, regardless of date.
    - today is on/after that match week's reveal date - the same anti-copying
      cutoff "everyone's predictions this week" uses.
    """
    today = today or timezone.now().date()
    match = prediction.match
    if match.home_score is None or match.away_score is None:
        return False
    return today >= _match_week_reveal_date(match.match_date)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def profile(request, username):
    profile_user = get_object_or_404(User, username=username)

    predictions = (
        Prediction.objects
        .filter(user__username=username)
        .select_related("match")
        .order_by("-match__match_date")
    )
    today_date = timezone.now().date()
    predictions_final = [
        p for p in predictions if _prediction_is_public(p, today_date)
    ]
    for p in predictions_final:
        p.result_class = prediction_result_class(p)

    stats_by_user, total_participants = build_player_stats()
    stats = stats_by_user.get(profile_user.id)
    stats_table = _stats_table(stats, profile_user.username) if stats else None

    return render(request, "leaderboard/profile.html", {
        "profile_user": profile_user,
        "predictions": predictions_final,
        "stats_table": stats_table,
        "total_participants": total_participants,
    })


def _match_outcome(home_score, away_score):
    if home_score > away_score:
        return "home"
    if home_score == away_score:
        return "draw"
    return "away"


def prediction_result_class(prediction):
    """CSS class describing how a scored prediction turned out.

    None while the match hasn't been played yet. Compares scores directly
    rather than going via the stored `points` value, so it can't be thrown
    off by stale points (see the perfect_predictions leaderboard bug).
    """
    match = prediction.match
    if not match.is_played:
        return None

    if (prediction.predicted_home_score == match.home_score
            and prediction.predicted_away_score == match.away_score):
        return "perfect_prediction"

    predicted_outcome = _match_outcome(
        prediction.predicted_home_score, prediction.predicted_away_score
    )
    actual_outcome = _match_outcome(match.home_score, match.away_score)
    return "correct_result" if predicted_outcome == actual_outcome else "wrong_result"


# ---------------------------------------------------------------------------
# This week's predictions, ranked by the user's leaderboard position
# ---------------------------------------------------------------------------
def predictions(request):
    today = timezone.now().date()
    match_week = get_match_week_start(make_previous_saturday(today))

    # Rank lookup comes from the single leaderboard build (no second rebuild).
    leaderboard = build_leaderboard()
    user_rankings = {
        entry["user"].id: rank for rank, entry in enumerate(leaderboard, start=1)
    }

    this_week_preds = (
        Prediction.objects
        .select_related("match", "user")
        .filter(match__match_date__gte=match_week,
                match__match_date__lte=match_week + datetime.timedelta(days=3))
    )

    rows = [
        {
            "prediction": p,
            "rank": user_rankings.get(p.user_id, len(leaderboard) + 1),
            "result_class": prediction_result_class(p),
        }
        for p in this_week_preds
    ]
    rows.sort(key=lambda item: item["rank"])

    return render(request, "leaderboard/predictions.html", {"predictions": rows})