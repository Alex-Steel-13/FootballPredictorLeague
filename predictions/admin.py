from django.contrib import admin
from .models import Match, Prediction

# Register your models here.
class MatchAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Date", {"fields":["match_date"]}),
        ("Predicted", {"fields": ["predicted"]}),
        ("Teams", {"fields": ["home_team", "away_team"]}),
        ("Scores", {"fields": ["home_score", "away_score"]}),
    ]

    list_display = ["home_team", "away_team", "match_date", "home_score", "away_score", "predicted"]

    list_filter = ["predicted", "match_date"]

    search_fields = ["match_date", "home_team", "away_team"]


admin.site.register(Match, MatchAdmin)
admin.site.register(Prediction)