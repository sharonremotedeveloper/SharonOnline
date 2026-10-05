from django.urls import path
from apps.admin_api.fx_views import FxRateView
from apps.admin_api.refund_views import AdminRefundListView, AdminRefundRetryView
from apps.admin_api.teacher_review_views import (  # slice T1b
    CancelTutorFutureLessonsView, SuspendedTutorsWithLessonsView, TeacherReviewActionView,
)
from apps.admin_api.teacher_packet_views import TeacherReviewPacketView  # slice T4a
from apps.teachers.review import ACTIONS as TEACHER_REVIEW_ACTIONS
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
    # ---- slice T1b: explicit staff review actions, admin cancel of a suspended tutor's lessons, work queue ----
    *[path(f'teachers/<uuid:pk>/{name}/', TeacherReviewActionView.as_view(action_name=name), name=f'admin-teacher-{name}')
      for name in TEACHER_REVIEW_ACTIONS],
    path('teachers/<uuid:pk>/cancel-future-lessons/', CancelTutorFutureLessonsView.as_view(),
         name='admin-teacher-cancel-future-lessons'),
    path('teachers/<uuid:pk>/review-packet/', TeacherReviewPacketView.as_view(), name='admin-teacher-review-packet'),   # T4a
    path('teachers/suspended-with-lessons/', SuspendedTutorsWithLessonsView.as_view(), name='admin-teachers-suspended-with-lessons'),
    # ---- end T1b ----
    path('attendance/live/', LiveSessionsView.as_view(), name='admin-live-sessions'),
    path('disputes/', DisputesListView.as_view(), name='admin-disputes-list'),
    path('disputes/<uuid:pk>/resolve/', ResolveDisputeView.as_view(), name='admin-resolve-dispute'),
    path('finance/ledger/', EscrowLedgerView.as_view(), name='admin-escrow-ledger'),
    path('fx-rates/', FxRateView.as_view(), name='admin-fx-rates'),
    path('refunds/', AdminRefundListView.as_view(), name='admin-refunds-list'),
    path('refunds/<uuid:refund_id>/retry/', AdminRefundRetryView.as_view(), name='admin-refund-retry'),
    path('payouts/batch/', PayoutBatchView.as_view(), name='admin-payouts-batch'),
    path('payouts/execute-batch/', ExecutePayoutBatchView.as_view(), name='admin-execute-payout'),
]
