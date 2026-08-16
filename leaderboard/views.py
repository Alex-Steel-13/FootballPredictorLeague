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
# Profile
# ---------------------------------------------------------------------------
def profile(request, username):
    today = timezone.now()
    this_week = get_match_week_start(today)
    profile_user = get_object_or_404(User, username=username)

    predictions = (
        Prediction.objects
        .filter(user__username=username)
        .select_related("match")
        .order_by("-match__match_date")
    )
    predictions_final = [
        p for p in predictions
        if get_match_week_start(p.match.match_date) != this_week
    ]

    return render(request, "leaderboard/profile.html", {
        "profile_user": profile_user,
        "predictions": predictions_final,
    })


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
        {"prediction": p, "rank": user_rankings.get(p.user_id, len(leaderboard) + 1)}
        for p in this_week_preds
    ]
    rows.sort(key=lambda item: item["rank"])

    return render(request, "leaderboard/predictions.html", {"predictions": rows})