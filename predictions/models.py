from django.db import models
from django.core.exceptions import ValidationError
import datetime
from predictorleague import settings


# Points awarded for each kind of correct prediction.
POINTS_CORRECT_RESULT_HOME_WIN = 50
POINTS_CORRECT_RESULT_DRAW = 100
POINTS_CORRECT_RESULT_AWAY_WIN = 75
POINTS_EXACT_SCORE = 50


class Match(models.Model):
    match_id = models.IntegerField(null=True, unique=True)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    match_date = models.DateField()
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    league = models.CharField(max_length=100, default="")
    predicted = models.BooleanField(default=False)
    postponed = models.BooleanField(default=False)

    @property
    def is_played(self):
        return self.home_score is not None and self.away_score is not None

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} on {self.match_date}"


class Prediction(models.Model):
    # creates a key for the user and the match they predicted
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, default=None
    )
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Stored score for this prediction. Computed once when the match result
    # is known (see calculate_points / recompute_points) instead of on every
    # leaderboard page load. 0 until the match has been played.
    points = models.PositiveIntegerField(default=0, db_index=True)

    def calculate_points(self):
        """Return the points this prediction is worth given the match result.

        Returns 0 if the match has not been played yet. This is pure - it does
        not save - so callers decide when to persist the value.
        """
        match = self.match
        if match.home_score is None or match.away_score is None:
            return 0

        score = 0
        actual_home, actual_away = match.home_score, match.away_score
        pred_home, pred_away = self.predicted_home_score, self.predicted_away_score

        # Correct outcome (home win / draw / away win)
        if actual_home > actual_away and pred_home > pred_away:
            score += POINTS_CORRECT_RESULT_HOME_WIN
        elif actual_home == actual_away and pred_home == pred_away:
            score += POINTS_CORRECT_RESULT_DRAW
        elif actual_home < actual_away and pred_home < pred_away:
            score += POINTS_CORRECT_RESULT_AWAY_WIN

        # Exact scoreline bonus
        if pred_home == actual_home and pred_away == actual_away:
            score += POINTS_EXACT_SCORE

        return score

    def clean(self):  # a method to make sure the input is valid
        # Predictions are non negative integers
        if self.predicted_home_score < 0 or self.predicted_away_score < 0:
            raise ValidationError("A score is negative")
        # User predicts a match only once
        if (
            Prediction.objects.filter(user=self.user, match=self.match)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError("You have already predicted this match")

    def error(self):
        # Scores are greater than 0
        if self.predicted_home_score < 0 or self.predicted_away_score < 0:
            return "Your scores must be positive integers"
        # User predicts a match only once
        if (
            Prediction.objects.filter(user=self.user, match=self.match)
            .exclude(pk=self.pk)
            .exists()
        ):
            return "you have already predicted this match"

    def __str__(self):
        return (
            f"{self.user.username} predicts "
            f"{self.predicted_home_score}-{self.predicted_away_score} for {self.match}"
        )


def recompute_points(match_pks=None):
    """Recompute and store `points` for predictions.

    Pass a list/iterable of Match pks to only recompute predictions for those
    matches (what the weekly scraper does). Pass nothing to recompute every
    prediction (useful for a one-off backfill or after a scoring-rule change).

    Uses bulk_update, so this does NOT fire per-row save signals.
    """
    preds = Prediction.objects.select_related("match")
    if match_pks is not None:
        preds = preds.filter(match_id__in=match_pks)
    preds = list(preds)

    for p in preds:
        p.points = p.calculate_points()

    if preds:
        Prediction.objects.bulk_update(preds, ["points"])
    return len(preds)