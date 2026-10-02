from django.urls import path
from .views import (
    TeacherSlotsView,
    ReserveSlotView,
    BookingListCreateView,
    BookingDetailView,
    SubmitMemoView,
    LegacySubmitReviewView,
    ReportOutageView,
    RedeemCreditView,
)

urlpatterns = [
    path('slots/<uuid:teacher_id>/', TeacherSlotsView.as_view(), name='teacher-slots'),
    path('reserve/', ReserveSlotView.as_view(), name='booking-reserve-slot'),
    path('', BookingListCreateView.as_view(), name='booking-list-create'),
    path('<uuid:id>/', BookingDetailView.as_view(), name='booking-detail'),
    path('<uuid:booking_id>/memo/', SubmitMemoView.as_view(), name='booking-submit-memo'),
    path('<uuid:booking_id>/review/', LegacySubmitReviewView.as_view(), name='booking-submit-review'),
    path('<uuid:booking_id>/report-outage/', ReportOutageView.as_view(), name='booking-report-outage'),
    path('<uuid:booking_id>/redeem-credit/', RedeemCreditView.as_view(), name='booking-redeem-credit'),
]
