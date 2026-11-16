"""CSV importers for securities and STOCK Act disclosures."""

import csv
import re
from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import CongressionalTrade, CongressMember, Security

TYPE_ALIASES = {
    "purchase": CongressionalTrade.Type.PURCHASE,
    "p": CongressionalTrade.Type.PURCHASE,
    "buy": CongressionalTrade.Type.PURCHASE,
    "sale": CongressionalTrade.Type.SALE,
    "sale_full": CongressionalTrade.Type.SALE,
    "sale_partial": CongressionalTrade.Type.SALE,
    "sale (full)": CongressionalTrade.Type.SALE,
    "sale (partial)": CongressionalTrade.Type.SALE,
    "s": CongressionalTrade.Type.SALE,
    "sell": CongressionalTrade.Type.SALE,
    "exchange": CongressionalTrade.Type.EXCHANGE,
    "e": CongressionalTrade.Type.EXCHANGE,
}


def parse_amount_range(text):
    """'$15,001 - $50,000' -> (15001, 50000); '$1,000,001 +' / 'Over $50,000,000' -> (n, n)."""
    numbers = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", text) if n.strip(",")]
    if not numbers:
        raise ValueError(f"cannot parse amount range {text!r}")
    return numbers[0], numbers[-1]


def import_securities(path):
    count = 0
    with open(path, newline="", encoding="utf-8") as fh, transaction.atomic():
        for row in csv.DictReader(fh):
            Security.objects.update_or_create(
                ticker=row["ticker"].strip().upper(),
                defaults={"name": row["name"].strip(), "last_price": Decimal(row["last_price"])},
            )
            count += 1
    return count


def import_congressional_trades(path, create_missing_securities=True):
    """Returns (created, skipped). Rows for unknown tickers are skipped unless create_missing_securities."""
    created = skipped = 0
    with open(path, newline="", encoding="utf-8") as fh, transaction.atomic():
        for row in csv.DictReader(fh):
            ticker = row["ticker"].strip().upper()
            trade_type = TYPE_ALIASES.get(row["type"].strip().lower())
            if not ticker or ticker == "--" or trade_type is None:
                skipped += 1
                continue

            security = Security.objects.filter(ticker=ticker).first()
            if security is None:
                if not create_missing_securities:
                    skipped += 1
                    continue
                security = Security.objects.create(ticker=ticker, name=ticker, last_price=Decimal("0"))

            member, _ = CongressMember.objects.get_or_create(
                full_name=row["member"].strip(),
                defaults={
                    "chamber": row.get("chamber", "HOUSE").strip().upper(),
                    "party": row.get("party", "").strip(),
                    "state": row.get("state", "").strip().upper()[:2],
                },
            )
            amount_min, amount_max = parse_amount_range(row["amount"])
            _, was_created = CongressionalTrade.objects.get_or_create(
                member=member,
                security=security,
                transaction_type=trade_type,
                transaction_date=date.fromisoformat(row["transaction_date"].strip()),
                amount_min=amount_min,
                owner=row.get("owner", "").strip(),
                defaults={
                    "disclosure_date": date.fromisoformat(row["disclosure_date"].strip()),
                    "amount_max": amount_max,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1
    return created, skipped
