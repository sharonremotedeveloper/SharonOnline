"""Run BEFORE turning TUTOR_TRAINING_GATE_ENABLED on (launch checklist, plan section 9): approved tutors without a training
date would otherwise vanish from search. Idempotent; `--dry-run` only reports."""
from django.core.management.base import BaseCommand

from apps.teachers import training


class Command(BaseCommand):
    help = 'Stamp training_completed_at on approved tutors that have none (idempotent), before enabling the training gate.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report only; change nothing.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        if not training.required_modules().exists():
            self.stdout.write(self.style.WARNING(
                'WARNING: there is no published required training module. With the gate on, no NEW tutor can finish training '
                'and become bookable: publish the modules first.'))
        count = training.backfill_training_completed(dry_run=dry)
        self.stdout.write(f"{'would stamp' if dry else 'stamped'} {count} approved tutor(s) without a training date")
