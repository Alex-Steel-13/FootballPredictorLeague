from django import forms
from . import models

class PredictionForm(forms.ModelForm):
    class Meta:
        model = models.Prediction
        fields = ["predicted_home_score", "predicted_away_score"]

class EditPredictionForm(forms.ModelForm):
    class Meta:
        model = models.Prediction
        fields = ["predicted_home_score", "predicted_away_score"]
