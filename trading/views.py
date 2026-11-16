from django.db.models import Count, Q
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CongressionalTrade, CongressMember, Portfolio, Security, WatchlistItem
from .serializers import (
    CongressionalTradeSerializer,
    CongressMemberSerializer,
    OrderSerializer,
    PlaceOrderSerializer,
    PortfolioSerializer,
    RegisterSerializer,
    SecuritySerializer,
    TransactionSerializer,
    WatchlistItemSerializer,
)
from .services import OrderRejected, place_market_order


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class SecurityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SecuritySerializer
    lookup_field = "ticker"

    def get_queryset(self):
        qs = Security.objects.all()
        if q := self.request.query_params.get("q"):
            qs = qs.filter(Q(ticker__icontains=q) | Q(name__icontains=q))
        return qs

    def get_object(self):
        self.kwargs["ticker"] = self.kwargs["ticker"].upper()
        return super().get_object()

    @action(detail=True, url_path="congressional-trades")
    def congressional_trades(self, request, ticker=None):
        security = self.get_object()
        trades = CongressionalTrade.objects.filter(security=security).select_related("member", "security")
        page = self.paginate_queryset(trades)
        return self.get_paginated_response(CongressionalTradeSerializer(page, many=True).data)


class PortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioSerializer

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user).prefetch_related("holdings__security")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get", "post"])
    def orders(self, request, pk=None):
        portfolio = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(portfolio.orders.select_related("security"))
            return self.get_paginated_response(OrderSerializer(page, many=True).data)

        params = PlaceOrderSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        try:
            order = place_market_order(portfolio.pk, **params.validated_data)
        except OrderRejected as exc:
            return Response(OrderSerializer(exc.order).data, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True)
    def transactions(self, request, pk=None):
        portfolio = self.get_object()
        page = self.paginate_queryset(portfolio.transactions.select_related("security"))
        return self.get_paginated_response(TransactionSerializer(page, many=True).data)


class WatchlistViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = WatchlistItemSerializer

    def get_queryset(self):
        return WatchlistItem.objects.filter(user=self.request.user).select_related("security")

    @action(detail=False, url_path="congressional-activity")
    def congressional_activity(self, request):
        """Congressional trades across every security on the user's watchlist."""
        security_ids = self.get_queryset().values_list("security_id", flat=True)
        trades = CongressionalTrade.objects.filter(security_id__in=security_ids).select_related("member", "security")
        page = self.paginate_queryset(trades)
        return self.get_paginated_response(CongressionalTradeSerializer(page, many=True).data)


class CongressMemberViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CongressMemberSerializer
    queryset = CongressMember.objects.annotate(trade_count=Count("trades")).order_by("-trade_count", "full_name")

    @action(detail=True)
    def trades(self, request, pk=None):
        member = self.get_object()
        page = self.paginate_queryset(member.trades.select_related("member", "security"))
        return self.get_paginated_response(CongressionalTradeSerializer(page, many=True).data)


class CongressionalTradeViewSet(viewsets.ReadOnlyModelViewSet):
    """Filter with ?ticker=, ?member=, ?type=PURCHASE|SALE, ?since=YYYY-MM-DD."""

    serializer_class = CongressionalTradeSerializer

    def get_queryset(self):
        qs = CongressionalTrade.objects.select_related("member", "security")
        p = self.request.query_params
        if ticker := p.get("ticker"):
            qs = qs.filter(security__ticker=ticker.upper())
        if member := p.get("member"):
            qs = qs.filter(member__full_name__icontains=member)
        if trade_type := p.get("type"):
            qs = qs.filter(transaction_type=trade_type.upper())
        if since := p.get("since"):
            qs = qs.filter(transaction_date__gte=since)
        return qs
