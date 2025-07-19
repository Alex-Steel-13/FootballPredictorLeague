from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import datetime

# Create your models here.

class Match(models.Model):
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    match_date = models.DateField()
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    league = models.CharField(max_length=100, default = "")
    predicted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} on {self.match_date}"

class Prediction(models.Model):
    #creates a key for the user and the match they predicted
    user = models.ForeignKey(User, on_delete=models.CASCADE, default=None)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    evaluated_score = models.BooleanField(default=False) # if this prediction has been used to calculate someone's score, then its true
    counted_for_in_number_of_predictions = models.BooleanField(default=False)# if this has been used for number of predictions stat then true

    def clean(self): # a method to make sure the input is valid
        #Predictions are non negative integers
        if self.predicted_home_score < 0 or self.predicted_away_score < 0:
            raise ValidationError("A score is negative")
        #User predicts a match only once
        if Prediction.objects.filter(user = self.user, match=self.match).exclude(pk=self.pk).exists():
            raise ValidationError("You have already predicted this match")
    
    def error(self):
        date = datetime.date.today()


        #Scores are greater than 0
        if self.predicted_home_score < 0 or self.predicted_away_score < 0:
            return "Your scores must be positive integers"
        #User predicts a match only once
        if Prediction.objects.filter(user = self.user, match=self.match).exclude(pk=self.pk).exists():
            return "you have already predicted this match"
        


    def __str__(self):
        return f"{self.user.username} predicts {self.predicted_home_score}-{self.predicted_away_score} for {self.match}"