"""D5: the fulfilment room step is provider-neutral (it provisions the Daily room)."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('payments', '0025_bank_change_challenge')]

    operations = [
        migrations.RenameField(model_name='fulfillmentdispatch', old_name='zoom_state', new_name='room_state'),
        migrations.RenameField(model_name='fulfillmentdispatch', old_name='zoom_completed', new_name='room_completed'),
    ]
