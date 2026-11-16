from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from trading import views

router = DefaultRouter()
router.register("securities", views.SecurityViewSet, basename="security")
router.register("portfolios", views.PortfolioViewSet, basename="portfolio")
router.register("watchlist", views.WatchlistViewSet, basename="watchlist")
router.register("congress/members", views.CongressMemberViewSet, basename="congress-member")
router.register("congress/trades", views.CongressionalTradeViewSet, basename="congress-trade")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", lambda request: JsonResponse({"status": "ok"})),
    path("api/auth/register/", views.RegisterView.as_view(), name="register"),
    path("api/auth/token/", obtain_auth_token, name="token"),
    path("api/", include(router.urls)),
]
