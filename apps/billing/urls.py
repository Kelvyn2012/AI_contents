from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("", views.billing_page, name="billing_page"),
    path("checkout/", views.checkout, name="checkout"),
    path("callback/", views.payment_callback, name="callback"),
    path("webhook/", views.webhook, name="webhook"),
    path("success/", views.payment_success, name="payment_success"),
    path("failure/", views.payment_failure, name="payment_failure"),
]
