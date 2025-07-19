from django.urls import path, include
from . import views

app_name = "predictions"
urlpatterns = [
    path("", views.upcoming_matches, name="upcoming_matches"),
    path("match/<int:match_id>", views.predict, name="predict_match"),
    path("your_predictions", views.your_predictions, name="your_predictions"),
    path("edit_prediction/<int:prediction_id>/", views.edit_prediction, name="edit_prediction"),
    path('delete_prediction/<int:prediction_id>/', views.delete_prediction, name='delete_prediction'),
    path("your_past_predictions", views.your_past_predictions, name="your_past_predictions"),

]