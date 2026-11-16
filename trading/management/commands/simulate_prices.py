import random
from decimal import Decimal

from django.core.management.base import BaseCommand

from trading.models import Security


class Command(BaseCommand):
    help = "Apply a random-walk price tick to every security (stand-in for a market data feed)."

    def add_arguments(self, parser):
        parser.add_argument("--volatility", type=float, default=0.02, help="Max fractional move per tick.")

    def handle(self, volatility, **options):
        securities = list(Security.objects.exclude(last_price=0))
        for security in securities:
            move = Decimal(str(random.uniform(-volatility, volatility)))
            security.last_price = (security.last_price * (1 + move)).quantize(Decimal("0.0001"))
        Security.objects.bulk_update(securities, ["last_price"])
        self.stdout.write(self.style.SUCCESS(f"Updated {len(securities)} prices."))
