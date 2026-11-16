from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from .importers import import_congressional_trades, import_securities, parse_amount_range
from .models import CongressionalTrade, Holding, Order, Portfolio, Security, Transaction
from .services import OrderRejected, place_market_order

SAMPLE_DIR = Path(settings.BASE_DIR) / "sample_data"


class OrderServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice", password="pw-123456")
        self.portfolio = Portfolio.objects.create(user=self.user, name="Main", cash_balance=Decimal("1000.00"))
        self.aapl = Security.objects.create(ticker="AAPL", name="Apple", last_price=Decimal("100.00"))

    def test_buy_debits_cash_and_creates_holding_and_ledger(self):
        order = place_market_order(self.portfolio.pk, "aapl", "BUY", "3")
        self.portfolio.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(self.portfolio.cash_balance, Decimal("700.00"))
        self.assertEqual(Holding.objects.get(portfolio=self.portfolio).quantity, Decimal("3"))
        txn = Transaction.objects.get(order=order)
        self.assertEqual(txn.cash_delta, Decimal("-300.00"))
        self.assertEqual(txn.cash_balance_after, Decimal("700.00"))

    def test_average_cost_is_weighted(self):
        place_market_order(self.portfolio.pk, "AAPL", "BUY", "2")
        self.aapl.last_price = Decimal("130.00")
        self.aapl.save()
        place_market_order(self.portfolio.pk, "AAPL", "BUY", "2")
        holding = Holding.objects.get(portfolio=self.portfolio)
        self.assertEqual(holding.quantity, Decimal("4"))
        self.assertEqual(holding.average_cost, Decimal("115.00"))

    def test_sell_all_removes_holding(self):
        place_market_order(self.portfolio.pk, "AAPL", "BUY", "5")
        place_market_order(self.portfolio.pk, "AAPL", "SELL", "5")
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.cash_balance, Decimal("1000.00"))
        self.assertFalse(Holding.objects.filter(portfolio=self.portfolio).exists())

    def test_insufficient_cash_is_rejected_without_side_effects(self):
        with self.assertRaises(OrderRejected) as ctx:
            place_market_order(self.portfolio.pk, "AAPL", "BUY", "11")
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.cash_balance, Decimal("1000.00"))
        self.assertEqual(ctx.exception.order.status, Order.Status.REJECTED)
        self.assertFalse(Holding.objects.exists())
        self.assertFalse(Transaction.objects.exists())

    def test_overselling_is_rejected(self):
        place_market_order(self.portfolio.pk, "AAPL", "BUY", "1")
        with self.assertRaises(OrderRejected):
            place_market_order(self.portfolio.pk, "AAPL", "SELL", "2")
        self.assertEqual(Holding.objects.get().quantity, Decimal("1"))

    def test_invalid_quantity_raises(self):
        with self.assertRaises(ValueError):
            place_market_order(self.portfolio.pk, "AAPL", "BUY", "0")


class ImporterTests(TestCase):
    def test_parse_amount_range(self):
        self.assertEqual(parse_amount_range("$15,001 - $50,000"), (15001, 50000))
        self.assertEqual(parse_amount_range("Over $50,000,000"), (50000000, 50000000))

    def test_import_is_idempotent(self):
        import_securities(SAMPLE_DIR / "securities.csv")
        created, _ = import_congressional_trades(SAMPLE_DIR / "congressional_trades.csv")
        self.assertEqual(created, 10)
        created_again, skipped = import_congressional_trades(SAMPLE_DIR / "congressional_trades.csv")
        self.assertEqual((created_again, skipped), (0, 10))
        self.assertEqual(CongressionalTrade.objects.count(), 10)


class ApiTests(APITestCase):
    def setUp(self):
        import_securities(SAMPLE_DIR / "securities.csv")
        import_congressional_trades(SAMPLE_DIR / "congressional_trades.csv")
        resp = self.client.post(
            "/api/auth/register/", {"username": "bob", "email": "bob@example.com", "password": "s3cure-pass!"}
        )
        self.assertEqual(resp.status_code, 201)
        token = self.client.post("/api/auth/token/", {"username": "bob", "password": "s3cure-pass!"}).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def test_requires_auth(self):
        self.client.credentials()
        self.assertEqual(self.client.get("/api/portfolios/").status_code, 401)

    def test_portfolio_trade_flow(self):
        portfolio = self.client.post("/api/portfolios/", {"name": "Growth"}).data
        self.assertEqual(Decimal(portfolio["cash_balance"]), Decimal(settings.STARTING_CASH))

        resp = self.client.post(f"/api/portfolios/{portfolio['id']}/orders/", {"ticker": "nvda", "side": "BUY", "quantity": "10"})
        self.assertEqual(resp.status_code, 201, resp.data)

        detail = self.client.get(f"/api/portfolios/{portfolio['id']}/").data
        self.assertEqual(detail["holdings"][0]["ticker"], "NVDA")
        self.assertEqual(Decimal(detail["total_value"]), Decimal(settings.STARTING_CASH))

        txns = self.client.get(f"/api/portfolios/{portfolio['id']}/transactions/").data
        self.assertEqual(txns["count"], 1)

        resp = self.client.post(f"/api/portfolios/{portfolio['id']}/orders/", {"ticker": "NVDA", "side": "SELL", "quantity": "999"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data["reject_reason"], "Insufficient shares")

    def test_cannot_access_other_users_portfolio(self):
        other = get_user_model().objects.create_user("eve", password="pw-123456")
        theirs = Portfolio.objects.create(user=other, name="Secret", cash_balance=Decimal("5"))
        self.assertEqual(self.client.get(f"/api/portfolios/{theirs.pk}/").status_code, 404)
        resp = self.client.post(f"/api/portfolios/{theirs.pk}/orders/", {"ticker": "AAPL", "side": "BUY", "quantity": "1"})
        self.assertEqual(resp.status_code, 404)

    def test_watchlist_congressional_activity(self):
        self.client.post("/api/watchlist/", {"ticker": "nvda"})
        self.client.post("/api/watchlist/", {"ticker": "XOM"})
        data = self.client.get("/api/watchlist/congressional-activity/").data
        self.assertEqual(data["count"], 2)
        self.assertEqual({t["ticker"] for t in data["results"]}, {"NVDA", "XOM"})

    def test_trade_filters(self):
        self.assertEqual(self.client.get("/api/congress/trades/?type=sale").data["count"], 3)
        self.assertEqual(self.client.get("/api/congress/trades/?member=ellis").data["count"], 2)
        self.assertEqual(self.client.get("/api/securities/aapl/congressional-trades/").data["count"], 1)
