"""
scrape_and_upload.py

Run this once a month on your laptop to scrape the latest fixtures and
write them straight into the live PythonAnywhere database. Replaces the
old flow of: scrape -> git push -> log into PythonAnywhere -> git pull ->
open a console -> run load_fixtures.py by hand.

How it works: opens an SSH tunnel to PythonAnywhere (this needs SSH access
enabled on your account, which requires a paid plan - see
https://help.pythonanywhere.com/pages/AccessingMySQLFromOutsidePythonAnywhere/),
points Django's database connection at that tunnel instead of the real
host, then scrapes and saves matches exactly like matches_scrape.py and
load_fixtures.py already do. The scrape itself still runs from your
laptop's IP - PythonAnywhere's servers never touch footballwebpages.co.uk.

Setup (one-off):
    pip install sshtunnel
    cp .env.example .env   # if you haven't already, then fill it in

Usage:
    python scrape_and_upload.py

Reads PA_USERNAME/PA_SSH_HOST/PA_SSH_PASSWORD and DB_HOST from .env (see
.env.example for what each one is). Leave PA_SSH_PASSWORD blank in .env to
be prompted for it interactively each run instead of storing it on disk -
either way, it's used only to open the SSH tunnel and is never written
anywhere by this script.
"""
import datetime
import getpass
import os

from decouple import config

# PythonAnywhere account details, from .env (see .env.example).
PA_USERNAME = config("PA_USERNAME")
PA_SSH_HOST = config("PA_SSH_HOST", default="ssh.pythonanywhere.com")
# The real production DB host - read now, before we override the DB_HOST
# environment variable further down for Django's benefit.
PROD_DB_HOST = config("DB_HOST")


def main():
    password = config("PA_SSH_PASSWORD", default="") or getpass.getpass(
        f"PythonAnywhere website password for '{PA_USERNAME}' "
        "(used only to open the SSH tunnel, never stored): "
    )

    import sshtunnel

    print(f"Opening SSH tunnel to {PA_SSH_HOST} ...")
    with sshtunnel.SSHTunnelForwarder(
        PA_SSH_HOST,
        ssh_username=PA_USERNAME,
        ssh_password=password,
        remote_bind_address=(PROD_DB_HOST, 3306),
    ) as tunnel:
        print(f"Tunnel open on 127.0.0.1:{tunnel.local_bind_port}")

        # Must be set *before* Django (and therefore settings.py) is
        # imported, so DATABASES picks up the tunnel instead of the real
        # host. See predictorleague/settings.py's DB_HOST/DB_PORT lookup.
        os.environ["DB_HOST"] = "127.0.0.1"
        os.environ["DB_PORT"] = str(tunnel.local_bind_port)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "predictorleague.settings")

        import django
        django.setup()

        from matches_scrape import scrape_all_leagues
        from load_fixtures import create_matches_from_rows

        print("Scraping fixtures...")
        df = scrape_all_leagues()
        print(f"Scraped {len(df)} fixtures.")

        # Local backup, purely so there's a record of what was scraped if
        # something goes wrong mid-upload - not required for the upload.
        os.makedirs("scraped_matches", exist_ok=True)
        backup_path = f"scraped_matches/matches_{datetime.date.today().isoformat()}.csv"
        df.to_csv(backup_path, index=False)
        print(f"Backup saved to {backup_path}")

        print("Uploading to the live database...")
        count = create_matches_from_rows(df.to_dict("records"))
        print(f"Done - added {count} matches to the live database.")


if __name__ == "__main__":
    main()
