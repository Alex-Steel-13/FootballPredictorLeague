from predictions.models import Match
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")
import django
django.setup()
def run():
    for match in Match.objects.all():
        match.delete()
