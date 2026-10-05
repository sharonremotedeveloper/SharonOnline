from django.db import migrations, models


class Migration(migrations.Migration):
    """Slice Z1: the Zoom user a lesson meeting was created under (HostPicker). Nullable, additive."""

    dependencies = [
        ('bookings', '0013_booking_cancel_reason_booking_cancelled_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='zoom_host_user_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
