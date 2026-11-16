"""Order execution. All balance/holding mutations happen here, inside one DB transaction."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import Holding, Order, Portfolio, Security, Transaction

CENTS = Decimal("0.01")


class OrderRejected(Exception):
    def __init__(self, order):
        super().__init__(order.reject_reason)
        self.order = order


def place_market_order(portfolio_id, ticker, side, quantity):
    """Fill a simulated market order at the security's last price.

    The portfolio row is locked with SELECT ... FOR UPDATE so concurrent orders on the
    same portfolio serialize; cash, holding, order and ledger rows commit together or not at all.
    Rejected orders are recorded with no balance changes and raised as OrderRejected.
    """
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if side not in Order.Side.values:
        raise ValueError(f"unknown side {side!r}")

    with transaction.atomic():
        portfolio = Portfolio.objects.select_for_update().get(pk=portfolio_id)
        security = Security.objects.get(ticker=ticker.upper())
        price = security.last_price
        notional = (price * quantity).quantize(CENTS, rounding=ROUND_HALF_UP)
        holding = Holding.objects.select_for_update().filter(portfolio=portfolio, security=security).first()

        if side == Order.Side.BUY and notional > portfolio.cash_balance:
            reject_reason = "Insufficient cash"
        elif side == Order.Side.SELL and (not holding or holding.quantity < quantity):
            reject_reason = "Insufficient shares"
        else:
            reject_reason = ""

        if reject_reason:
            order = Order.objects.create(
                portfolio=portfolio,
                security=security,
                side=side,
                quantity=quantity,
                status=Order.Status.REJECTED,
                reject_reason=reject_reason,
            )
        else:
            order = _fill(portfolio, security, holding, side, quantity, price, notional)

    if order.status == Order.Status.REJECTED:
        raise OrderRejected(order)
    return order


def _fill(portfolio, security, holding, side, quantity, price, notional):
    if side == Order.Side.BUY:
        portfolio.cash_balance -= notional
        cash_delta = -notional
        if holding:
            total_cost = holding.average_cost * holding.quantity + price * quantity
            holding.quantity += quantity
            holding.average_cost = total_cost / holding.quantity
            holding.save()
        else:
            Holding.objects.create(portfolio=portfolio, security=security, quantity=quantity, average_cost=price)
    else:
        portfolio.cash_balance += notional
        cash_delta = notional
        holding.quantity -= quantity
        if holding.quantity == 0:
            holding.delete()
        else:
            holding.save()

    portfolio.save(update_fields=["cash_balance"])
    order = Order.objects.create(
        portfolio=portfolio,
        security=security,
        side=side,
        quantity=quantity,
        status=Order.Status.FILLED,
        fill_price=price,
    )
    Transaction.objects.create(
        portfolio=portfolio,
        order=order,
        security=security,
        side=side,
        quantity=quantity,
        price=price,
        cash_delta=cash_delta,
        cash_balance_after=portfolio.cash_balance,
    )
    return order
