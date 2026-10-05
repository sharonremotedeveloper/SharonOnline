from django.db import migrations


def blank_stored_host_links(apps, schema_editor):
    """Slice Z1: host start links embed an expiring ZAK and are no longer stored. One UPDATE, each row once; no schema
    change in this migration, so no deferred trigger event can be pending before DDL (cf. ERR-192)."""
    Booking = apps.get_model('bookings', 'Booking')
    Booking.objects.exclude(zoom_start_url='').update(zoom_start_url='')
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')     # nothing left pending for a later migration's DDL


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0014_booking_zoom_host_user_id'),
    ]

    operations = [
        # Reverse: nothing to restore (the links had expired anyway).
        migrations.RunPython(blank_stored_host_links, migrations.RunPython.noop),
    ]
