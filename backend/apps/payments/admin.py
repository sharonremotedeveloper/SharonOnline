import re

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from .models import (
    BookingFunding, CreditBundle, FxRate, CreditPack, CreditPurchase, CreditWalletEntry, FulfillmentDispatch,
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


PROVIDER_REFUND_ID_RE = re.compile(r'[A-Za-z0-9_-]{5,64}')        # the shape of a PayPal refund id; fullmatch(), no newline loophole


class ProviderRefundIdsForm(forms.Form):
    """One required, well-formed gateway refund id per selected refund (field `ref_<refund pk>`)."""

    def __init__(self, refunds_, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.refunds = list(refunds_)
        for refund in self.refunds:
            self.fields[f'ref_{refund.pk}'] = forms.CharField(
                label='Gateway refund id', max_length=64, strip=True,
                widget=forms.TextInput(attrs={'size': 40, 'autocomplete': 'off'}))

    def clean(self):
        cleaned = super().clean()
        for refund in self.refunds:
            name = f'ref_{refund.pk}'
            value = cleaned.get(name)
            if value is not None and not PROVIDER_REFUND_ID_RE.fullmatch(value):
                self.add_error(name, 'Use the refund id shown by the gateway: 5 to 64 letters, digits, "-" or "_".')
        return cleaned

    def rows(self):
        return [(refund, self[f'ref_{refund.pk}']) for refund in self.refunds]


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    """Refunds owed to students. The sweeper sends them to the gateway; a person marks one paid here only after paying it in the gateway's console."""
    list_display = ('id', 'user', 'booking', 'amount', 'currency', 'reason', 'status', 'failure_kind', 'attempts', 'created_at', 'processed_at')
    list_filter = ('status', 'failure_kind', 'reason', 'currency')
    search_fields = ('id', 'booking__id', 'user__username', 'gateway_reference')
    readonly_fields = [f.name for f in RefundRequest._meta.fields]
    actions = ['mark_paid_in_gateway']
    mark_paid_template = 'admin/payments/refundrequest/mark_paid.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_mark_paid_permission(self, request):
        """Posting cash by hand is for superusers and platform admins (role), on top of Django's change permission."""
        user = request.user
        return bool(user.is_active and (user.is_superuser or getattr(user, 'role', None) == 'admin'))

    @admin.action(description='Mark as paid in the gateway (posts the cash movement)', permissions=['change', 'mark_paid'])
    def mark_paid_in_gateway(self, request, queryset):
        if not (self.has_change_permission(request) and self.has_mark_paid_permission(request)):
            raise PermissionDenied
        selected = list(queryset.order_by('created_at'))
        form = ProviderRefundIdsForm(selected, request.POST) if 'apply' in request.POST else ProviderRefundIdsForm(selected)
        if 'apply' in request.POST and form.is_valid():
            done = 0
            for refund in selected:
                if refund.status == RefundRequest.Status.PROCESSED:
                    self.message_user(request, f'Refund {refund.pk} was already paid ({refund.gateway_reference}); left unchanged.',
                                      messages.INFO)
                    continue
                try:
                    refunds.mark_paid_manually(refund.pk, actor=request.user, reference=form.cleaned_data[f'ref_{refund.pk}'])   # audited (RefundAttempt)
                except (refunds.RefundStateError, ValueError) as exc:
                    self.message_user(request, f'Refund {refund.pk} was not marked as paid: {exc}', messages.ERROR)
                else:
                    done += 1
            self.message_user(request, f'{done} refund(s) marked as paid.')
            return None
        context = {**self.admin_site.each_context(request), 'title': 'Mark refunds as paid in the gateway', 'opts': self.model._meta,
                   'form': form, 'rows': form.rows(), 'selected': [str(r.pk) for r in selected]}
        return TemplateResponse(request, self.mark_paid_template, context)


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


@admin.register(FulfillmentDispatch)
class FulfillmentDispatchAdmin(admin.ModelAdmin):
    """Lesson provisioning (Zoom room, tutor calendar, confirmation e-mail). Read-only; FAILED rows can be re-queued."""
    list_display = ('booking', 'status', 'attempts', 'zoom_state', 'calendar_state', 'email_state', 'last_error',
                    'next_retry_at', 'updated_at')
    list_filter = ('status', 'zoom_state', 'calendar_state', 'email_state')
    search_fields = ('booking__id',)
    readonly_fields = [f.name for f in FulfillmentDispatch._meta.fields]
    actions = ['requeue_failed']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_requeue_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and (user.is_superuser or getattr(user, 'role', None) == 'admin'))

    @admin.action(description='Re-queue FAILED fulfilment (fresh attempts)', permissions=['requeue'])
    def requeue_failed(self, request, queryset):
        if not self.has_requeue_permission(request):
            raise PermissionDenied
        from apps.bookings.services.fulfillment import admin_requeue
        requeued = admin_requeue(queryset, actor=request.user)          # audited: one log line per booking with the actor id
        self.message_user(request, f'{len(requeued)} fulfilment(s) re-queued; rows that were not FAILED were left unchanged.')


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
