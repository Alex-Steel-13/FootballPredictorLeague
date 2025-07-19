from django.urls import path, include
from . import views

app_name = "leaderboard"

urlpatterns = [
    path("", views.leaderboard, name="leaderboard"),
    path("predictions_this_week", views.predictions, name="predictions_this_week")
]