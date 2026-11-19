from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("daily-revenue/", views.daily_revenue_report, name="daily_revenue"),
]
