from django.urls import path, include
from . import views

app_name = "leaderboard"

urlpatterns = [
    path("", views.leaderboard, name="leaderboard"),
    path("predictions_this_week", views.predictions, name="predictions_this_week"),
    path("maanger_of_the_month", views.manager_of_month, name="manager_of_the_month")
]