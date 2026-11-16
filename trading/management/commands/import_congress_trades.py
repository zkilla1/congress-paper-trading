from django.core.management.base import BaseCommand

from trading.importers import import_congressional_trades


class Command(BaseCommand):
    help = "Import congressional stock trade disclosures from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument(
            "--skip-unknown-tickers",
            action="store_true",
            help="Skip rows whose ticker is not already a Security instead of creating it.",
        )

    def handle(self, csv_path, skip_unknown_tickers, **options):
        created, skipped = import_congressional_trades(csv_path, create_missing_securities=not skip_unknown_tickers)
        self.stdout.write(self.style.SUCCESS(f"Imported {created} trades ({skipped} skipped/duplicates)."))
