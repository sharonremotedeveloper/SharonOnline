from django.contrib import admin
from .models import (
    BookingFunding, CreditBundle, FxRate, CreditPack, CreditPurchase, CreditWalletEntry,
    LedgerEntry, PaymentTransaction, RefundAttempt, RefundRequest, SettlementAnomaly,
)
from .services import refunds

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('gateway_reference', 'gateway', 'amount', 'currency', 'status', 'booking', 'created_at')
    list_filter = ('gateway', 'status', 'currency')
    search_fields = ('gateway_reference', 'booking__id', 'booking__student__username')
    readonly_fields = ('created_at', 'updated_at', 'raw_webhook_payload')

@admin.register(CreditBundle)
class CreditBundleAdmin(admin.ModelAdmin):
    list_display = ('user', 'pack_name', 'source', 'remaining_credits', 'total_credits', 'unit_amount', 'currency', 'expires_at', 'created_at')
    list_filter = ('source',)
    search_fields = ('user__username', 'pack_name')


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    """Refunds owed to students. The sweeper sends them to the gateway; a person marks one paid here only after paying it in the gateway's console."""
    list_display = ('id', 'user', 'booking', 'amount', 'currency', 'reason', 'status', 'failure_kind', 'attempts', 'created_at', 'processed_at')
    list_filter = ('status', 'failure_kind', 'reason', 'currency')
    search_fields = ('id', 'booking__id', 'user__username', 'gateway_reference')
    readonly_fields = [f.name for f in RefundRequest._meta.fields]
    actions = ['mark_paid_in_gateway']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Mark as paid in the gateway (posts the cash movement)')
    def mark_paid_in_gateway(self, request, queryset):
        done = 0
        for refund in queryset.filter(status__in=[RefundRequest.Status.PENDING_GATEWAY, RefundRequest.Status.FAILED]):
            refunds.mark_paid_manually(refund.pk, actor=request.user, reference=f'MANUAL-{refund.pk}')    # audited (RefundAttempt)
            done += 1
        self.message_user(request, f'{done} refund(s) marked as paid.')

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


admin.site.register(CreditPack)
admin.site.register(CreditPurchase)
admin.site.register(SettlementAnomaly)


@admin.register(CreditWalletEntry, BookingFunding, RefundAttempt)
class ImmutableFinanceAdmin(admin.ModelAdmin):
    readonly_fields = ()

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(FxRate)
class FxRateAdmin(admin.ModelAdmin):
    """Append-only: add a new rate, never edit or delete history. Prefer the Next.js admin screen (sanity-checked)."""
    list_display = ('currency', 'rate_to_zar', 'source', 'valid_from', 'set_by')
    readonly_fields = ('set_by', 'created_at')

    def has_change_permission(self, request, obj=None):
        return obj is None   # list view only; existing rows are read-only

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.set_by = request.user
        super().save_model(request, obj, form, change)
