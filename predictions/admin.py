from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect
from .models import Match, Prediction, recompute_points

# Register your models here.
class MatchAdmin(admin.ModelAdmin):
    change_list_template = "admin/predictions/match/change_list.html"

    fieldsets = [
        ("Date", {"fields":["match_date"]}),
        ("Predicted", {"fields": ["predicted"]}),
        ("Teams", {"fields": ["home_team", "away_team"]}),
        ("Scores", {"fields": ["home_score", "away_score"]}),
        ("League", {"fields": ["league"]})
    ]

    list_display = ["home_team", "away_team", "league", "match_date", "home_score", "away_score", "predicted"]

    list_filter = ["predicted", "match_date"]

    search_fields = ["match_date", "home_team", "away_team"]

    def get_urls(self):
        urls = [
            path(
                "recalculate-scores/",
                self.admin_site.admin_view(self.recalculate_scores),
                name="predictions_match_recalculate_scores",
            ),
        ]
        return urls + super().get_urls()

    def recalculate_scores(self, request):
        n = recompute_points()
        self.message_user(
            request,
            f"Recomputed points for {n} predictions.",
            level=messages.SUCCESS,
        )
        return redirect("admin:predictions_match_changelist")


admin.site.register(Match, MatchAdmin)
admin.site.register(Prediction)