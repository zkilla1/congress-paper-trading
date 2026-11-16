from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from trading.importers import import_congressional_trades, import_securities

SAMPLE_DIR = Path(settings.BASE_DIR) / "sample_data"


class Command(BaseCommand):
    help = "Load sample securities and (fictional) congressional trades for local development."

    def handle(self, **options):
        n = import_securities(SAMPLE_DIR / "securities.csv")
        created, skipped = import_congressional_trades(SAMPLE_DIR / "congressional_trades.csv")
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} securities and {created} congressional trades."))
