from django.urls import path

from .wallet.api import AccountHistory, Accounts, TransferDetail, Transfers

urlpatterns = [
    path("transfers", Transfers.as_view()),
    path("transfers/<uuid:pk>", TransferDetail.as_view()),
    path("accounts", Accounts.as_view()),
    path("accounts/<uuid:pk>/transfers", AccountHistory.as_view()),
]
