"""R1: minimize sensitive attendance payload retention without deleting verdicts."""

from datetime import timedelta
from django.db.models import Q
from apps.common import clock
from .models import AttendanceAudit, Booking

BATCH_SIZE = 1000
RETENTION_DAYS = 90
DISPUTE_WINDOW = timedelta(hours=24)


def purge_attendance_payloads(now=None):
    now = now or clock.now()
    cutoff = now - timedelta(days=RETENTION_DAYS)
    pending_refund = Q(booking__refund_requests__status__in={
        'awaiting_clearance', 'pending_gateway', 'submitted', 'failed'})
    protected = (Q(booking__status=Booking.Status.DISPUTED) |
                 Q(booking__dispute__status='open') |
                 pending_refund |
                 Q(booking__escrow_cleared_at__isnull=True) |
                 Q(booking__status__in={Booking.Status.STUDENT_NO_SHOW, Booking.Status.TEACHER_NO_SHOW},
                   booking__end_time_utc__gt=now - DISPUTE_WINDOW))
    qs = (AttendanceAudit.objects.filter(created_at__lt=cutoff).exclude(raw_payload={})
          .exclude(protected).order_by('id').values_list('id', flat=True))
    purged = 0
    while True:
        ids = list(qs[:BATCH_SIZE])
        if not ids:
            break
        purged += AttendanceAudit.objects.filter(id__in=ids).update(raw_payload={})
        if len(ids) < BATCH_SIZE:
            break
    return {'purged_count': purged, 'cutoff': cutoff.isoformat()}
