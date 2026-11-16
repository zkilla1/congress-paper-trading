from django.contrib import admin

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


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ["ticker", "name", "last_price", "updated_at"]
    search_fields = ["ticker", "name"]


class HoldingInline(admin.TabularInline):
    model = Holding
    extra = 0


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "cash_balance", "created_at"]
    inlines = [HoldingInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["portfolio", "security", "side", "quantity", "status", "fill_price", "created_at"]
    list_filter = ["status", "side"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["portfolio", "security", "side", "quantity", "price", "cash_delta", "created_at"]


@admin.register(CongressMember)
class CongressMemberAdmin(admin.ModelAdmin):
    list_display = ["full_name", "chamber", "party", "state"]
    list_filter = ["chamber", "party"]
    search_fields = ["full_name"]


@admin.register(CongressionalTrade)
class CongressionalTradeAdmin(admin.ModelAdmin):
    list_display = ["member", "security", "transaction_type", "transaction_date", "amount_min", "amount_max"]
    list_filter = ["transaction_type"]
    search_fields = ["member__full_name", "security__ticker"]


admin.site.register(WatchlistItem)
