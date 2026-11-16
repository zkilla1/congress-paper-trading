from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    CongressionalTrade,
    CongressMember,
    Holding,
    Order,
    Portfolio,
    Security,
    Transaction,
    WatchlistItem,
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data)


class SecuritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Security
        fields = ["id", "ticker", "name", "last_price", "updated_at"]


class HoldingSerializer(serializers.ModelSerializer):
    ticker = serializers.CharField(source="security.ticker", read_only=True)
    last_price = serializers.DecimalField(source="security.last_price", max_digits=14, decimal_places=4, read_only=True)
    market_value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    unrealized_pnl = serializers.SerializerMethodField()

    class Meta:
        model = Holding
        fields = ["ticker", "quantity", "average_cost", "last_price", "market_value", "unrealized_pnl"]

    def get_unrealized_pnl(self, obj):
        return str(((obj.security.last_price - obj.average_cost) * obj.quantity).quantize(Decimal("0.01")))


class PortfolioSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)
    holdings_value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Portfolio
        fields = ["id", "name", "cash_balance", "holdings_value", "total_value", "holdings", "created_at"]
        read_only_fields = ["cash_balance", "created_at"]

    def validate_name(self, value):
        user = self.context["request"].user
        qs = Portfolio.objects.filter(user=user, name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("You already have a portfolio with this name.")
        return value

    def create(self, validated_data):
        validated_data["cash_balance"] = Decimal(settings.STARTING_CASH)
        return super().create(validated_data)


class OrderSerializer(serializers.ModelSerializer):
    ticker = serializers.CharField(source="security.ticker", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "ticker", "side", "quantity", "status", "fill_price", "reject_reason", "created_at"]


class PlaceOrderSerializer(serializers.Serializer):
    ticker = serializers.CharField(max_length=12)
    side = serializers.ChoiceField(choices=Order.Side.choices)
    quantity = serializers.DecimalField(max_digits=16, decimal_places=4, min_value=Decimal("0.0001"))

    def validate_ticker(self, value):
        if not Security.objects.filter(ticker=value.upper()).exists():
            raise serializers.ValidationError("Unknown ticker.")
        return value.upper()


class TransactionSerializer(serializers.ModelSerializer):
    ticker = serializers.CharField(source="security.ticker", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "order", "ticker", "side", "quantity", "price", "cash_delta", "cash_balance_after", "created_at"]


class WatchlistItemSerializer(serializers.ModelSerializer):
    ticker = serializers.CharField(write_only=True)
    security = SecuritySerializer(read_only=True)

    class Meta:
        model = WatchlistItem
        fields = ["id", "ticker", "security"]

    def validate_ticker(self, value):
        try:
            return Security.objects.get(ticker=value.upper())
        except Security.DoesNotExist:
            raise serializers.ValidationError("Unknown ticker.")

    def create(self, validated_data):
        security = validated_data.pop("ticker")
        item, _ = WatchlistItem.objects.get_or_create(user=self.context["request"].user, security=security)
        return item


class CongressMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CongressMember
        fields = ["id", "full_name", "chamber", "party", "state"]


class CongressionalTradeSerializer(serializers.ModelSerializer):
    member = CongressMemberSerializer(read_only=True)
    ticker = serializers.CharField(source="security.ticker", read_only=True)

    class Meta:
        model = CongressionalTrade
        fields = [
            "id",
            "member",
            "ticker",
            "transaction_type",
            "transaction_date",
            "disclosure_date",
            "amount_min",
            "amount_max",
            "owner",
        ]
