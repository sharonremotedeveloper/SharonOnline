from django.urls import path
from apps.admin_api.views import (
    AdminTelemetryView,
    PendingTeachersListView,
    VerifyTeacherView,
    LiveSessionsView,
    DisputesListView,
    ResolveDisputeView,
    EscrowLedgerView,
    PayoutBatchView,
    ExecutePayoutBatchView,
)

urlpatterns = [
    path('telemetry/', AdminTelemetryView.as_view(), name='admin-telemetry'),
    path('teachers/pending-vetting/', PendingTeachersListView.as_view(), name='admin-pending-teachers'),
    path('teachers/<uuid:pk>/verify/', VerifyTeacherView.as_view(), name='admin-verify-teacher'),
    path('attendance/live/', LiveSessionsView.as_view(), name='admin-live-sessions'),
    path('disputes/', DisputesListView.as_view(), name='admin-disputes-list'),
    path('disputes/<uuid:pk>/resolve/', ResolveDisputeView.as_view(), name='admin-resolve-dispute'),
    path('finance/ledger/', EscrowLedgerView.as_view(), name='admin-escrow-ledger'),
    path('payouts/batch/', PayoutBatchView.as_view(), name='admin-payouts-batch'),
    path('payouts/execute-batch/', ExecutePayoutBatchView.as_view(), name='admin-execute-payout'),
]
