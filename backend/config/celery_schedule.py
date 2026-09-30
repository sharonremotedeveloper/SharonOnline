from celery.schedules import crontab

# Sharon's ESL Marketplace - Production Celery Beat Schedule
# Compliant with SOW-ESL-2026-001 & Master Architecture Blueprint
CELERY_BEAT_SCHEDULE = {
    # 1. Purge expired 10-minute slot locks & abandoned checkouts (Every 60 seconds)
    'purge-expired-reservations-every-minute': {
        'task': 'apps.bookings.tasks.purge_expired_reservations_task',
        'schedule': 60.0,
        'options': {'queue': 'scheduler_beat', 'expires': 50},
    },

    # 2. Audit live attendance, drop-out radar, and no-shows (Every 60 seconds)
    'audit-live-attendance-every-minute': {
        'task': 'apps.bookings.tasks.audit_attendance_and_noshows_task',
        'schedule': 60.0,
        'options': {'queue': 'scheduler_beat', 'expires': 50},
    },

    # 3. Dispatch T-24h, T-1h, and T-10m pre-lesson reminders (Every 5 minutes)
    'dispatch-pre-lesson-reminders-5min': {
        'task': 'apps.bookings.tasks.dispatch_pre_lesson_reminders_task',
        'schedule': 300.0,
        'options': {'queue': 'notifications', 'expires': 240},
    },

    # 4. Release 24-hour cleared escrow holds to tutor wallets (Every 15 minutes)
    'release-escrow-holds-15min': {
        'task': 'apps.payments.tasks.release_cleared_escrow_task',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'financial_escrow', 'expires': 800},
    },

    # 5. Enforce 12h warning and 24h memo SLA penalties (Every 15 minutes)
    'enforce-memo-sla-15min': {
        'task': 'apps.bookings.tasks.enforce_memo_sla_task',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'scheduler_beat', 'expires': 800},
    },

    # 6. Synchronize EskomSePush load shedding stages & proactive alerts (Every 15 minutes)
    'sync-eskom-stages-15min': {
        'task': 'apps.integrations.tasks.sync_eskom_stages_task',
        'schedule': crontab(minute='*/15'),
        'options': {'queue': 'scheduler_beat', 'expires': 800},
    },

    # 7. Reconcile 2-way Google Calendar free/busy status (Every 30 minutes)
    'reconcile-gcal-freebusy-30min': {
        'task': 'apps.integrations.tasks.reconcile_teacher_gcal_task',
        'schedule': crontab(minute='0,30'),
        'options': {'queue': 'scheduler_beat', 'expires': 1600},
    },

    # 8. Reconcile stuck or unacknowledged webhook transactions (Hourly)
    'reconcile-unhandled-webhooks-hourly': {
        'task': 'apps.payments.tasks.reconcile_pending_transactions_task',
        'schedule': crontab(minute=45),
        'options': {'queue': 'financial_escrow', 'expires': 3000},
    },
}

# Task Queue Routing Definition
CELERY_TASK_ROUTES = {
    'apps.bookings.tasks.purge_expired_reservations_task': {'queue': 'scheduler_beat'},
    'apps.bookings.tasks.audit_attendance_and_noshows_task': {'queue': 'scheduler_beat'},
    'apps.bookings.tasks.dispatch_pre_lesson_reminders_task': {'queue': 'notifications'},
    'apps.bookings.tasks.enforce_memo_sla_task': {'queue': 'scheduler_beat'},
    'apps.payments.tasks.release_cleared_escrow_task': {'queue': 'financial_escrow'},
    'apps.payments.tasks.reconcile_pending_transactions_task': {'queue': 'financial_escrow'},
    'apps.integrations.tasks.sync_eskom_stages_task': {'queue': 'scheduler_beat'},
    'apps.integrations.tasks.reconcile_teacher_gcal_task': {'queue': 'scheduler_beat'},
    'apps.integrations.tasks.dispatch_booking_fulfillment': {'queue': 'critical_io'},
}
