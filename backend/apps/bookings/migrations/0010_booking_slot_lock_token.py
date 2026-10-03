from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('bookings', '0009_lesson_review_tags')]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='slot_lock_token',
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
    ]
