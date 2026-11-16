from decimal import Decimal

from django.conf import settings
from django.db import models


class Security(models.Model):
    ticker = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=200)
    last_price = models.DecimalField(max_digits=14, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ticker"]
        verbose_name_plural = "securities"

    def __str__(self):
        return self.ticker


class Portfolio(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=100)
    cash_balance = models.DecimalField(max_digits=16, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_portfolio_name_per_user"),
            models.CheckConstraint(condition=models.Q(cash_balance__gte=0), name="cash_balance_non_negative"),
        ]

    def __str__(self):
        return f"{self.user} / {self.name}"

    @property
    def holdings_value(self):
        return sum((h.market_value for h in self.holdings.select_related("security")), Decimal("0"))

    @property
    def total_value(self):
        return self.cash_balance + self.holdings_value


class Holding(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="holdings")
    security = models.ForeignKey(Security, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=16, decimal_places=4)
    average_cost = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["portfolio", "security"], name="unique_holding_per_security"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="holding_quantity_positive"),
        ]

    @property
    def market_value(self):
        return self.quantity * self.security.last_price


class Order(models.Model):
    class Side(models.TextChoices):
        BUY = "BUY"
        SELL = "SELL"

    class Status(models.TextChoices):
        FILLED = "FILLED"
        REJECTED = "REJECTED"

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="orders")
    security = models.ForeignKey(Security, on_delete=models.PROTECT)
    side = models.CharField(max_length=4, choices=Side.choices)
    quantity = models.DecimalField(max_digits=16, decimal_places=4)
    status = models.CharField(max_length=8, choices=Status.choices)
    fill_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    reject_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Transaction(models.Model):
    """Immutable ledger entry written for every filled order."""

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="transactions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="transaction")
    security = models.ForeignKey(Security, on_delete=models.PROTECT)
    side = models.CharField(max_length=4, choices=Order.Side.choices)
    quantity = models.DecimalField(max_digits=16, decimal_places=4)
    price = models.DecimalField(max_digits=14, decimal_places=4)
    cash_delta = models.DecimalField(max_digits=16, decimal_places=2)
    cash_balance_after = models.DecimalField(max_digits=16, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WatchlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watchlist")
    security = models.ForeignKey(Security, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "security"], name="unique_watchlist_item")]


class CongressMember(models.Model):
    class Chamber(models.TextChoices):
        HOUSE = "HOUSE"
        SENATE = "SENATE"

    full_name = models.CharField(max_length=150, unique=True)
    chamber = models.CharField(max_length=6, choices=Chamber.choices)
    party = models.CharField(max_length=20, blank=True)
    state = models.CharField(max_length=2, blank=True)

    def __str__(self):
        return self.full_name


class CongressionalTrade(models.Model):
    """A disclosed stock trade from a member of Congress (STOCK Act periodic transaction report)."""

    class Type(models.TextChoices):
        PURCHASE = "PURCHASE"
        SALE = "SALE"
        EXCHANGE = "EXCHANGE"

    member = models.ForeignKey(CongressMember, on_delete=models.CASCADE, related_name="trades")
    security = models.ForeignKey(Security, on_delete=models.CASCADE, related_name="congressional_trades")
    transaction_type = models.CharField(max_length=8, choices=Type.choices)
    transaction_date = models.DateField()
    disclosure_date = models.DateField()
    amount_min = models.PositiveIntegerField()
    amount_max = models.PositiveIntegerField()
    owner = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["-transaction_date"]
        indexes = [models.Index(fields=["security", "-transaction_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "security", "transaction_type", "transaction_date", "amount_min", "owner"],
                name="unique_congressional_trade",
            )
        ]
