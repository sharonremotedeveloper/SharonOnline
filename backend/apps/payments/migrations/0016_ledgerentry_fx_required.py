from django.db import migrations, models


# Schema-only (Task 10.1 slice B): drops the model-level defaults (18.75 / 'legacy_default') on LedgerEntry so every new
# row must carry the rate it was captured at. Existing rows are immutable and are not touched; the database never had a
# column default, so this emits no SQL on PostgreSQL.
class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0015_lessonprice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ledgerentry',
            name='fx_rate_to_zar',
            field=models.DecimalField(decimal_places=6, max_digits=12),
        ),
        migrations.AlterField(
            model_name='ledgerentry',
            name='fx_source',
            field=models.CharField(max_length=64),
        ),
    ]
