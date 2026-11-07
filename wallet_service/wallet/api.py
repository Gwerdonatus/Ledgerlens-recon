from django.db.models import Q
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MAX_MINOR, Account, Transfer
from .services import make_transfer


class MinorUnitsField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            raise serializers.ValidationError("Use an integer number of minor units.")
        return super().to_internal_value(data)


class TransferInput(serializers.Serializer):
    source = serializers.UUIDField()
    destination = serializers.UUIDField()
    amount = MinorUnitsField(min_value=1, max_value=MAX_MINOR)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({field: "Unknown field." for field in unknown})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["source"] == attrs["destination"]:
            raise serializers.ValidationError("Choose two different accounts.")
        return attrs


class TransferOutput(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()

    def get_currency(self, obj):
        return "GBP"

    class Meta:
        model = Transfer
        fields = ["id", "source", "destination", "amount", "currency", "status", "created_at"]


class Transfers(APIView):
    def post(self, request):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValidationError(
                {"Idempotency-Key": "Provide 1–128 printable ASCII characters without spaces."}
            )
        data = TransferInput(data=request.data)
        data.is_valid(raise_exception=True)
        result, code = make_transfer(user=request.user, key=key, **data.validated_data)
        return Response(result, status=code)


class TransferDetail(generics.RetrieveAPIView):
    serializer_class = TransferOutput

    def get_queryset(self):
        return Transfer.objects.filter(
            Q(source__owner=self.request.user) | Q(destination__owner=self.request.user)
        )


class AccountOutput(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "balance", "currency"]


class WalletPagination(LimitOffsetPagination):
    max_limit = 100


class Accounts(generics.ListAPIView):
    pagination_class = WalletPagination
    serializer_class = AccountOutput

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user).order_by("id")


class AccountHistory(generics.ListAPIView):
    pagination_class = WalletPagination
    serializer_class = TransferOutput

    def get_queryset(self):
        from django.shortcuts import get_object_or_404

        account = get_object_or_404(Account, pk=self.kwargs["pk"], owner=self.request.user)
        return Transfer.objects.filter(Q(source=account) | Q(destination=account)).order_by(
            "-created_at", "-id"
        )
