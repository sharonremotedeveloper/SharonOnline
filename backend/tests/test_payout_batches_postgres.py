"""
P1a-c on PostgreSQL (plan section 5: every new row lock and constraint has a Postgres-marked test; the `postgres-ledger` CI job
runs `-m postgres`). SQLite ignores row locks, so these are the tests that can see a race.
"""
import threading
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.db import connection

import factories as f
from apps.admin_api.models import PayoutBatch, PayoutBatchLine
from apps.payments.models import LedgerEntry
from apps.payments.services import payout_batches as svc
from test_payout_batches import owed

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def pg_only(settings):
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL row-lock and constraint behaviour')
    settings.PAYOUT_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
    settings.PAYOUT_DATA_ACTIVE_KEY = 'v1'
    settings.PAYOUT_MIN_ZAR = Decimal('100')


def _in_threads(count, fn):
    barrier = threading.Barrier(count)
    outcomes = []

    def run(index):
        from django.db import connections
        try:
            barrier.wait()
            outcomes.append(('ok', fn(index)))
        except BaseException as exc:                 # surfaced by the asserting caller
            outcomes.append(('error', exc))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    return outcomes


def test_concurrent_batch_builders_put_a_tutor_in_exactly_one_open_batch():
    owed(f.make_teacher_profile(), '300.00')
    makers = [f.make_admin() for _ in range(4)]
    outcomes = _in_threads(4, lambda i: svc.create_batch(actor=makers[i])[0].id)
    made = [o for kind, o in outcomes if kind == 'ok']
    refused = [o for kind, o in outcomes if kind == 'error']
    assert len(made) == 1, outcomes
    assert all(isinstance(e, svc.PayoutError) and e.code == 'nothing_to_pay' for e in refused), refused
    assert PayoutBatchLine.objects.filter(is_open=True).count() == 1


def test_two_people_marking_the_same_batch_processed_post_it_once():
    owed(f.make_teacher_profile(), '300.00')
    maker, first, second = f.make_admin(), f.make_admin(), f.make_admin()
    batch = svc.create_batch(actor=maker)[0]
    svc.approve_batch(batch.id, actor=first)
    svc.export_batch(batch.id, actor=first)
    outcomes = _in_threads(2, lambda i: svc.mark_processed(batch.id, actor=(first, second)[i]).status)
    assert [kind for kind, _ in outcomes] == ['ok', 'ok'], outcomes
    assert LedgerEntry.objects.filter(payout_batch=batch, event_type='payout_executed').count() == 2     # one DR + one CR
    assert PayoutBatch.objects.get(pk=batch.pk).status == 'processed'
