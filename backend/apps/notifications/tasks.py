"""Celery tasks of the notifications app; all route to the `notifications` queue (config/celery_schedule.py)."""
from celery import shared_task

from apps.common import clock
from apps.common.locks import distributed_task_lock


@shared_task(name='apps.notifications.tasks.deliver_notification_task')
def deliver_notification_task(notification_id: str) -> str:
    """Send one notification e-mail (claim protocol in notifications/delivery.py). Retries come from the sweep."""
    from apps.notifications.delivery import deliver
    return deliver(notification_id)


@shared_task(name='apps.notifications.tasks.sweep_notifications_task')
def sweep_notifications_task():
    """Every 2 minutes: due retries, lost messages (pending > 2 min) and expired 15-minute leases."""
    from apps.notifications.delivery import sweep_due

    @distributed_task_lock('lock:beat:sweep_notifications', timeout_seconds=110)
    def _execute():
        return {'enqueued': sweep_due(clock.now())}

    return _execute()


@shared_task(name='apps.notifications.tasks.purge_notifications_task')
def purge_notifications_task():
    """Daily: retention of read in-app items (180 days) and finished e-mail-only rows (90 days)."""
    from apps.notifications.retention import purge

    @distributed_task_lock('lock:beat:purge_notifications', timeout_seconds=3000)
    def _execute():
        return purge(clock.now())

    return _execute()
