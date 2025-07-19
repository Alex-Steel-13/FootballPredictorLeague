from predictions.models import Prediction, Match
from leaderboard.models import LeaderboardEntry

def evaluate_scores():
    output = {}
    #gets the list of predictions
    predictions = Prediction.objects.select_related('match', 'user')

    for prediction in predictions.filter(evaluated_score=False):
        match = prediction.match

        if prediction.evaluated_score:
            continue
        if match.home_score is None or match.away_score is None:
            entry, created = LeaderboardEntry.objects.get_or_create(user=prediction.user)
            if entry:
                entry.number_of_predictions +=1
                entry.save()
            prediction.counted_for_in_number_of_predictions = True
            prediction.save()
            
            continue

        #working out who won the match
        home_team_won = False
        draw = False
        if match.home_score > match.away_score:
            home_team_won = True
        elif match.home_score == match.away_score:
            draw = True
        
        #working out who they predicted won
        predicted_home_won = False
        predicted_draw = False
        if prediction.predicted_home_score > prediction.predicted_away_score:
            predicted_home_won = True
        elif prediction.predicted_home_score == prediction.predicted_away_score:
            predicted_draw = True

        correct_away_winner_or_draw = False
        correct_home_winner = False
        #work out if predicted correct winner/draw
        if home_team_won and predicted_home_won:
            correct_home_winner = True
        elif draw and predicted_draw:
            correct_away_winner_or_draw = True
        elif not home_team_won and not predicted_home_won:
            correct_away_winner_or_draw = True
        else:
            correct_home_winner = False
            correct_away_winner_or_draw = False
        
        #work out if predicted correct home score
        if prediction.predicted_home_score == match.home_score:
            correct_home_score = True
        else:
            correct_home_score = False
        
        #work out if predicted correct away score
        if prediction.predicted_away_score == match.away_score:
            correct_away_score = True
        else:
            correct_away_score = False
        
        entry, created = LeaderboardEntry.objects.get_or_create(user=prediction.user)
        

        if entry:
            #increments number of predictions stat
            if not prediction.counted_for_in_number_of_predictions: # adds one to number of predictions
                entry.number_of_predictions +=1
                prediction.counted_for_in_number_of_predictions = True
                prediction.save()
            
            if correct_home_winner:#predicted home team won
                entry.correct_predictions +=1
                entry.score += 50
            
            if correct_away_winner_or_draw: # predicted away won or draw
                entry.correct_predictions +=1
                entry.score += 75
            
            
            if correct_home_score and correct_away_score:
                entry.perfect_predictions +=1
                entry.score += 50 # adds 50 points for getting it perfect

            
            entry.save()
            prediction.evaluated_score = True
            prediction.save()
            """
            print(
                f"User: {prediction.user.username}, "
                f"Match: {match.home_team} vs {match.away_team} on {match.match_date}, "
                f"Predicted: {prediction.predicted_home_score}-{prediction.predicted_away_score}, "
                f"Actual: {match.home_score}-{match.away_score}, "
                f"Evaluated: {prediction.evaluated_score}, "
                f"Counted: {prediction.counted_for_in_number_of_predictions}, "
                f"Correct Home Winner: {correct_home_winner}, "
                f"Correct Away Winner/Draw: {correct_away_winner_or_draw}, "
                f"Correct Home Score: {correct_home_score}, "
                f"Correct Away Score: {correct_away_score}, "
                f"Perfect Prediction: {correct_home_score and correct_away_score}, "
                f"Entry Score: {entry.score}, "
                f"Correct Predictions: {entry.correct_predictions}, "
                f"Perfect Predictions: {entry.perfect_predictions}, "
                f"Number of Predictions: {entry.number_of_predictions}"
            )
            """
