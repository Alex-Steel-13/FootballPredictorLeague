# backup_predictions.py
import os
import django
import pandas as pd

# --- set up Django (assumes this file lives next to manage.py) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")  # <- change to your project
django.setup()

from predictions.models import Prediction
from django.core.mail import EmailMessage
from django.conf import settings

def main():
    # Build data
    rows = []
    for p in Prediction.objects.select_related("match", "user"):
        rows.append({
            "Date": getattr(p.match.match_date, "isoformat", lambda: p.match.match_date)(),
            "User": p.user.username,
            "Home Team": p.match.home_team,
            "Away Team": p.match.away_team,
            "Home Team Score": p.match.home_score,
            "Away Team Score": p.match.away_score,
            "Predicted Home Team Score": p.predicted_home_score,
            "Predicted Away Team Score": p.predicted_away_score,
        })

    # Save CSV to a guaranteed location
    out_dir = os.path.expanduser("~/backups")
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "predictions_backup.csv")

    pd.DataFrame(rows).to_csv(out_csv, index=False)

    # Email it
    email = EmailMessage(
        subject="Automated Database CSV",
        body="Please find the attached database export for this week.",
        from_email=settings.EMAIL_HOST_USER,
        to=[settings.EMAIL_DESTINATION_USER, settings.EMAIL_HOST_USER],
    )
    email.attach_file(out_csv, mimetype="text/csv")
    sent = email.send()

    # Minimal diagnostics that show up in the task log
    print(f"Wrote: {out_csv}")
    print(f"email.send() returned: {sent}")

if __name__ == "__main__":
    main()