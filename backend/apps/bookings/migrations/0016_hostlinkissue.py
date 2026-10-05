import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Slice Z1 (QA #3): audit + review hold for a host link issued to staff. New table only; additive and reversible."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('bookings', '0015_clear_stored_zoom_start_urls'),
    ]

    operations = [
        migrations.CreateModel(
            name='HostLinkIssue',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('booking', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='host_link_issues',
                                              to='bookings.booking')),
                ('issued_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                                                to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['booking', 'reviewed_at'], name='bookings_ho_booking_f455bc_idx')],
            },
        ),
    ]
