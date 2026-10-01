from django.contrib import admin
from .models import PaymentTransaction, CreditBundle, LedgerEntry

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

@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('journal_batch_id', 'entry_type', 'amount', 'currency', 'amount_zar', 'account', 'event_type', 'created_at')
    list_filter = ('entry_type', 'account', 'event_type', 'currency')
    search_fields = ('journal_batch_id', 'description', 'booking__id', 'user__username', 'payment_transaction__gateway_reference')
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

