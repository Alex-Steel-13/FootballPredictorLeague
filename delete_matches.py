from predictions.models import Match
import os

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")
django.setup()
from predictions.models import Match
def run():
    for match in Match.objects.all():
        match.delete()
