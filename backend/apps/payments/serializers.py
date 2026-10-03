from rest_framework import serializers

from .models import TutorPayoutAccount
from .services.payout_crypto import decrypt_payout_payload, encrypt_payout_payload


SA_BANKS = {
    'Capitec Bank': '470010',
    'First National Bank (FNB)': '250655',
    'Standard Bank': '051001',
    'Nedbank': '198765',
    'Absa Bank': '632005',
    'Discovery Bank': '679000',
    'TymeBank': '678910',
    'Investec Bank': '580105',
}


class PayoutAccountWriteSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    account_holder_name = serializers.CharField(max_length=150)
    account_number = serializers.RegexField(r'^\d{6,16}$', max_length=16)
    bank_name = serializers.ChoiceField(choices=tuple(SA_BANKS))
    branch_code = serializers.RegexField(r'^\d{6}$', max_length=6)
    account_type = serializers.ChoiceField(choices=('cheque', 'savings'))
    identification_number = serializers.RegexField(r'^[A-Za-z0-9 -]{6,30}$', required=False, allow_blank=True)

    def validate_account_holder_name(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Enter the account holder name.')
        return value

    def validate(self, attrs):
        request = self.context['request']
        if not request.user.check_password(attrs['current_password']):
            raise serializers.ValidationError({'current_password': 'Your current password is incorrect.'})
        expected = SA_BANKS[attrs['bank_name']]
        if attrs['branch_code'] != expected:
            raise serializers.ValidationError({'branch_code': f'Use the supported universal branch code {expected}.'})
        return attrs

    def save(self, **kwargs):
        data = dict(self.validated_data)
        data.pop('current_password')
        ciphertext, version = encrypt_payout_payload(data)
        account, _ = TutorPayoutAccount.objects.update_or_create(
            tutor=self.context['request'].user,
            defaults={
                'encrypted_payload': ciphertext,
                'key_version': version,
                'account_last_four': data['account_number'][-4:],
            },
        )
        return account


class PayoutAccountMaskedSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    bank_name = serializers.ChoiceField(choices=tuple(SA_BANKS), required=False)
    account_holder_name = serializers.CharField(required=False)
    account_number_masked = serializers.CharField(required=False)
    branch_code = serializers.CharField(required=False)
    account_type = serializers.ChoiceField(choices=('cheque', 'savings'), required=False)
    identification_masked = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.DateTimeField(required=False)


def masked_payout_account(account):
    if account is None:
        return {'configured': False}
    payload = decrypt_payout_payload(account.encrypted_payload, account.key_version)
    identification = payload.get('identification_number', '')
    return {
        'configured': True,
        'bank_name': payload['bank_name'],
        'account_holder_name': payload['account_holder_name'],
        'account_number_masked': f'****{account.account_last_four}',
        'branch_code': payload['branch_code'],
        'account_type': payload['account_type'],
        'identification_masked': f'****{identification[-4:]}' if identification else '',
        'updated_at': account.updated_at,
    }


class TutorWalletFxSerializer(serializers.Serializer):
    currency = serializers.CharField()
    fx_rate_to_zar = serializers.DecimalField(max_digits=12, decimal_places=6, coerce_to_string=False)
    fx_source = serializers.CharField()


class TutorWalletTransactionSerializer(serializers.Serializer):
    id = serializers.CharField()
    date = serializers.DateTimeField()
    booking_ref = serializers.CharField(allow_blank=True)
    student_name = serializers.CharField()
    gross_amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    currency = serializers.CharField()
    gross_zar = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    net_zar = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    fx_rate_to_zar = serializers.DecimalField(max_digits=12, decimal_places=6, coerce_to_string=False)
    fx_source = serializers.CharField()
    status = serializers.CharField()


class TutorWalletSerializer(serializers.Serializer):
    pending_escrow_zar = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    cleared_balance_zar = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    fx_context = TutorWalletFxSerializer(many=True)
    payout_bank_account = PayoutAccountMaskedSerializer(allow_null=True)
    transactions = TutorWalletTransactionSerializer(many=True)
