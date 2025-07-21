from predictions.models import Match
def run():
    for match in Match.objects.all():
        match.delete()
