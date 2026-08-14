import os
import django

# 1. Configure settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")

# 2. Setup Django
django.setup()

# 3. Import models (This MUST be below django.setup!)
from predictions.models import Match

def run():
    for match in Match.objects.all():
        match.delete()
    print("All matches deleted successfully!")