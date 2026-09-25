from django.contrib import admin
from .models import PaymentTransaction, CreditBundle

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('gateway_reference', 'gateway', 'amount', 'currency', 'status', 'booking', 'created_at')
    list_filter = ('gateway', 'status', 'currency')
    search_fields = ('gateway_reference', 'booking__id', 'booking__student__username')
    readonly_fields = ('created_at', 'updated_at', 'raw_webhook_payload')

@admin.register(CreditBundle)
class CreditBundleAdmin(admin.ModelAdmin):
    list_display = ('user', 'pack_name', 'remaining_credits', 'total_credits', 'amount_paid', 'currency', 'created_at')
    search_fields = ('user__username', 'pack_name')
