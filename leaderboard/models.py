from django.db import models
from django.contrib.auth.models import User
from predictions.models import Prediction
from predictorleague import settings

# Create your models here.
class LeaderboardEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, default=None)
    score = models.IntegerField(default=0) #their score
    correct_predictions = models.IntegerField(default=0) #the number of times they predicted the correct winning team
    perfect_predictions = models.IntegerField(default=0) # the number of perfect predictions
    number_of_predictions = models.IntegerField(default=0)