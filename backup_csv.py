import pandas as pd
from predictions.models import Prediction

data = {"Date": [],
        "User": [],
        "Home Team": [],
        "Away Team": [],
        "Home Team Score": [],
        "Away Team Score": [],
        "Predicted Home Team Score": [],
        "Predicted Away Team Score": [],
        }

for prediction in Prediction.objects.all():
    data["Date"].append(prediction.match.match_date)
    data["User"].append(prediction.user.username)
    data["Home Team"].append(prediction.match.home_team)
    data["Away Team"].append(prediction.match.away_team)
    data["Home Team Score"].append(prediction.match.home_score)
    data["Away Team Score"].append(prediction.match.away_score)
    data["Predicted Home Team Score"].append(prediction.predicted_home_score)
    data["Predicted Away Team Score"].append(prediction.predicted_away_score)

# Create DataFrame and save to CSV
df = pd.DataFrame(data)
df.to_csv("predictions_backup.csv", index=False)
    